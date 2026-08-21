"""Artifact builder 测试：立体证据 v1 + 轨迹 v3 结构契约。"""

from __future__ import annotations

from app.vision.multiview.ball_stereo.artifact_builders import (
    build_stereo_evidence_v1,
    build_v3_trajectory,
)
from app.vision.multiview.ball_stereo.landing_authority import LandingPointResult
from app.vision.multiview.ball_stereo.metrics import BallMetrics
from app.vision.multiview.ball_stereo.segment_reconstruction import (
    FULL_ESTIMATED_3D,
    LANDING_ONLY,
    UNAVAILABLE,
    Reconstructed3DSample,
    Reconstructed3DSegment,
)
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement


def _meas() -> BallStereoMeasurement:
    return BallStereoMeasurement(
        take_timestamp_ms=100.0, cam1_timestamp_ms=100.0, cam2_timestamp_ms=103.0,
        cam1_image_xy=(10.0, 20.0), cam2_image_xy=(11.0, 21.0),
        estimated_x_ft=10.0, estimated_y_ft=22.0, estimated_z_ft=3.0,
        sync_error_ms=3.0, reprojection_error_cam1_px=1.0, reprojection_error_cam2_px=1.1,
        epipolar_residual_px=1.05, geometry_quality=0.9, confidence=0.9,
    )


def test_evidence_v1_immutable_shape():
    evidence = build_stereo_evidence_v1(take_id="take1", measurements=[_meas()], pairings=[{"a": 1}])
    assert evidence["schema_version"] == "multiview_ball_stereo_evidence.v1"
    assert evidence["take_id"] == "take1"
    assert evidence["measurements"][0]["source"] == "dual_view_estimated"
    assert evidence["measurements"][0]["estimated_z_ft"] == 3.0
    assert evidence["pairings"] == [{"a": 1}]


def test_v3_trajectory_shape_and_grading():
    seg = Reconstructed3DSegment(
        segment_id="seg1", status=FULL_ESTIMATED_3D,
        samples=[Reconstructed3DSample(0.0, 5.0, 10.0, 1.0), Reconstructed3DSample(1.0, 7.0, 30.0, 0.5)],
        reprojection_error_px=8.0, stereo_coverage=0.9, prediction_ratio=0.1,
    )
    metrics = BallMetrics(
        average_speed_kmh=42.0, average_speed_validity="estimated",
        peak_height_ft=4.0, net_height_ft=1.0, speed_eligibility_reason=None,
    )
    landing = LandingPointResult((11.3, 38.0), "dual_view_ground_fused", "high", 0.85)

    doc = build_v3_trajectory(
        job_id="job1", take_id="take1", bounce_source="reference_view_confirmed",
        segments=[seg], landing=landing, metrics_by_segment={"seg1": metrics},
        duration_by_segment={"seg1": 1.0},
    )
    assert doc["schema_version"] == "reconstructed_ball_trajectory.v3"
    assert doc["reconstruction_mode"] == "multiview_estimated_3d"
    assert doc["coordinate_semantics"]["z"] == "estimated_multiview_height_ft"
    assert doc["coordinate_semantics"]["validity"] == "approximate_multiview"
    assert doc["overall_status"] == FULL_ESTIMATED_3D
    assert doc["landing_point"]["landing_validity"] == "high"
    assert doc["landing_point"]["landing_source"] == "dual_view_ground_fused"
    assert doc["segments"][0]["stereo_coverage"] == 0.9
    assert doc["segments"][0]["metrics"]["average_speed_kmh"] == 42.0
    assert doc["segments"][0]["samples"][1]["estimated_height_ft"] == 0.5


def test_v3_overall_status_landing_only():
    seg = Reconstructed3DSegment(
        segment_id="seg1", status=UNAVAILABLE, samples=[], reprojection_error_px=float("inf"),
        stereo_coverage=0.0, prediction_ratio=1.0,
    )
    landing = LandingPointResult((10.0, 30.0), "single_view_ground", "high", 0.5)
    doc = build_v3_trajectory(
        job_id="job1", take_id="take1", bounce_source="reference_view_confirmed",
        segments=[seg], landing=landing, metrics_by_segment={}, duration_by_segment={"seg1": 1.0},
    )
    assert doc["overall_status"] == LANDING_ONLY