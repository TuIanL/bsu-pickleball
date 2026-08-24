from __future__ import annotations

import json
from pathlib import Path

from app.vision.pickleball_game_analysis.ball_environment_classifier import (
    BallEnvironmentClassifier,
    EndpointEvidence,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "ball_trajectory" / "hybrid-regression-cases.json"


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
