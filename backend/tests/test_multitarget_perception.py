import pytest

from app.schemas.multitarget import MultiTargetDetection
from app.schemas.tracking import Detection
from app.vision.detectors.multitarget import (
    EmptyMultiTargetDetector,
    FixtureMultiTargetDetector,
    normalize_raw_multitarget_detections,
    player_detections_from_multitarget,
)


def test_multitarget_detection_schema_serializes_player():
    detections = [
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="player", bbox=[1, 2, 10, 20], confidence=0.9, source_width=96, source_height=96),
    ]

    payload = [detection.model_dump(mode="json") for detection in detections]

    assert [item["class_name"] for item in payload] == ["player"]
    assert payload[0]["bbox"] == [1.0, 2.0, 10.0, 20.0]


def test_multitarget_detection_rejects_invalid_bbox():
    with pytest.raises(ValueError):
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="player", bbox=[5, 5, 4, 8], confidence=0.8, source_width=96, source_height=96)


def test_normalize_raw_multitarget_detections_filters_classes_and_confidence():
    detections = normalize_raw_multitarget_detections(
        [
            {"class_name": "person", "bbox": [10, 10, 30, 44], "confidence": 0.82},
            {"class_name": "person", "bbox": [20, 10, 30, 44], "confidence": 0.2},
            {"class_name": "spectator", "bbox": [0, 0, 10, 10], "confidence": 0.99},
            {"class_id": 2, "bbox": [30, 30, 42, 44], "confidence": 0.7},
        ],
        frame_index=0,
        timestamp_seconds=0,
        frame_width=96,
        frame_height=96,
        class_map={"person": "player"},
        confidence_thresholds={"player": 0.5},
    )

    assert [detection.class_name for detection in detections] == ["player"]


def test_fixture_and_empty_multitarget_detectors():
    fixture = FixtureMultiTargetDetector({0: [{"class_name": "player", "bbox": [1, 1, 12, 24], "confidence": 0.8}]})

    assert fixture.detect_frame(None, 0, 0, 96, 96)[0].class_name == "player"
    assert EmptyMultiTargetDetector().detect_frame(None, 0, 0, 96, 96) == []


def test_player_detections_from_multitarget_adapts_players():
    detections = [
        MultiTargetDetection(frame_index=0, timestamp_seconds=0, class_name="player", bbox=[1, 2, 10, 20], confidence=0.9, source_width=96, source_height=96),
    ]

    player_detections = player_detections_from_multitarget(detections)

    assert player_detections == [Detection(bbox=[1.0, 2.0, 10.0, 20.0], confidence=0.9)]
