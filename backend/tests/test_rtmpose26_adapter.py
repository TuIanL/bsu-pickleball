from types import SimpleNamespace

import pytest

from app.schemas.pose import RTMPOSE26_KEYPOINT_NAMES, default_skeleton_edges
from app.schemas.tracking import FrameDetection
from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter


def test_rtmpose26_keypoint_names_match_halpe26():
    assert len(RTMPOSE26_KEYPOINT_NAMES) == 26
    assert RTMPOSE26_KEYPOINT_NAMES[19] == "hip"


def test_default_skeleton_edges_include_halpe26_core_links():
    edges = {(edge.from_keypoint, edge.to_keypoint) for edge in default_skeleton_edges()}

    assert ("neck", "hip") in edges
    assert ("left_ankle", "left_small_toe") in edges
    assert ("right_ankle", "right_heel") in edges


def test_normalize_keypoints_marks_low_confidence_invisible():
    adapter = RTMPose26Adapter(
        config_path=None,
        checkpoint_path=None,
        conf_threshold=0.5,
    )

    keypoints = [[float(index), float(index + 1)] for index in range(26)]
    scores = [0.75] * 26
    scores[3] = 0.25

    normalized = adapter._normalize_keypoints(keypoints, scores)

    assert normalized[0].name == "nose"
    assert normalized[0].visible is True
    assert normalized[3].name == "left_ear"
    assert normalized[3].visible is False


def test_normalize_keypoints_rejects_incompatible_count():
    adapter = RTMPose26Adapter(config_path=None, checkpoint_path=None)

    with pytest.raises(RuntimeError, match="expected 26"):
        adapter._normalize_keypoints([[0.0, 0.0]], [0.9])


def test_adapter_rejects_unsupported_schema():
    adapter = RTMPose26Adapter(config_path=None, checkpoint_path=None, keypoint_schema="coco17")

    with pytest.raises(RuntimeError, match="Unsupported RTMPose keypoint schema"):
        adapter._normalize_keypoints([], [])


def test_empty_or_invalid_subjects_skip_model_loading():
    adapter = RTMPose26Adapter(config_path=None, checkpoint_path=None)

    empty = adapter.estimate_frame(frame=object(), subjects=[], frame_index=3, timestamp_seconds=0.6)
    invalid = adapter.estimate_frame(
        frame=object(),
        subjects=[
            FrameDetection(
                frame_index=3,
                timestamp_seconds=0.6,
                bbox=[10, 10, 10, 40],
                confidence=0.9,
                track_id="1",
                source_width=100,
                source_height=100,
            )
        ],
        frame_index=3,
        timestamp_seconds=0.6,
    )

    assert empty.subjects == []
    assert invalid.subjects == []


def test_extract_keypoints_handles_mmpose_data_sample_shape():
    keypoints = [[[float(index), float(index + 2)] for index in range(26)]]
    scores = [[0.8 for _ in range(26)]]
    sample = SimpleNamespace(pred_instances=SimpleNamespace(keypoints=keypoints, keypoint_scores=scores))

    extracted_keypoints, extracted_scores = RTMPose26Adapter._extract_keypoints(sample)

    assert len(extracted_keypoints) == 26
    assert extracted_keypoints[0] == [0.0, 2.0]
    assert extracted_scores == [0.8 for _ in range(26)]


def test_extract_keypoints_handles_dict_shape_without_scores():
    keypoints = [[[float(index), float(index + 2)] for index in range(26)]]
    sample = {"pred_instances": {"keypoints": keypoints}}

    extracted_keypoints, extracted_scores = RTMPose26Adapter._extract_keypoints(sample)

    assert len(extracted_keypoints) == 26
    assert extracted_scores == [1.0 for _ in range(26)]
