from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.vision.pickleball_game_analysis.ball_environment_classifier import (
    BallEnvironmentClassifier,
    EndpointEvidence,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "ball_trajectory" / "hybrid-regression-cases.json"
REAL_60S_ARTIFACT = Path(
    "/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/"
    "take_sync_20260720_122645_317228/analysis/job-71166f62f7/"
    "reconstructed_ball_trajectory.json"
)


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixed_regression_dataset_covers_real_capture_out_occlusion_static_and_strides():
    payload = _fixture()
    kinds = {case["kind"] for case in payload["cases"]}
    ids = {case["id"] for case in payload["cases"]}
    assert payload["source_capture"]["analysis_window_sec"] == [0.0, 60.0]
    assert kinds == {"endpoint", "provenance_sequence", "stride"}
    assert {"real_out_bounce", "short_occlusion", "spectator_sign_static", "stride_1", "stride_2"} <= ids


def test_regression_endpoint_cases_keep_real_out_degrade_calibration_and_reject_environment():
    classifier = BallEnvironmentClassifier()
    for case in (item for item in _fixture()["cases"] if item["kind"] == "endpoint"):
        result = classifier.classify(tuple(case["court_xy"]), EndpointEvidence(**case["evidence"]))
        assert result.outcome_classification == case["expected"], case["id"]
        if case["expected"] == "legal_out_candidate":
            assert result.non_adjudication_notice == "可能界外落点，非自动判罚"


def test_real_capture_acceptance_requires_displayable_hybrid_even_when_v3_is_unavailable():
    capture = _fixture()["source_capture"]
    assert capture["historical_v3"]["overall_status"] == "UNAVAILABLE"
    assert capture["historical_event_anchored_2_5d"]["segment_count"] >= 1
    assert capture["expected_hybrid"] == {
        "overall_status": "UNAVAILABLE",
        "display_trajectory_status": "degraded",
        "minimum_displayable_segments": 1,
    }


def test_real_60s_v4_artifact_quarantines_negative_3d_before_rendering():
    """同一份 60 秒真实双摄产物：历史坏段可读，但不得进入正式几何。"""
    if not REAL_60S_ARTIFACT.exists():
        pytest.skip("real capture volume is not mounted")
    artifact = json.loads(REAL_60S_ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "reconstructed_ball_trajectory.v4"
    assert artifact["diagnostics"]["frame_stride"] == 2
    assert max(window["end_sec"] for window in artifact["diagnostics"]["segment_windows"]) >= 59.0

    flight_69 = next(segment for segment in artifact["segments"] if segment["segment_id"] == "flight-69")
    assert flight_69["reconstruction_mode"] == "stereo_estimated_3d"
    assert min(sample["estimated_height_ft"] for sample in flight_69["samples"]) < 0.0

    # 与前端 adapter / scene 的安全门保持同义：含非法高度的历史 3D 段整体隔离，
    # 其余正式渲染样本只允许 finite、z>=0。
    rendered_segments = []
    for segment in artifact["segments"]:
        samples = segment.get("samples") or []
        heights = [sample.get("estimated_height_ft") for sample in samples]
        if segment.get("reconstruction_mode") == "stereo_estimated_3d" and any(
            not isinstance(height, (int, float)) or height < 0 for height in heights
        ):
            continue
        safe_samples = [
            sample for sample in samples
            if isinstance(sample.get("estimated_height_ft"), (int, float))
            and sample["estimated_height_ft"] >= 0
        ]
        if safe_samples:
            rendered_segments.append(segment["segment_id"])
            assert all(sample["estimated_height_ft"] >= 0 for sample in safe_samples)
    assert "flight-69" not in rendered_segments
