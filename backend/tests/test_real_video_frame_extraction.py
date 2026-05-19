import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from app.vision.courtvision_calibration_engine.real_video_frame_extraction import (
    FrameExtractionError,
    FrameExtractionSettings,
    extract_real_video_frames,
    sanitize_video_stem,
)


cv2 = pytest.importorskip("cv2")


def test_extract_real_video_frames_samples_interval_limit_and_manifest(tmp_path):
    video = tmp_path / "phone court.mov"
    make_test_video(video, fps=5, frame_count=20)

    manifest = extract_real_video_frames(
        video,
        tmp_path / "frames",
        FrameExtractionSettings(
            interval_seconds=1.0,
            max_frames_per_video=3,
            jpeg_quality=90,
        ),
    )

    assert manifest["summary"]["video_count"] == 1
    assert manifest["summary"]["frames_written"] == 3
    assert manifest["summary"]["error_count"] == 0
    assert manifest["settings"]["interval_seconds"] == 1.0
    frames = manifest["videos"][0]["frames"]
    assert [frame["frame_index"] for frame in frames] == [0, 5, 10]
    assert [frame["timestamp_seconds"] for frame in frames] == [0.0, 1.0, 2.0]
    assert frames[0]["file_name"].startswith("phone-court_f000000_t00000.00s")
    assert all(Path(frame["output_path"]).exists() for frame in frames)

    manifest_path = tmp_path / "frames" / "manifest.json"
    assert manifest_path.exists()
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert written["summary"]["frames_written"] == 3


def test_extract_real_video_frames_honors_start_and_end_seconds(tmp_path):
    video = tmp_path / "tripod.mp4"
    make_test_video(video, fps=10, frame_count=50)

    manifest = extract_real_video_frames(
        video,
        tmp_path / "frames",
        FrameExtractionSettings(
            interval_seconds=1.0,
            max_frames_per_video=10,
            start_seconds=1.0,
            end_seconds=2.0,
        ),
    )

    frames = manifest["videos"][0]["frames"]
    assert [frame["frame_index"] for frame in frames] == [10, 20]
    assert [frame["timestamp_seconds"] for frame in frames] == [1.0, 2.0]


def test_extract_real_video_frames_processes_directory_per_video(tmp_path):
    source = tmp_path / "videos"
    source.mkdir()
    make_test_video(source / "court A.mp4", fps=5, frame_count=10)
    make_test_video(source / "court A.mov", fps=5, frame_count=10)
    (source / "notes.txt").write_text("ignore me", encoding="utf-8")

    manifest = extract_real_video_frames(
        source,
        tmp_path / "frames",
        FrameExtractionSettings(interval_seconds=1.0, max_frames_per_video=1),
    )

    assert manifest["summary"]["video_count"] == 2
    assert manifest["summary"]["frames_written"] == 2
    stems = [video["output_stem"] for video in manifest["videos"]]
    assert stems == ["court-A", "court-A-2"]
    assert (tmp_path / "frames" / "court-A").is_dir()
    assert (tmp_path / "frames" / "court-A-2").is_dir()


def test_extract_real_video_frames_reports_unreadable_video(tmp_path):
    video = tmp_path / "broken.mp4"
    video.write_text("not video", encoding="utf-8")

    manifest = extract_real_video_frames(
        video,
        tmp_path / "frames",
        FrameExtractionSettings(interval_seconds=1.0, max_frames_per_video=1),
    )

    assert manifest["summary"]["frames_written"] == 0
    assert manifest["summary"]["error_count"] == 1
    assert "Could not open video" in manifest["videos"][0]["errors"][0]["message"]


def test_extract_real_video_frames_rejects_invalid_settings(tmp_path):
    video = tmp_path / "input.mp4"
    make_test_video(video)

    with pytest.raises(FrameExtractionError, match="interval_seconds"):
        extract_real_video_frames(
            video,
            tmp_path / "frames",
            FrameExtractionSettings(interval_seconds=0),
        )


def test_extract_real_video_frames_script_returns_nonzero_for_missing_input(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "extract_real_video_frames.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(tmp_path / "missing.mp4"),
            "--output-root",
            str(tmp_path / "frames"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Input path not found" in result.stdout


def test_sanitize_video_stem_keeps_annotation_friendly_names():
    assert sanitize_video_stem(" phone court 01 ") == "phone-court-01"
    assert sanitize_video_stem("实拍 场地") == "video"


def make_test_video(path, fps=10, frame_count=12, size=(64, 48)):
    suffix = path.suffix.lower()
    fourcc = cv2.VideoWriter_fourcc(*("mp4v" if suffix in {".mp4", ".mov", ".m4v"} else "MJPG"))
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    assert writer.isOpened(), f"could not create synthetic video: {path}"
    width, height = size
    for index in range(frame_count):
        frame = np.full((height, width, 3), 35 + index, dtype=np.uint8)
        cv2.putText(frame, str(index), (4, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 220, 220), 1)
        writer.write(frame)
    writer.release()
