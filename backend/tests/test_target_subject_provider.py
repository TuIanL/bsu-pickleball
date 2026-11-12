from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from jsonschema import ValidationError

from app.schemas.tracking import Detection
from app.vision.target_subject_provider.contracts import validate_contract
from app.vision.target_subject_provider.preflight import ProviderPreflightError, run_preflight
from app.vision.target_subject_provider.provider import (
    FrameEvidence,
    build_candidate_result,
    run_video_provider,
)


cv2 = pytest.importorskip("cv2")
CONTRACT_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "target_subject" / "v1"


def request_fixture() -> dict:
    payload = json.loads(
        (CONTRACT_ROOT / "fixtures" / "provider_request.example.json").read_text(encoding="utf-8")
    )
    payload["run_mode"] = "development"
    payload["video"].update(frame_count=5, width=100, height=100, fps=10.0)
    payload["configuration"].update(tracker_max_lost=0, candidate_merge_max_gap=2, candidate_merge_min_iou=0.1)
    return payload


def metadata() -> dict:
    return {
        "contract_version": "pb.target-candidate-provider.v1.0",
        "platform_commit": "1" * 40,
        "worktree_clean": False,
        "configuration_sha256": "2" * 64,
        "models": {"person_detector": "3" * 64},
        "runtime_versions": {"python": "test"},
    }


def person(box, confidence=0.9):
    return Detection(bbox=box, confidence=confidence)


def test_fragmented_tracklets_merge_and_occlusion_stays_explicit():
    request = request_fixture()
    frames = [
        FrameEvidence(0, 0.0, [person([10, 10, 30, 70])]),
        FrameEvidence(1, 0.1, []),
        FrameEvidence(2, 0.2, [person([11, 10, 31, 70])]),
        FrameEvidence(3, 0.3, []),
        FrameEvidence(4, 0.4, []),
    ]

    result = build_candidate_result(request, frames, provider_metadata=metadata())

    assert len(result["tracklets"]) == 2
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["tracklet_ids"] == ["tracklet_001", "tracklet_002"]
    assert [item["status"] for item in result["candidates"][0]["observations"]] == [
        "detected", "missing", "detected", "missing", "missing"
    ]
    validate_contract("provider_result", result)


def test_multiple_players_and_non_top_one_candidates_remain_reviewable():
    request = request_fixture()
    frames = [
        FrameEvidence(
            index,
            index / 10,
            [person([5 + index, 5, 25 + index, 80], 0.95), person([60, 20, 75, 65], 0.75)],
        )
        for index in range(5)
    ]

    result = build_candidate_result(request, frames, provider_metadata=metadata())

    assert len(result["candidates"]) == 2
    assert {candidate["rank"] for candidate in result["candidates"]} == {1, 2}
    assert all(len(candidate["observations"]) == 5 for candidate in result["candidates"])


def test_missing_and_error_frames_have_explicit_states():
    request = request_fixture()
    frames = [
        FrameEvidence(0, 0.0, [], status="missing"),
        FrameEvidence(1, 0.1, [], status="error", error_code="decode_failed"),
    ]

    result = build_candidate_result(request, frames, provider_metadata=metadata())

    assert [frame["status"] for frame in result["frames"]] == ["missing", "error"]
    assert result["errors"][0]["code"] == "decode_failed"
    assert result["candidates"] == []


def test_calibration_falls_back_without_fabricating_court_positions():
    request = request_fixture()
    request["calibration"].update(requested_mode="origin_calibration", homography=None)

    result = build_candidate_result(request, [], provider_metadata=metadata())

    assert result["calibration"]["mode"] == "fallback_image_space"
    assert result["calibration"]["status"] == "fallback"
    assert "court_position" not in json.dumps(result)


def test_candidate_output_is_deterministic_and_product_state_is_not_imported():
    request = request_fixture()
    frames = [FrameEvidence(0, 0.0, [person([50, 10, 70, 80]), person([5, 10, 25, 80])])]

    first = build_candidate_result(copy.deepcopy(request), frames, provider_metadata=metadata())
    second = build_candidate_result(copy.deepcopy(request), frames, provider_metadata=metadata())

    assert first == second
    assert "stroke_type" not in json.dumps(first)
    assert "nested_loso" not in json.dumps(first)


def test_contract_rejects_label_and_protocol_side_channels():
    for key in ("stroke_type", "profile", "nested_loso_role"):
        request = request_fixture()
        request[key] = "forbidden"
        with pytest.raises(Exception):
            build_candidate_result(request, [], provider_metadata=metadata())


def test_preflight_hashes_inputs_and_rejects_dirty_pilot(tmp_path):
    platform = tmp_path / "platform"
    platform.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=platform, check=True)
    (platform / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=platform, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "baseline"],
        cwd=platform,
        check=True,
    )
    video = tmp_path / "clip.mp4"
    model = tmp_path / "detector.pt"
    video.write_bytes(b"video")
    model.write_bytes(b"model")
    request = request_fixture()
    request["video"]["path"] = str(video)
    request["video"]["sha256"] = hashlib.sha256(b"video").hexdigest()
    request["configuration"]["detector_model_path"] = str(model)

    report = run_preflight(
        request,
        request_dir=tmp_path,
        output_path=tmp_path / "result.json",
        platform_root=platform,
    )
    assert report.worktree_clean is True
    assert report.model_sha256["person_detector"] == hashlib.sha256(b"model").hexdigest()

    request["run_mode"] = "pilot"
    (platform / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ProviderPreflightError, match="dirty"):
        run_preflight(
            request,
            request_dir=tmp_path,
            output_path=tmp_path / "pilot.json",
            platform_root=platform,
        )


def test_headless_video_provider_writes_atomic_contract_result(tmp_path):
    platform = tmp_path / "platform"
    platform.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=platform, check=True)
    (platform / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=platform, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "baseline"],
        cwd=platform,
        check=True,
    )
    video = tmp_path / "clip.mp4"
    _make_video(video, frame_count=3)
    model = tmp_path / "detector.pt"
    model.write_bytes(b"model")
    request = request_fixture()
    request["video"].update(
        path=str(video),
        sha256=_sha256(video),
        frame_count=3,
        width=64,
        height=48,
        fps=10.0,
    )
    request["configuration"]["detector_model_path"] = str(model)
    output = tmp_path / "result.json"

    result = run_video_provider(
        request,
        request_dir=tmp_path,
        output_path=output,
        detector=FakeDetector(),
        platform_root=platform,
    )

    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert not list(tmp_path.glob("*.incomplete"))


class FakeDetector:
    def detect_frame(self, frame, frame_index):
        return [person([5 + frame_index, 5, 25 + frame_index, 40])]


def _make_video(path: Path, frame_count: int):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    assert writer.isOpened()
    for value in range(frame_count):
        writer.write(np.full((48, 64, 3), 30 + value, dtype=np.uint8))
    writer.release()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def provider_case(tmp_path):
    platform = tmp_path / "platform"
    platform.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=platform, check=True)
    (platform / "tracked.txt").write_text("baseline\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=platform, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "baseline"],
        cwd=platform, check=True,
    )
    video = tmp_path / "clip.mp4"
    _make_video(video, frame_count=3)
    model = tmp_path / "detector.pt"
    model.write_bytes(b"fixture model; never loaded")
    request = request_fixture()
    request["video"].update(path=str(video), sha256=_sha256(video), frame_count=3, width=64, height=48, fps=10.0)
    request["configuration"]["detector_model_path"] = str(model)
    return request, dict(request_dir=tmp_path, output_path=tmp_path / "result.json", platform_root=platform)


@pytest.mark.parametrize("declared", [2, 5])
def test_video_range_mismatch_is_not_silently_truncated_or_padded(provider_case, declared):
    request, kwargs = provider_case
    request["video"]["frame_count"] = declared
    with pytest.raises(ProviderPreflightError, match="frame count mismatch"):
        run_video_provider(request, detector=FakeDetector(), **kwargs)
    assert not kwargs["output_path"].exists()
    assert not list(kwargs["request_dir"].glob("*.incomplete"))


@pytest.mark.parametrize("field,value,reason", [
    ("width", 128, "dimensions mismatch"),
    ("height", 96, "dimensions mismatch"),
    ("fps", 30.0, "frame rate mismatch"),
])
def test_video_metadata_mismatch_rejects_output(provider_case, field, value, reason):
    request, kwargs = provider_case
    request["video"][field] = value
    with pytest.raises(ProviderPreflightError, match=reason):
        run_video_provider(request, detector=FakeDetector(), **kwargs)
    assert not kwargs["output_path"].exists()


@pytest.mark.parametrize("fps", [0.0, float("nan"), float("inf")])
def test_unavailable_video_rate_does_not_fall_back_to_claimed_rate(provider_case, monkeypatch, fps):
    request, kwargs = provider_case
    capture = FakeCapture(fps=fps)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: capture)
    with pytest.raises(ProviderPreflightError, match="frame rate unavailable or invalid"):
        run_video_provider(request, detector=FakeDetector(), **kwargs)
    assert capture.released
    assert not kwargs["output_path"].exists()


def test_decoder_early_end_does_not_publish_a_partial_success(provider_case, monkeypatch):
    request, kwargs = provider_case
    capture = FakeCapture(frame_count=1)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: capture)
    with pytest.raises(ProviderPreflightError, match="declared 3, decoded 1"):
        run_video_provider(request, detector=FakeDetector(), **kwargs)
    assert capture.released
    assert not kwargs["output_path"].exists()


def test_existing_result_is_not_replaced(provider_case):
    request, kwargs = provider_case
    kwargs["output_path"].write_text("original result\n")
    with pytest.raises(ProviderPreflightError, match="output already exists"):
        run_video_provider(request, detector=FakeDetector(), **kwargs)
    assert kwargs["output_path"].read_text() == "original result\n"


@pytest.mark.parametrize("indices", [[-1], [5], [0, 0]])
def test_candidate_builder_rejects_invalid_source_frame_addresses(indices):
    frames = [FrameEvidence(i, 0.0, []) for i in indices]
    with pytest.raises(ValueError, match="source frame index"):
        build_candidate_result(request_fixture(), frames, provider_metadata=metadata())


def _algorithm_boundary_frames():
    return [FrameEvidence(0, 0.0, [person([0, 0, 10, 20])]), FrameEvidence(1, 0.1, [person([11, 0, 21, 20])])]


def test_default_tracker_ignores_process_environment(monkeypatch, provider_case):
    request, kwargs = provider_case
    observed = []
    hashes = []
    for algorithm in ("motion", "legacy", "invalid-process-setting"):
        monkeypatch.setenv("PICKLEBALL_TRACKER_ALGORITHM", algorithm)
        observed.append(build_candidate_result(request, _algorithm_boundary_frames(), provider_metadata=metadata()))
        hashes.append(run_preflight(request, **kwargs).configuration_sha256)
    assert observed[0] == observed[1] == observed[2]
    assert len(observed[0]["candidates"]) == 1
    assert len(set(hashes)) == 1
    explicit_default = copy.deepcopy(request)
    explicit_default["configuration"]["tracker_algorithm"] = "motion"
    assert run_preflight(explicit_default, **kwargs).configuration_sha256 == hashes[0]


def test_explicit_algorithm_is_executed_and_changes_effective_hash(provider_case):
    request, kwargs = provider_case
    results = []
    hashes = []
    for algorithm in ("motion", "legacy"):
        request["configuration"]["tracker_algorithm"] = algorithm
        results.append(build_candidate_result(request, _algorithm_boundary_frames(), provider_metadata=metadata()))
        hashes.append(run_preflight(request, **kwargs).configuration_sha256)
    assert [len(r["candidates"]) for r in results] == [1, 2]
    assert hashes[0] != hashes[1]
    request["configuration"]["tracker_algorithm"] = "unsupported"
    with pytest.raises(ValidationError):
        run_preflight(request, **kwargs)


def test_headless_provider_does_not_import_product_database_in_fresh_process(provider_case):
    request, kwargs = provider_case
    request_path = kwargs["request_dir"] / "request.json"
    request_path.write_text(json.dumps(request))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    code = """
import json, sys
from pathlib import Path
from app.schemas.tracking import Detection
from app.vision.target_subject_provider.provider import run_video_provider
assert 'app.database' not in sys.modules
class Detector:
    def detect_frame(self, frame, index):
        return [Detection(bbox=[5,5,25,40], confidence=0.9)]
run_video_provider(json.loads(Path(sys.argv[1]).read_text()), request_dir=Path(sys.argv[1]).parent,
                   output_path=Path(sys.argv[2]), platform_root=Path(sys.argv[3]), detector=Detector())
assert 'app.database' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(request_path), str(kwargs["output_path"]), str(kwargs["platform_root"])],
        cwd=kwargs["request_dir"], env=env, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert kwargs["output_path"].is_file()


class FakeCapture:
    def __init__(self, *, fps=10.0, frame_count=3):
        self.fps, self.remaining, self.released = fps, frame_count, False

    def isOpened(self):
        return True

    def get(self, key):
        return {cv2.CAP_PROP_FPS: self.fps, cv2.CAP_PROP_FRAME_WIDTH: 64, cv2.CAP_PROP_FRAME_HEIGHT: 48}.get(key, 3)

    def read(self):
        if self.remaining == 0:
            return False, None
        self.remaining -= 1
        return True, np.zeros((48, 64, 3), dtype=np.uint8)

    def release(self):
        self.released = True
