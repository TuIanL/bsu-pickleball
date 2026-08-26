import json
from pathlib import Path

from app.vision.pickleball_game_analysis.ball_quality_gate import (
    BallQualityGateConfig,
    evaluate_candidate,
    evaluate_interpolation_gap,
    evaluate_motion,
)
from app.vision.pickleball_game_analysis.schemas import BallCandidate


FIXTURE_PATH = Path(__file__).parents[1] / "fixtures/ball_trajectory/ball_quality_gate_hard_negatives.v1.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_hard_negative_candidate_fixture_rejects_static_objects() -> None:
    fixture = _fixture()
    config = BallQualityGateConfig()
    for case in fixture["cases"]:
        if "candidate" not in case:
            continue
        candidate = BallCandidate(**case["candidate"])
        decision = evaluate_candidate(
            candidate,
            frame_shape=fixture["frame_shape"],
            roi_corners=tuple(tuple(point) for point in fixture["roi_corners"]),
            config=config,
            point_in_roi=case["point_in_roi"],
            projected_xy=case["projected_xy"],
        )
        assert decision.reason == case["expected_reason"], case["id"]
        assert not decision.accepted, case["id"]


def test_hard_negative_fixture_preserves_short_gap_and_breaks_long_gap() -> None:
    config = BallQualityGateConfig()
    for case in _fixture()["cases"]:
        if case.get("kind") != "occlusion":
            continue
        decision = evaluate_interpolation_gap(*case["timestamps_sec"][::2], config=config)
        assert decision.reason == case["expected"], case["id"]


def test_hard_negative_fixture_separates_high_speed_ball_from_false_jump() -> None:
    config = BallQualityGateConfig()
    for case in _fixture()["cases"]:
        if case.get("kind") not in {"high_speed_object", "high_speed_ball"}:
            continue
        decision = evaluate_motion(
            [(float(timestamp), tuple(point)) for timestamp, point in case["history"]],
            float(case["timestamp_sec"]),
            tuple(case["current_point"]),
            config=config,
        )
        assert decision.reason == case["expected"], case["id"]
