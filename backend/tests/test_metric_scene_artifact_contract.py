from __future__ import annotations

import numpy as np

from app.vision.multiview.ball_stereo.artifact_builders import build_stereo_evidence_v1, build_v3_trajectory
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement, measure_stereo
from app.vision.multiview.ball_stereo.segment_reconstruction import Reconstructed3DSample, Reconstructed3DSegment


def test_stereo_measurement_round_trips_metric_scene_provenance() -> None:
    projection_a = np.array([[500.0, 0.0, 320.0, 0.0], [0.0, 500.0, 240.0, 0.0], [0.0, 0.0, 1.0, 10.0]])
    projection_b = np.array([[500.0, 0.0, 320.0, -100.0], [0.0, 500.0, 240.0, 0.0], [0.0, 0.0, 1.0, 10.0]])
    measurement = measure_stereo(
        projection_cam1=projection_a,
        projection_cam2=projection_b,
        image_xy1=(320.0, 240.0),
        image_xy2=(315.0, 240.0),
        cam1_timestamp_ms=100.0,
        cam2_timestamp_ms=100.0,
        scene_calibration_revision=3,
        camera_model_source="net_refined_virtual",
        metric_validity="metric_multiview",
        height_uncertainty_ft=0.08,
        scene_quality={"status": "ready"},
    )

    restored = BallStereoMeasurement.from_dict(measurement.to_dict())
    assert restored.scene_calibration_revision == 3
    assert restored.camera_model_source == "net_refined_virtual"
    assert restored.metric_validity == "metric_multiview"
    assert restored.height_uncertainty_ft == 0.08
    assert restored.scene_quality == {"status": "ready"}

    old_payload = measurement.to_dict()
    for key in ("scene_calibration_revision", "camera_model_source", "metric_validity", "height_uncertainty_ft", "scene_quality"):
        old_payload.pop(key, None)
    old_restored = BallStereoMeasurement.from_dict(old_payload)
    assert old_restored.scene_calibration_revision is None
    assert old_restored.metric_validity == "approximate_multiview"


def test_v3_and_evidence_keep_metric_validity_and_revision() -> None:
    measurement = BallStereoMeasurement(
        take_timestamp_ms=0,
        cam1_timestamp_ms=0,
        cam2_timestamp_ms=0,
        cam1_image_xy=(1, 1),
        cam2_image_xy=(1, 1),
        estimated_x_ft=5,
        estimated_y_ft=22,
        estimated_z_ft=2,
        sync_error_ms=0,
        reprojection_error_cam1_px=1,
        reprojection_error_cam2_px=1,
        epipolar_residual_px=1,
        geometry_quality=0.9,
        confidence=0.95,
        scene_calibration_revision=4,
        camera_model_source="net_refined_virtual",
        metric_validity="metric_multiview",
    )
    evidence = build_stereo_evidence_v1(take_id="take-1", measurements=[measurement], pairings=[])
    trajectory = build_v3_trajectory(
        job_id="job-1",
        take_id="take-1",
        bounce_source="canonical_reference_view",
        segments=[],
        landing=None,
        metrics_by_segment={},
        duration_by_segment={},
        scene_calibration_revision=4,
        metric_validity="metric_multiview",
        height_uncertainty_ft=0.1,
    )

    assert evidence["measurements"][0]["scene_calibration_revision"] == 4
    assert trajectory["coordinate_semantics"]["validity"] == "metric_multiview"
    assert trajectory["coordinate_semantics"]["scene_calibration_revision"] == 4


def test_mixed_segment_height_semantics_are_not_collapsed() -> None:
    metric_segment = Reconstructed3DSegment(
        segment_id="metric",
        status="FULL_ESTIMATED_3D",
        samples=[Reconstructed3DSample(0.0, 5.0, 22.0, 2.8, height_source="metric_multiview", height_uncertainty_ft=0.08)],
        reprojection_error_px=1.5,
        stereo_coverage=1.0,
    )
    approximate_segment = Reconstructed3DSegment(
        segment_id="approximate",
        status="PARTIAL_3D",
        samples=[Reconstructed3DSample(0.0, 6.0, 22.0, 2.2, height_source="estimated", height_uncertainty_ft=None)],
        reprojection_error_px=6.0,
        stereo_coverage=0.4,
    )
    trajectory = build_v3_trajectory(
        job_id="job-mixed",
        take_id="take-1",
        bounce_source="canonical_reference_view",
        segments=[metric_segment, approximate_segment],
        landing=None,
        metrics_by_segment={},
        duration_by_segment={"metric": 1.0, "approximate": 1.0},
        metric_validity="metric_multiview",
    )

    payload_by_id = {segment["segment_id"]: segment for segment in trajectory["segments"]}
    assert payload_by_id["metric"]["samples"][0]["height_source"] == "metric_multiview"
    assert payload_by_id["metric"]["samples"][0]["height_uncertainty_ft"] == 0.08
    assert payload_by_id["approximate"]["samples"][0]["height_source"] == "estimated"
