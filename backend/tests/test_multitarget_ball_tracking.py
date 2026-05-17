import json
from pathlib import Path

import pytest

from app.schemas.ball import BallOverlayArtifact
from app.schemas.multitarget import MultiTargetDetection
from app.schemas.tracking import Detection
from app.vision.detectors.multitarget import (
    EmptyMultiTargetDetector,
    FixtureMultiTargetDetector,
    normalize_raw_multitarget_detections,
    player_detections_from_multitarget,
)
from app.vision.tracking.ball_trajectory import BallTrajectoryBuilder


def ball(frame_index, x, y, confidence=0.9):
    return MultiTargetDetection(
        frame_index=frame_index,
        timestamp_seconds=frame_index / 5,
        class_name="ball",
        bbox=[x - 2, y - 2, x + 2, y + 2],
        confidence=confidence,
        source_width=96,
        source_height=96,
    )


def test_multitarget_detection_schema_serializes_player_ball_and_paddle():
    detections = [
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="player", bbox=[1, 2, 10, 20], confidence=0.9, source_width=96, source_height=96),
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="ball", bbox=[20, 22, 24, 26], confidence=0.8, source_width=96, source_height=96),
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="paddle", bbox=[30, 32, 38, 42], confidence=0.7, source_width=96, source_height=96),
    ]

    payload = [detection.model_dump(mode="json") for detection in detections]

    assert [item["class_name"] for item in payload] == ["player", "ball", "paddle"]
    assert payload[1]["bbox"] == [20.0, 22.0, 24.0, 26.0]


def test_multitarget_detection_rejects_invalid_bbox():
    with pytest.raises(ValueError):
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="ball", bbox=[5, 5, 4, 8], confidence=0.8, source_width=96, source_height=96)


def test_ball_overlay_fixture_artifacts_are_valid():
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    for name in [
        "ball-overlay-available.json",
        "ball-overlay-partial.json",
        "ball-overlay-no-detections.json",
        "ball-overlay-unavailable.json",
    ]:
        artifact = BallOverlayArtifact.model_validate(json.loads((fixture_dir / name).read_text(encoding="utf-8")))
        assert artifact.job_id == "job-ball-fixture"
        assert artifact.source.width == 96


def test_normalize_raw_multitarget_detections_filters_classes_and_confidence():
    detections = normalize_raw_multitarget_detections(
        [
            {"class_name": "pickleball", "bbox": [10, 10, 14, 14], "confidence": 0.82},
            {"class_name": "pickleball", "bbox": [20, 10, 24, 14], "confidence": 0.2},
            {"class_name": "spectator", "bbox": [0, 0, 10, 10], "confidence": 0.99},
            {"class_id": 2, "bbox": [30, 30, 42, 44], "confidence": 0.7},
        ],
        frame_index=0,
        timestamp_seconds=0,
        frame_width=96,
        frame_height=96,
        class_map={"pickleball": "ball", 2: "paddle"},
        confidence_thresholds={"player": 0.5, "ball": 0.5, "paddle": 0.6},
    )

    assert [detection.class_name for detection in detections] == ["ball", "paddle"]


def test_fixture_and_empty_multitarget_detectors():
    fixture = FixtureMultiTargetDetector({0: [{"class_name": "ball", "bbox": [1, 1, 5, 5], "confidence": 0.8}]})

    assert fixture.detect_frame(None, 0, 0, 96, 96)[0].class_name == "ball"
    assert EmptyMultiTargetDetector().detect_frame(None, 0, 0, 96, 96) == []


def test_player_detections_from_multitarget_ignores_ball_and_paddle():
    detections = [
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="player", bbox=[1, 2, 10, 20], confidence=0.9, source_width=96, source_height=96),
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="ball", bbox=[20, 22, 24, 26], confidence=0.8, source_width=96, source_height=96),
    ]

    player_detections = player_detections_from_multitarget(detections)

    assert player_detections == [Detection(bbox=[1.0, 2.0, 10.0, 20.0], confidence=0.9)]


def test_ball_trajectory_repairs_short_gap():
    builder = BallTrajectoryBuilder(max_gap_frames=2, max_speed_px_per_frame=50)

    frames, diagnostics = builder.build([ball(0, 10, 10), ball(2, 20, 20)])

    points = [point for frame in frames for point in frame.points]
    assert [point.source for point in points] == ["observed", "repaired", "observed"]
    assert diagnostics["repaired_points"] == 1
    assert diagnostics["segments"] == 1


def test_ball_trajectory_segments_long_gap():
    builder = BallTrajectoryBuilder(max_gap_frames=2, max_speed_px_per_frame=50)

    frames, diagnostics = builder.build([ball(0, 10, 10), ball(8, 20, 20)])

    points = [point for frame in frames for point in frame.points]
    assert [point.segment_id for point in points] == [1, 2]
    assert diagnostics["unresolved_gaps"] == 1


def test_ball_trajectory_rejects_implausible_repair():
    builder = BallTrajectoryBuilder(max_gap_frames=5, max_speed_px_per_frame=5)

    frames, diagnostics = builder.build([ball(0, 10, 10), ball(2, 90, 90)])

    points = [point for frame in frames for point in frame.points]
    assert [point.source for point in points] == ["observed", "observed"]
    assert diagnostics["unresolved_gaps"] == 1
