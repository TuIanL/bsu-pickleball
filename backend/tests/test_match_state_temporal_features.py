from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.build_match_state_aligned_features import build_take_records
from scripts.match_state_temporal_features import (
    BallFeatureState,
    PlayerFeatureState,
    derive_ball_features,
    derive_player_features,
    nearest_by_timestamp,
    rgb_frame_reference,
)
from scripts.match_state_timeline import decode_state_timeline, evaluate_rally_segments, evaluate_state_windows


def _frame(timestamp_ms: int, x_offset: float = 0.0) -> dict:
    people = []
    for track_id in range(1, 5):
        x = 0.1 * track_id + x_offset
        people.append(
            {
                "track_id": track_id,
                "bbox_xyxy_norm": [x - 0.02, 0.2, x + 0.02, 0.4],
                "det_confidence": 0.9,
                "keypoints_xy_norm": [[x, 0.25], [x, 0.35]],
                "keypoint_visible_mask": [1, 1],
            }
        )
    return {
        "take_timestamp_ms": timestamp_ms,
        "people": people,
        "ball_candidates": [{"center_xy_norm": [0.2 + x_offset, 0.3], "confidence": 0.8}],
        "quality": {
            "four_players_observed": True,
            "pose_usable": True,
            "pose_visible_ratio": 1.0,
            "structured_loss_mask": 1,
        },
    }


def test_player_features_include_motion_activity_and_formation_change():
    state = PlayerFeatureState()
    first = derive_player_features(_frame(0), state)
    second = derive_player_features(_frame(1000, 0.1), state)

    assert first["formation"]["player_count"] == 4
    assert second["players"][0]["speed_norm_per_s"] > 0
    assert second["players"][0]["acceleration_norm_per_s2"] > 0
    assert second["players"][0]["body_activity_intensity"] > 0
    assert second["formation"]["formation_change_speed"] == 0


def test_ball_candidates_are_associated_and_have_direction_and_stationary_state():
    state = BallFeatureState()
    first = derive_ball_features(_frame(0), state)
    second = derive_ball_features(_frame(1000, 0.1), state)
    assert first["observed"] is True
    assert second["track_id"] == first["track_id"]
    assert second["speed_norm_per_s"] > 0
    assert second["direction_rad"] is not None
    assert second["stationary"] is False
    assert second["candidate_track_ids"] == [first["track_id"]]


def test_timestamp_alignment_is_explicit_about_gap_and_rgb_quantization():
    records = [{"take_timestamp_ms": 0}, {"take_timestamp_ms": 83}, {"take_timestamp_ms": 167}]
    found, delta = nearest_by_timestamp(records, 90, 20)
    assert found == records[1]
    assert delta == -7
    missing, missing_delta = nearest_by_timestamp(records, 250, 20)
    assert missing is None
    assert missing_delta == -83
    reference = rgb_frame_reference({"frame_dir": "/remote/frames", "frame_count": 10, "duration_ms": 1000}, 90, 12)
    assert reference["frame_index"] == 2
    assert reference["frame_path"].endswith("/000002.jpg")


def test_dual_view_builder_emits_one_time_grid_and_explicit_view_masks():
    frame_one = [_frame(timestamp, timestamp / 10_000) for timestamp in range(0, 1001, 83)]
    views = {
        "cam_1": {
            "uri": "matchstate://take/cam_1",
            "structured": {
                "summary": {"last_timestamp_ms": 1000},
                    "frames": frame_one,
                "court": [{"timestamp_ms": 0, "polygons_xy_norm": []}],
            },
        },
        "cam_2": {
            "uri": "matchstate://take/cam_2",
            "structured": {
                "summary": {"last_timestamp_ms": 1000},
                    "frames": frame_one,
                "court": [{"timestamp_ms": 0, "polygons_xy_norm": []}],
            },
        },
    }
    rgb_entries = {
        "matchstate://take/cam_1": {
            "status": "complete",
            "frame_dir": "/remote/cam1",
            "frame_count": 13,
            "duration_ms": 1000,
            "identity": {"fps": 12},
        },
        "matchstate://take/cam_2": {
            "status": "complete",
            "frame_dir": "/remote/cam2",
            "frame_count": 13,
            "duration_ms": 1000,
            "identity": {"fps": 12},
        },
    }
    records, summary = build_take_records(
        take_id="ct_test",
        source_session_id="sync_test",
        views=views,
        rgb_entries=rgb_entries,
        fps=12,
        max_alignment_gap_ms=60,
    )
    assert len(records) == 13
    assert summary["dual_view_record_count"] == 13
    assert records[0]["views"]["cam_1"]["quality"]["rgb_available"] is True
    assert records[0]["views"]["cam_1"]["features"]["pose"]["players"][0]["track_id"] == 1


def test_decoder_applies_unknown_gate_hysteresis_and_minimum_duration():
    windows = [
        {"center_ms": 0, "state_probabilities": {"rally_active": 0.9, "non_play": 0.1}, "coverage": 1.0},
        {"center_ms": 500, "state_probabilities": {"rally_active": 0.58, "non_play": 0.42}, "coverage": 1.0},
        {"center_ms": 1000, "state_probabilities": {"rally_active": 0.4, "non_play": 0.6}, "coverage": 1.0},
        {"center_ms": 1500, "state_probabilities": {"rally_active": 0.8, "non_play": 0.2}, "coverage": 0.4},
    ]
    decoded = decode_state_timeline(
        windows, minimum_confidence=0.65, minimum_coverage=0.75, hysteresis=0.1, minimum_duration_ms=500
    )
    assert [item["state"] for item in decoded["windows"]] == ["rally_active", "rally_active", "non_play", "unknown"]
    assert len(decoded["segments"]) == 1
    assert decoded["segments"][0]["start_ms"] == 0
    assert decoded["segments"][0]["end_ms"] == 750


def test_timeline_metrics_report_iou_boundaries_misses_and_false_positives():
    ground_truth = [{"start_ms": 100, "end_ms": 1100}, {"start_ms": 2000, "end_ms": 2500}]
    predicted = [{"start_ms": 100, "end_ms": 1100}, {"start_ms": 5000, "end_ms": 5500}]
    rally = evaluate_rally_segments(predicted, ground_truth)
    assert rally["matched_count"] == 1
    assert rally["missed_count"] == 1
    assert rally["false_positive_count"] == 1
    assert rally["boundary_start_mae_ms"] == 0
    assert rally["mean_iou"] == 1
    windows = [
        {"center_ms": 500, "state": "rally_active"},
        {"center_ms": 1500, "state": "unknown"},
    ]
    state = evaluate_state_windows(windows, ground_truth)
    assert state["unknown_rate"] == 0.5
    assert state["confusion_matrix"][0][0] == 1


def test_rally_matching_rejects_incidental_low_iou_overlap():
    ground_truth = [{"start_ms": 1000, "end_ms": 2000}]
    predicted = [{"start_ms": 1900, "end_ms": 3000}]
    rally = evaluate_rally_segments(predicted, ground_truth)
    assert rally["matched_count"] == 0
    assert rally["missed_count"] == 1
    assert rally["false_positive_count"] == 1
