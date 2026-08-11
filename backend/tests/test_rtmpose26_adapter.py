import os
import sys
from types import SimpleNamespace
from types import ModuleType

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


def test_model_loading_prepares_torch_compatibility_and_restores_environment(monkeypatch, tmp_path):
    torch = pytest.importorskip("torch")
    numpy = pytest.importorskip("numpy")
    config_path = tmp_path / "rtmpose.py"
    checkpoint_path = tmp_path / "rtmpose.pth"
    config_path.write_text("# test config\n", encoding="utf-8")
    checkpoint_path.write_bytes(b"test checkpoint")

    observed: dict[str, object] = {}
    mmpose_module = ModuleType("mmpose")
    mmpose_apis_module = ModuleType("mmpose.apis")
    mmpose_utils_module = ModuleType("mmpose.utils")

    def fake_init_model(config, checkpoint, *, device):
        observed["env"] = os.environ.get("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD")
        observed["args"] = (config, checkpoint, device)
        return object()

    def fake_register_all_modules():
        observed["registered"] = True

    mmpose_apis_module.init_model = fake_init_model
    mmpose_utils_module.register_all_modules = fake_register_all_modules
    mmpose_module.apis = mmpose_apis_module
    mmpose_module.utils = mmpose_utils_module
    monkeypatch.setitem(sys.modules, "mmpose", mmpose_module)
    monkeypatch.setitem(sys.modules, "mmpose.apis", mmpose_apis_module)
    monkeypatch.setitem(sys.modules, "mmpose.utils", mmpose_utils_module)

    safe_globals_calls: list[list[object]] = []
    monkeypatch.setattr(
        torch.serialization,
        "add_safe_globals",
        lambda values: safe_globals_calls.append(list(values)),
    )
    monkeypatch.delenv("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", raising=False)

    adapter = RTMPose26Adapter(str(config_path), str(checkpoint_path), device="cpu")
    assert adapter._load_model() is not None

    assert observed["env"] == "1"
    assert observed["args"] == (str(config_path), str(checkpoint_path), "cpu")
    assert observed["registered"] is True
    assert safe_globals_calls
    assert numpy.ndarray in safe_globals_calls[0]
    assert numpy.core.multiarray._reconstruct in safe_globals_calls[0]
    assert "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD" not in os.environ


def test_model_loading_preserves_existing_compatibility_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "rtmpose.py"
    checkpoint_path = tmp_path / "rtmpose.pth"
    config_path.write_text("# test config\n", encoding="utf-8")
    checkpoint_path.write_bytes(b"test checkpoint")

    mmpose_module = ModuleType("mmpose")
    mmpose_apis_module = ModuleType("mmpose.apis")
    mmpose_utils_module = ModuleType("mmpose.utils")
    mmpose_apis_module.init_model = lambda config, checkpoint, *, device: object()
    mmpose_utils_module.register_all_modules = lambda: None
    mmpose_module.apis = mmpose_apis_module
    mmpose_module.utils = mmpose_utils_module
    monkeypatch.setitem(sys.modules, "mmpose", mmpose_module)
    monkeypatch.setitem(sys.modules, "mmpose.apis", mmpose_apis_module)
    monkeypatch.setitem(sys.modules, "mmpose.utils", mmpose_utils_module)
    monkeypatch.setenv("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "0")

    adapter = RTMPose26Adapter(str(config_path), str(checkpoint_path))
    adapter._load_model()

    assert os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] == "0"
