"""Fused Artifact 与 Diagnostics —— 序列化、读写、诊断统计。"""

from __future__ import annotations

import pytest

from app.vision.multiview.artifact import (
    build_fused_artifact,
    build_fusion_diagnostics,
    normalize_fusion_diagnostics,
    load_fused_artifact,
    serialize_fused_sample,
    write_fused_artifact,
    write_fusion_diagnostics,
)
from app.vision.multiview.association import PlayerAssociation
from app.vision.multiview.fusion import FusionMeasurement
from app.vision.multiview.joint_artifact import FusedSample, write_fused_v2


def _measurement(
    gid="g1",
    t=0.0,
    take_ms=0.0,
    frame=0,
    x=5.0,
    y=8.0,
    status="dual_observed",
    source="dual",
    eligible=True,
    ref_detail=None,
    sec_detail=None,
):
    return FusionMeasurement(
        global_player_id=gid,
        timestamp_seconds=t,
        take_timestamp_ms=take_ms,
        reference_frame_index=frame,
        x_ft=x,
        y_ft=y,
        fusion_status=status,
        fusion_confidence=0.9,
        contributing_views=("reference", "secondary"),
        selected_view=None if status == "dual_observed" else "reference",
        view_observations={
            "reference": ref_detail
            or {
                "view_id": "cam_1",
                "view_status": "available",
                "source_frame_index": frame,
                "source_timestamp_ms": take_ms,
                "mapped_take_timestamp_ms": take_ms,
                "selection_error_ms": 0.0,
                "x_ft": x,
                "y_ft": y,
                "quality": 0.8,
            },
            **(
                {}
                if sec_detail is None
                else {
                    "secondary": sec_detail
                }
            ),
        },
        association_confidence=0.9,
        sync_quality="good",
        court_frame_version="canonical_court_frame.v1",
        measurement_source=source,
        metric_eligible=eligible,
    )


def test_serialize_fused_sample_has_all_contract_fields():
    sample = serialize_fused_sample(_measurement())
    for key in (
        "global_player_id",
        "timestamp_seconds",
        "take_timestamp_ms",
        "reference_frame_index",
        "x_ft",
        "y_ft",
        "fusion_status",
        "fusion_confidence",
        "contributing_views",
        "selected_view",
        "view_observations",
        "association_confidence",
        "sync_quality",
        "court_frame_version",
        "measurement_source",
        "metric_eligible",
    ):
        assert key in sample


def test_view_observations_traceable_composition():
    m = _measurement(
        frame=10,
        take_ms=1000.0,
        sec_detail={
            "view_id": "cam_2",
            "view_status": "available",
            "source_frame_index": 10,
            "source_timestamp_ms": 1500.0,
            "mapped_take_timestamp_ms": 1000.0,
            "selection_error_ms": 3.0,
            "x_ft": 5.2,
            "y_ft": 8.1,
            "quality": 0.7,
        },
    )
    sec = serialize_fused_sample(m)["view_observations"]["secondary"]
    assert sec["source_frame_index"] == 10
    assert sec["source_timestamp_ms"] == 1500.0
    assert sec["mapped_take_timestamp_ms"] == 1000.0
    assert sec["selection_error_ms"] == 3.0


def test_authoritative_v2_requires_timing_provenance_fields():
    detail = {
        "source_frame_index": 1,
        "source_timestamp_ms": 100.0,
        "mapped_take_timestamp_ms": 99.0,
        "selection_error_ms": 1.0,
        "timing_authority": "source_pts",
        "sync_quality": "good",
    }
    artifact = write_fused_v2(
        run_id="mvr-authoritative",
        capture_take_id="take",
        reference_view_id="cam_1",
        authoritative_run=True,
        samples=[
            FusedSample(
                global_player_id="g1",
                take_timestamp_ms=99.0,
                reference_frame_index=1,
                x_ft=1.0,
                y_ft=2.0,
                fusion_status="dual_observed",
                metric_eligible=True,
                view_observations={"cam_1": detail, "cam_2": detail},
            )
        ],
    )
    assert artifact["authoritative_run"] is True

    with pytest.raises(ValueError, match="missing timing fields"):
        write_fused_v2(
            run_id="mvr-invalid",
            capture_take_id="take",
            reference_view_id="cam_1",
            authoritative_run=True,
            samples=[
                FusedSample(
                    global_player_id="g1",
                    take_timestamp_ms=0.0,
                    reference_frame_index=0,
                    x_ft=1.0,
                    y_ft=2.0,
                    fusion_status="dual_observed",
                    metric_eligible=True,
                    view_observations={"cam_1": {}},
                )
            ],
        )


def test_build_fused_artifact_sorted_and_players():
    ms = [
        _measurement(gid="g1", t=2 / 30.0, take_ms=66.7, frame=2),
        _measurement(gid="g1", t=0.0, take_ms=0.0, frame=0),
        _measurement(gid="g2", t=1 / 30.0, take_ms=33.3, frame=1),
    ]
    artifact = build_fused_artifact(
        ms,
        run_id="mvf_1",
        capture_take_id="take_1",
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        sync_quality="good",
        court_frame_version="canonical_court_frame.v1",
    )
    assert artifact["schema_version"] == "fused_player_trajectory.v1"
    assert artifact["players"] == ["g1", "g2"]
    timestamps = [s["take_timestamp_ms"] for s in artifact["samples"]]
    assert timestamps == sorted(timestamps)


def test_write_and_load_round_trip(tmp_path):
    artifact = build_fused_artifact(
        [_measurement()],
        run_id="mvf_1",
        capture_take_id="take_1",
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        sync_quality="good",
        court_frame_version="canonical_court_frame.v1",
    )
    path = write_fused_artifact(tmp_path, artifact)
    loaded = load_fused_artifact(path)
    assert loaded is not None
    assert loaded["schema_version"] == "fused_player_trajectory.v1"
    assert loaded["samples"][0]["measurement_source"] == "dual"
    assert loaded["samples"][0]["metric_eligible"] is True


def test_load_missing_returns_none(tmp_path):
    assert load_fused_artifact(tmp_path / "missing.json") is None


def test_build_fusion_diagnostics_counts_and_disagreement():
    measurements = [
        _measurement(
            gid="g1",
            status="dual_observed",
            source="dual",
            eligible=True,
            sec_detail={
                "view_id": "cam_2",
                "view_status": "available",
                "source_frame_index": 0,
                "source_timestamp_ms": 3.0,
                "mapped_take_timestamp_ms": 0.0,
                "selection_error_ms": 3.0,
                "x_ft": 5.2,
                "y_ft": 8.1,
                "quality": 0.7,
            },
        ),
        _measurement(
            gid="g1",
            t=1 / 30.0,
            take_ms=33.3,
            frame=1,
            status="single_view_fallback",
            source="reference",
            eligible=True,
        ),
        _measurement(
            gid="g1",
            t=2 / 30.0,
            take_ms=66.7,
            frame=2,
            status="conflict",
            source="reference",
            eligible=True,
            sec_detail={
                "view_id": "cam_2",
                "view_status": "available",
                "source_frame_index": 2,
                "source_timestamp_ms": 70.0,
                "mapped_take_timestamp_ms": 66.7,
                "selection_error_ms": 50.0,
                "x_ft": 15.0,
                "y_ft": 35.0,
                "quality": 0.4,
            },
        ),
    ]
    diagnostics = build_fusion_diagnostics(
        measurements,
        run_id="mvf_1",
        global_players=[PlayerAssociation("g1", "A", "X")],
        orientations={"cam_1": "mirror_y", "cam_2": "mirror_x"},
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
    )
    assert diagnostics["schema_version"] == "fused_diagnostics.v1"
    assert diagnostics["fusion_status_counts"]["dual_observed"] == 1
    assert diagnostics["fusion_status_counts"]["single_view_fallback"] == 1
    assert diagnostics["fusion_status_counts"]["conflict"] == 1
    assert diagnostics["metric_eligible_count"] == 3
    assert diagnostics["orientation_normalization"]["reference"] == "mirror_y"
    assert diagnostics["orientation_normalization"]["secondary"] == "mirror_x"
    assert diagnostics["association_decisions"][0]["secondary_view_player_id"] == "X"
    # 冲突样本的 inter-view 距离应较大。
    assert diagnostics["view_disagreement"]["dual_samples"] == 2
    assert diagnostics["frame_mapping_errors"]["secondary_count"] == 2
    assert diagnostics["frame_mapping_errors"]["secondary_max_error_ms"] == 50.0


def test_write_fusion_diagnostics(tmp_path):
    diagnostics = build_fusion_diagnostics(
        [_measurement()],
        run_id="mvf_1",
        global_players=[],
        orientations={},
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
    )
    path = write_fusion_diagnostics(tmp_path, diagnostics)
    assert path.name == "fused_diagnostics.json"
    assert path.exists()


def test_normalize_joint_v2_diagnostics_publishes_fusion_quality_fields():
    artifact = {
        "schema_version": "fused_player_trajectory.v2",
        "samples": [
            {
                "fusion_status": "dual_observed",
                "metric_eligible": True,
                "view_observations": {
                    "cam_1": {"x_ft": 1.0, "y_ft": 2.0},
                    "cam_2": {"x_ft": 2.0, "y_ft": 2.0},
                },
            },
            {"fusion_status": "single_view_fallback", "metric_eligible": True, "view_observations": {}},
        ],
    }

    diagnostics = normalize_fusion_diagnostics(
        artifact,
        {"schema_version": "fused_player_trajectory.v2", "effective_multiview_ratio": 0.5},
    )

    assert diagnostics["schema_version"] == "fused_diagnostics.v1"
    assert diagnostics["fusion_status_counts"] == {"dual_observed": 1, "single_view_fallback": 1}
    assert diagnostics["sample_count"] == 2
    assert diagnostics["metric_eligible_count"] == 2
    assert diagnostics["view_disagreement"]["dual_samples"] == 1
    assert diagnostics["view_disagreement"]["median_distance_ft"] == 1.0
