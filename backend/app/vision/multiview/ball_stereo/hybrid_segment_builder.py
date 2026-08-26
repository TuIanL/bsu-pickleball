"""把逐飞行段 3D、稀疏 stereo 与单摄证据组装为统一混合段。"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Mapping

import numpy as np

from app.vision.multiview.ball_stereo.segment_reconstruction import (
    FULL_ESTIMATED_3D,
    PARTIAL_3D,
    Reconstructed3DSegment,
    validate_height_profile,
)
from app.vision.multiview.ball_stereo.segment_view_selection import MainViewSelection
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement
from app.vision.pickleball_game_analysis.ball_environment_classifier import (
    BallEnvironmentClassifier,
    EndpointEvidence,
)
from app.vision.pickleball_game_analysis.event_anchored_trajectory_reconstructor import (
    EventAnchoredTrajectoryReconstructor,
)
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    FlightSegment,
    HybridReconstructionMode,
    ReconstructionConfig,
    ReconstructionMode,
    HeightSource,
    HeightValidity,
    TrajectoryEvent,
)
from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint


def build_hybrid_segment(
    *,
    flight: FlightSegment,
    points_by_view: Mapping[str, list[TrajectoryPoint]],
    events_by_id: Mapping[str, TrajectoryEvent],
    main_view: MainViewSelection,
    projections: Mapping[str, Any],
    reconstructed_3d: Reconstructed3DSegment,
    stereo_measurements: list[BallStereoMeasurement],
    base_3d_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    primary_points = points_by_view[main_view.primary_view_id]
    homography = _ground_image_to_court_homography(projections.get(main_view.primary_view_id))
    trusted = [measurement for measurement in stereo_measurements if measurement.high_quality_anchor]
    metric_anchors = [
        measurement
        for measurement in trusted
        if measurement.metric_validity == "metric_multiview"
    ]
    approximate_anchors = [
        measurement
        for measurement in stereo_measurements
        if measurement.metric_validity == "approximate_multiview"
        and measurement.depth_valid
        and measurement not in metric_anchors
    ]
    reconstruction_anchors = metric_anchors or approximate_anchors
    config = ReconstructionConfig()
    events_with_height_evidence = _augment_contact_height_evidence(events_by_id, trusted, config)
    reconstructed_2_5d = EventAnchoredTrajectoryReconstructor(config).reconstruct(
        flight,
        primary_points,
        events_with_height_evidence,
        homography,
    )
    valid_points = [primary_points[index] for index in flight.point_indices if primary_points[index].image_xy is not None]
    duration_sec = max(
        0.0,
        primary_points[flight.end_index].timestamp_sec - primary_points[flight.start_index].timestamp_sec,
    )

    qualified_3d, height_quality_reason = _qualified_3d(
        reconstructed_3d,
        base_3d_payload,
        bounce_end=flight.end_event_type is not None and flight.end_event_type.value == "bounce",
    )
    if qualified_3d and len(reconstruction_anchors) >= 2:
        mode = HybridReconstructionMode.STEREO_ESTIMATED_3D
        samples = [
            {
                **sample,
                "source_view_id": "dual_view",
                "source_view_ids": [main_view.primary_view_id, main_view.secondary_view_id],
                "provenance": "stereo_anchor_constrained",
                "validity": "approximate_multiview",
            }
            for sample in list((base_3d_payload or {}).get("samples") or [])
        ]
        metric_validity = "metric_multiview" if len(metric_anchors) >= 2 else "approximate_multiview"
        display_level = "high" if reconstructed_3d.status == FULL_ESTIMATED_3D else "medium"
        height_validity = HeightValidity.VALID.value
    elif len(reconstruction_anchors) >= 1 and len(valid_points) >= 4 and homography is not None:
        mode = HybridReconstructionMode.STEREO_ANCHORED_2_5D
        samples = _samples_2_5d(reconstructed_2_5d.samples, main_view.primary_view_id, primary_points)
        metric_validity = "visualization_only"
        display_level = "medium"
        height_validity = HeightValidity.UNKNOWN_OPEN_END.value if height_quality_reason else HeightValidity.VALID.value
    elif (
        reconstructed_2_5d.reconstruction_mode != ReconstructionMode.IMAGE_ONLY.value
        and len(reconstructed_2_5d.samples) >= 4
    ):
        mode = HybridReconstructionMode.SINGLE_VIEW_EVENT_ANCHORED_2_5D
        samples = _samples_2_5d(reconstructed_2_5d.samples, main_view.primary_view_id, primary_points)
        metric_validity = "visualization_only"
        display_level = "medium"
        height_validity = HeightValidity.UNKNOWN_OPEN_END.value if height_quality_reason else HeightValidity.VALID.value
    elif len(valid_points) >= 4 and duration_sec >= 0.08:
        mode = HybridReconstructionMode.SINGLE_VIEW_VISUAL_ARC
        samples = _visual_arc_samples(
            flight=flight,
            points=primary_points,
            homography=homography,
            source_view_id=main_view.primary_view_id,
        )
        metric_validity = "visualization_only"
        display_level = "low"
        height_validity = HeightValidity.UNKNOWN_OPEN_END.value
    else:
        mode = HybridReconstructionMode.UNAVAILABLE
        samples = []
        metric_validity = "unavailable"
        display_level = "none"
        height_validity = HeightValidity.UNKNOWN.value

    sample_sources = [str(sample.get("source") or "") for sample in samples]
    observed_count = sum(source in {"detected", "anchor"} for source in sample_sources)
    interpolated_count = sum(source == "interpolated" for source in sample_sources)
    predicted_count = sum(source in {"model_predicted", "predicted"} for source in sample_sources)
    sample_count = len(sample_sources)
    observed_ratio = observed_count / sample_count if sample_count else 0.0
    predicted_ratio = (interpolated_count + predicted_count) / sample_count if sample_count else 1.0
    stereo_coverage = float(getattr(reconstructed_3d, "stereo_coverage", 0.0) or 0.0)
    display_eligible = bool(
        display_level in {"high", "medium"}
        and (
            (mode == HybridReconstructionMode.STEREO_ESTIMATED_3D and stereo_coverage >= 0.35)
            or (mode != HybridReconstructionMode.STEREO_ESTIMATED_3D and observed_ratio >= 0.45 and predicted_ratio <= 0.55)
        )
    )
    quality_gate_summary = {
        "schema_version": "ball_quality_gates.v1",
        "observed_count": observed_count,
        "observed_ratio": round(observed_ratio, 4),
        "interpolated_count": interpolated_count,
        "predicted_count": predicted_count,
        "predicted_ratio": round(predicted_ratio, 4),
        "stereo_coverage": round(stereo_coverage, 4),
        "display_eligible_reason": "passed_segment_quality_gates" if display_eligible else "insufficient_observed_coverage_or_low_display_level",
    }

    metric_eligibility = {
        "speed": (
            mode == HybridReconstructionMode.STEREO_ESTIMATED_3D
            and metric_validity == "metric_multiview"
            and reconstructed_3d.status == FULL_ESTIMATED_3D
        ),
        "peak_height": mode == HybridReconstructionMode.STEREO_ESTIMATED_3D and metric_validity == "metric_multiview",
        "authoritative_landing": False,
        "reason": (
            None
            if metric_validity == "metric_multiview"
            else "approximate_multiview_not_metric_eligible"
            if metric_validity == "approximate_multiview"
            else "visualization_only_estimate"
        ),
    }
    endpoint = _endpoint_payload(
        flight=flight,
        events_by_id=events_with_height_evidence,
        samples=samples,
        main_view=main_view,
        reconstructed_3d=reconstructed_3d,
        trusted_anchor_count=len(reconstruction_anchors),
    )
    return {
        **(base_3d_payload or {}),
        "segment_id": flight.segment_id,
        "reconstruction_mode": mode.value,
        "status": "available" if mode != HybridReconstructionMode.UNAVAILABLE else "unavailable",
        "display_level": display_level,
        "display_eligible": display_eligible,
        "quality_gate_summary": quality_gate_summary,
        "metric_validity": metric_validity,
        "metric_eligibility": metric_eligibility,
        "height_validity": height_validity,
        "height_quality_reason": height_quality_reason,
        "primary_view_id": main_view.primary_view_id,
        "secondary_view_id": main_view.secondary_view_id,
        "primary_view_reason": main_view.reason,
        "view_quality": {view_id: metric.to_dict() for view_id, metric in main_view.metrics_by_view.items()},
        "stereo_anchor_count": len(reconstruction_anchors),
        "high_quality_stereo_anchor_count": len(metric_anchors),
        "samples": samples,
        "image_paths_by_view": {
            view_id: _image_path(points, flight)
            for view_id, points in points_by_view.items()
        },
        "start_endpoint": _event_endpoint(
            flight.start_event_id,
            events_with_height_evidence,
            "start",
            flight.start_event_type.value if flight.start_event_type is not None else "unknown",
        ),
        "end_endpoint": endpoint,
        "quality": {
            **dict((base_3d_payload or {}).get("quality") or {}),
            "display_level": display_level,
            "display_eligible": display_eligible,
            "observation_coverage": round(observed_ratio, 4),
            "predicted_ratio": round(predicted_ratio, 4),
            "metric_validity": metric_validity,
            "primary_view_score": main_view.metrics_by_view[main_view.primary_view_id].score(),
        },
    }


def _ground_image_to_court_homography(projection: Any) -> list[list[float]] | None:
    if projection is None:
        return None
    matrix = np.asarray(projection, dtype=np.float64)
    if matrix.shape != (3, 4) or not np.isfinite(matrix).all():
        return None
    ground_projection = matrix[:, [0, 1, 3]]
    try:
        inverse = np.linalg.inv(ground_projection)
    except np.linalg.LinAlgError:
        return None
    return inverse.tolist()


def _augment_contact_height_evidence(
    events_by_id: Mapping[str, TrajectoryEvent],
    trusted_measurements: list[BallStereoMeasurement],
    config: ReconstructionConfig,
) -> dict[str, TrajectoryEvent]:
    """把时间上可对齐的合格双摄高度作为逐事件证据注入 2.5D。"""
    if not trusted_measurements:
        return dict(events_by_id)
    output: dict[str, TrajectoryEvent] = {}
    measurements = [
        measurement
        for measurement in trusted_measurements
        if np.isfinite(float(measurement.estimated_z_ft)) and measurement.depth_valid
    ]
    for event_id, event in events_by_id.items():
        if event.height_ft is not None or event.event_type.value not in {"hit", "serve_reset"}:
            output[event_id] = event
            continue
        nearest = min(
            measurements,
            key=lambda measurement: abs(float(measurement.take_timestamp_ms) / 1000.0 - event.timestamp_sec),
            default=None,
        )
        if nearest is None or abs(float(nearest.take_timestamp_ms) / 1000.0 - event.timestamp_sec) > 0.15:
            output[event_id] = event
            continue
        confidence = max(0.0, min(1.0, float(nearest.confidence)))
        uncertainty = max(0.15, (1.0 - confidence) * (config.contact_height_max_ft - config.contact_height_min_ft))
        output[event_id] = replace(
            event,
            height_ft=float(nearest.estimated_z_ft),
            height_source=HeightSource.STEREO_EVENT_ESTIMATE.value,
            height_confidence=confidence,
            height_uncertainty_ft=uncertainty,
        )
    return output


def _qualified_3d(
    reconstructed_3d: Reconstructed3DSegment,
    base_3d_payload: dict[str, Any] | None,
    *,
    bounce_end: bool = False,
) -> tuple[bool, str | None]:
    """3D 发布前同时检查内部采样与序列化采样，失败时必须回退同段 2.5D。"""
    if reconstructed_3d.status not in {FULL_ESTIMATED_3D, PARTIAL_3D} or not reconstructed_3d.samples:
        return False, reconstructed_3d.height_quality_reason
    heights = np.asarray([sample.z_ft for sample in reconstructed_3d.samples], dtype=float)
    if not np.isfinite(heights).all():
        return False, "non_finite_height"
    profile_ok, profile_reason = validate_height_profile(reconstructed_3d.samples, bounce_end=bounce_end)
    if not profile_ok:
        return False, profile_reason
    for raw in list((base_3d_payload or {}).get("samples") or []):
        if not isinstance(raw, dict):
            return False, "invalid_3d_sample_payload"
        value = raw.get("estimated_height_ft", raw.get("z_ft"))
        if value is None:
            continue
        try:
            height = float(value)
        except (TypeError, ValueError):
            return False, "non_finite_height"
        if not np.isfinite(height):
            return False, "non_finite_height"
        if height < -1e-4:
            return False, "below_ground"
    base_samples = list((base_3d_payload or {}).get("samples") or [])
    if bounce_end and base_samples:
        last_height = base_samples[-1].get("estimated_height_ft", base_samples[-1].get("z_ft"))
        if last_height is not None and abs(float(last_height)) > 1e-3:
            return False, "bounce_endpoint_not_grounded"
    return True, None


def _samples_2_5d(samples, source_view_id: str, points: list[TrajectoryPoint]) -> list[dict[str, Any]]:
    points_by_frame = {point.frame_index: point for point in points}
    return [
        {
            "frame_index": sample.frame_index,
            "timestamp_sec": sample.timestamp_sec,
            "court_xy": list(sample.court_xy) if sample.court_xy is not None else None,
            "image_xy": (
                list(points_by_frame[sample.frame_index].image_xy)
                if sample.frame_index in points_by_frame and points_by_frame[sample.frame_index].image_xy is not None
                else None
            ),
            "estimated_height_ft": sample.estimated_height_ft,
            "source": sample.source,
            "provenance": sample.source,
            "source_view_id": source_view_id,
            "confidence": sample.confidence,
            "height_confidence": sample.height_confidence,
            "height_source": sample.height_source,
            "height_uncertainty_ft": sample.height_uncertainty_ft,
            "height_validity": sample.height_validity,
            "validity": "visualization_only",
            "gap_length_frames": sample.gap_length_frames,
            "reprojection_error_px": sample.reprojection_error_px,
            "gap_length_seconds": (
                points_by_frame[sample.frame_index].diagnostics.get("interpolation_gap_seconds")
                if sample.frame_index in points_by_frame
                else None
            ),
            "gap_boundary_reason": (
                points_by_frame[sample.frame_index].diagnostics.get("gap_boundary_reason")
                if sample.frame_index in points_by_frame
                else None
            ),
            "display_break": bool(
                points_by_frame[sample.frame_index].diagnostics.get("gap_boundary_reason")
                if sample.frame_index in points_by_frame
                else False
            ),
        }
        for sample in samples
    ]


def _image_path(points: list[TrajectoryPoint], flight: FlightSegment) -> list[dict[str, Any]]:
    return [
        {
            "frame_index": points[index].frame_index,
            "timestamp_sec": points[index].timestamp_sec,
            "image_xy": list(points[index].image_xy) if points[index].image_xy is not None else None,
            "source": points[index].source,
            "provenance": (
                "predicted"
                if points[index].source == "predicted"
                else "interpolated" if points[index].interpolated else "detected"
            ),
            "confidence": points[index].confidence,
            "validity": "visualization_only",
            "gap_length_seconds": points[index].diagnostics.get("interpolation_gap_seconds"),
            "gap_boundary_reason": points[index].diagnostics.get("gap_boundary_reason"),
            "display_break": bool(points[index].diagnostics.get("gap_boundary_reason")),
        }
        for index in flight.point_indices
    ]


def _visual_arc_samples(
    *,
    flight: FlightSegment,
    points: list[TrajectoryPoint],
    homography: list[list[float]] | None,
    source_view_id: str,
) -> list[dict[str, Any]]:
    indices = flight.point_indices
    output: list[dict[str, Any]] = []
    for order, index in enumerate(indices):
        point = points[index]
        progress = order / max(1, len(indices) - 1)
        court_xy = None
        if point.image_xy is not None and homography is not None:
            h = np.asarray(homography) @ np.asarray([point.image_xy[0], point.image_xy[1], 1.0])
            if abs(float(h[2])) > 1e-9:
                court_xy = [round(float(h[0] / h[2]), 4), round(float(h[1] / h[2]), 4)]
        height = round(1.0 + 5.0 * 4.0 * progress * (1.0 - progress), 3)
        confidence = round(min(progress / 0.2, (1.0 - progress) / 0.2, 1.0), 3)
        output.append(
            {
                "frame_index": point.frame_index,
                "timestamp_sec": point.timestamp_sec,
                "image_xy": list(point.image_xy) if point.image_xy is not None else None,
                "court_xy": court_xy,
                "estimated_height_ft": height,
                "source": "model_predicted" if point.image_xy is None else point.source,
                "provenance": "single_view_visual_fit",
                "source_view_id": source_view_id,
                "confidence": point.confidence,
                "height_confidence": confidence,
                "height_source": HeightSource.UNKNOWN_OPEN_END.value,
                "height_uncertainty_ft": None,
                "height_validity": HeightValidity.UNKNOWN_OPEN_END.value,
            "validity": "visualization_only",
            "gap_length_seconds": points[index].diagnostics.get("interpolation_gap_seconds"),
            "gap_boundary_reason": points[index].diagnostics.get("gap_boundary_reason"),
            "display_break": bool(points[index].diagnostics.get("gap_boundary_reason")),
        }
        )
    return output


def _event_endpoint(
    event_id: str | None,
    events_by_id: Mapping[str, TrajectoryEvent],
    position: str,
    fallback_event_type: str = "unknown",
) -> dict:
    event = events_by_id.get(event_id or "")
    return {
        "position": position,
        "event_id": event.event_id if event else None,
        "event_type": event.event_type.value if event else fallback_event_type,
        "timestamp_sec": event.timestamp_sec if event else None,
        "confidence": event.confidence if event else None,
        "court_xy": list(event.court_xy) if event and event.court_xy is not None else None,
    }


def _endpoint_payload(
    *,
    flight: FlightSegment,
    events_by_id: Mapping[str, TrajectoryEvent],
    samples: list[dict[str, Any]],
    main_view: MainViewSelection,
    reconstructed_3d: Reconstructed3DSegment,
    trusted_anchor_count: int,
) -> dict:
    payload = _event_endpoint(
        flight.end_event_id,
        events_by_id,
        "end",
        flight.end_event_type.value if flight.end_event_type is not None else "unknown",
    )
    court_xy = payload.get("court_xy") or next(
        (sample.get("court_xy") for sample in reversed(samples) if sample.get("court_xy") is not None),
        None,
    )
    if court_xy is None:
        payload.update({"court_location": "unknown", "outcome_classification": "calibration_uncertain"})
        return payload
    metric = main_view.metrics_by_view[main_view.primary_view_id]
    classification = BallEnvironmentClassifier().classify(
        (float(court_xy[0]), float(court_xy[1])),
        EndpointEvidence(
            continuity_score=metric.continuity,
            endpoint_time_consistent=payload["event_type"] in {"hit", "bounce", "serve_reset"},
            static_pattern=metric.static_false_positive_ratio > 0.25,
            reprojection_error_px=(
                reconstructed_3d.reprojection_error_px
                if np.isfinite(reconstructed_3d.reprojection_error_px)
                else None
            ),
            cross_view_supported=trusted_anchor_count > 0,
            calibration_uncertainty_ft=1.0,
        ),
    )
    payload.update(asdict(classification))
    payload["court_xy"] = court_xy
    payload["non_adjudication_notice"] = classification.non_adjudication_notice
    return payload
