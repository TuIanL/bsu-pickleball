import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from app.schemas.tracking import Detection
from app.vision.action_classification_preprocessing import (
    ActionPreprocessingConfig,
    ActionPreprocessingError,
    CLAHEConfig,
    ROIConfig,
    apply_clahe_bgr,
    build_clip_windows,
    crop_court_roi,
    crop_player,
    expand_box,
    export_action_classification_dataset,
    sample_frame_indices,
    select_target_detection,
)


cv2 = pytest.importorskip("cv2")


class FakeDetector:
    def __init__(self, detections_by_call):
        self.detections_by_call = detections_by_call
        self.calls = 0

    def detect(self, frame):
        detections = self.detections_by_call[min(self.calls, len(self.detections_by_call) - 1)]
        self.calls += 1
        return detections


def test_config_rejects_invalid_values(tmp_path):
    with pytest.raises(ActionPreprocessingError, match="target_fps"):
        ActionPreprocessingConfig(input_path=tmp_path, output_root=tmp_path / "out", label="serve", target_fps=0)

    with pytest.raises(ActionPreprocessingError, match="ROI"):
        ActionPreprocessingConfig(
            input_path=tmp_path,
            output_root=tmp_path / "out",
            label="serve",
            roi=ROIConfig(x1_ratio=0.9, y1_ratio=0.1, x2_ratio=0.2, y2_ratio=0.9),
        )


def test_sample_frame_indices_uses_target_fps_and_time_range():
    samples = sample_frame_indices(fps=60, frame_count=180, target_fps=20, start_seconds=1.0, end_seconds=1.2)

    assert samples == [(60, 1.0), (63, 1.05), (66, 1.1), (69, 1.15), (72, 1.2)]


def test_roi_clahe_expand_and_crop_player():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[:, :, 0] = 40
    frame[:, :, 1] = np.arange(200, dtype=np.uint8)
    frame[:, :, 2] = 100

    roi_frame, roi = crop_court_roi(frame, ROIConfig(x1_ratio=0.1, y1_ratio=0.2, x2_ratio=0.9, y2_ratio=0.8))
    assert roi_frame.shape[:2] == (60, 160)
    assert roi.bbox == [20, 20, 180, 80]

    enhanced = apply_clahe_bgr(roi_frame, clip_limit=2.0, tile_grid_size=4)
    assert enhanced.shape == roi_frame.shape

    expanded = expand_box([0, 0, 20, 20], roi_frame.shape, scale=1.5)
    assert expanded[0] == 0
    assert expanded[1] == 0
    assert expanded[2] > 20
    assert expanded[3] > 20

    crop, crop_box = crop_player(roi_frame, [10, 10, 40, 50], output_size=32, scale=1.4)
    assert crop.shape[:2] == (32, 32)
    assert crop_box[0] < 10
    assert crop_box[2] > 40


def test_select_target_detection_strategies():
    detections = [
        Detection(bbox=[5, 10, 25, 80], confidence=0.8),
        Detection(bbox=[70, 20, 95, 90], confidence=0.85),
        Detection(bbox=[40, 10, 55, 45], confidence=0.9),
    ]

    assert select_target_detection(detections, strategy="largest", frame_shape=(100, 100, 3)).bbox == [70, 20, 95, 90]
    assert select_target_detection(detections, strategy="near-left", frame_shape=(100, 100, 3)).bbox == [5, 10, 25, 80]
    assert select_target_detection(detections, strategy="near-right", frame_shape=(100, 100, 3)).bbox == [70, 20, 95, 90]
    assert (
        select_target_detection(
            detections,
            strategy="track-iou",
            frame_shape=(100, 100, 3),
            previous_bbox=[38, 8, 56, 46],
        ).bbox
        == [40, 10, 55, 45]
    )
    assert (
        select_target_detection(
            detections,
            strategy="manual-initial-bbox",
            frame_shape=(100, 100, 3),
            manual_initial_bbox=[4, 9, 24, 81],
        ).bbox
        == [5, 10, 25, 80]
    )


def test_build_clip_windows_handles_complete_and_short_sequences():
    assert build_clip_windows(5, clip_length=3, clip_stride=2) == [[0, 1, 2], [2, 3, 4]]
    assert build_clip_windows(2, clip_length=3, clip_stride=1) == []


def test_export_action_classification_dataset_with_fake_detector(tmp_path):
    video = tmp_path / "phone court.mp4"
    make_test_video(video, fps=10, frame_count=8, size=(120, 80))
    detections = [[Detection(bbox=[20, 10, 60, 70], confidence=0.91)] for _ in range(8)]
    config = ActionPreprocessingConfig(
        input_path=video,
        output_root=tmp_path / "processed",
        label="forehand",
        target_fps=10,
        roi=ROIConfig(x1_ratio=0.0, y1_ratio=0.0, x2_ratio=1.0, y2_ratio=1.0),
        clahe=CLAHEConfig(enabled=False),
        selection_strategy="largest",
        clip_length=4,
        clip_stride=4,
        output_size=32,
    )

    manifest = export_action_classification_dataset(config, detector=FakeDetector(detections))

    assert manifest["summary"]["video_count"] == 1
    assert manifest["summary"]["clips_written"] == 2
    assert manifest["summary"]["frames_written"] == 8
    first_clip = manifest["videos"][0]["clips"][0]
    assert first_clip["label"] == "forehand"
    assert first_clip["output_dir"].endswith("forehand/phone-court_clip0000")
    first_frame = first_clip["frames"][0]
    assert first_frame["frame_index"] == 0
    assert first_frame["bbox_roi"] == [20.0, 10.0, 60.0, 70.0]
    assert Path(first_frame["output_path"]).exists()

    written = json.loads((tmp_path / "processed" / "manifest.json").read_text(encoding="utf-8"))
    assert written["summary"]["clips_written"] == 2


def test_export_action_classification_dataset_reports_no_samples(tmp_path):
    video = tmp_path / "empty.mp4"
    make_test_video(video, fps=10, frame_count=4, size=(120, 80))
    config = ActionPreprocessingConfig(
        input_path=video,
        output_root=tmp_path / "processed",
        label="serve",
        target_fps=10,
        roi=ROIConfig(x1_ratio=0.0, y1_ratio=0.0, x2_ratio=1.0, y2_ratio=1.0),
        clahe=CLAHEConfig(enabled=False),
        clip_length=3,
        clip_stride=3,
    )

    manifest = export_action_classification_dataset(config, detector=FakeDetector([[]]))

    assert manifest["summary"]["status"] == "no_samples"
    assert manifest["summary"]["clips_written"] == 0
    assert manifest["summary"]["skipped_frame_count"] == 4
    assert "No complete clips generated" in manifest["videos"][0]["errors"][-1]["message"]


def test_export_action_classification_script_reports_missing_input(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "export_action_classification_dataset.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(tmp_path / "missing.mp4"),
            "--output-root",
            str(tmp_path / "processed"),
            "--label",
            "serve",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Input path not found" in result.stdout


def make_test_video(path, fps=10, frame_count=12, size=(64, 48)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    assert writer.isOpened(), f"could not create synthetic video: {path}"
    width, height = size
    for index in range(frame_count):
        frame = np.full((height, width, 3), 35 + index, dtype=np.uint8)
        cv2.rectangle(frame, (20, 10), (60, min(height - 1, 70)), (80, 140, 220), -1)
        writer.write(frame)
    writer.release()
