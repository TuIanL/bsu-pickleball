"""混合球路 artifact schema、兼容性与不可变发布契约。"""

from __future__ import annotations

import json

import pytest

from app.services.multiview_result_composer import (
    SUPPORTED_RECONSTRUCTED_TRAJECTORY_SCHEMAS,
    _validate_ball_artifact_payloads,
    _write_immutable_ball_artifact,
)


class _Storage:
    def write_json_atomic(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def _v4_payload():
    return {
        "schema_version": "reconstructed_ball_trajectory.v4",
        "overall_status": "UNAVAILABLE",
        "display_trajectory_status": "degraded",
        "coordinate_semantics": {
            "xy": "canonical_court_ft",
            "z": "estimated_multiview_or_visualization_only_height_ft",
        },
        "segments": [
            {
                "segment_id": "flight-1",
                "reconstruction_mode": "single_view_visual_arc",
                "metric_validity": "visualization_only",
                "quality": {"overall": 0.5, "predicted_ratio": 0.1, "observation_coverage": 0.8},
                "samples": [
                    {
                        "frame_index": 10,
                        "timestamp_sec": 1.0,
                        "source_view_id": "cam_a",
                        "provenance": "detected",
                        "confidence": 0.8,
                        "validity": "visualization_only",
                    }
                ],
                "end_endpoint": {
                    "event_type": "bounce",
                    "court_location": "outside_line",
                    "outcome_classification": "legal_out_candidate",
                    "calibration_uncertainty_ft": 1.0,
                    "automatic_adjudication": False,
                },
            }
        ],
    }


def test_v4_hybrid_schema_and_metric_eligibility_validate():
    assert _validate_ball_artifact_payloads(_v4_payload(), None) is None


def test_unknown_hybrid_mode_is_rejected():
    payload = _v4_payload()
    payload["segments"][0]["reconstruction_mode"] = "magic_trajectory"
    assert "reconstruction_mode" in _validate_ball_artifact_payloads(payload, None)


def test_unified_slug_contract_supports_historical_v1_v2_v3_and_new_v4():
    assert SUPPORTED_RECONSTRUCTED_TRAJECTORY_SCHEMAS == {
        "reconstructed_ball_trajectory.v1",
        "reconstructed_ball_trajectory.v2",
        "reconstructed_ball_trajectory.v3",
        "reconstructed_ball_trajectory.v4",
    }


def test_job_scoped_artifact_write_is_idempotent_but_refuses_mutation(tmp_path):
    path = tmp_path / "job-new" / "reconstructed_ball_trajectory.json"
    storage = _Storage()
    payload = _v4_payload()
    _write_immutable_ball_artifact(storage, path, payload)
    first = path.read_text(encoding="utf-8")
    _write_immutable_ball_artifact(storage, path, payload)
    assert path.read_text(encoding="utf-8") == first

    changed = _v4_payload()
    changed["display_trajectory_status"] = "available"
    with pytest.raises(RuntimeError, match="拒绝覆盖"):
        _write_immutable_ball_artifact(storage, path, changed)
