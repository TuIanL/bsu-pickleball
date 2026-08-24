"""把逐飞行段 3D、稀疏 stereo 与单摄证据组装为统一混合段。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

import numpy as np

from app.vision.multiview.ball_stereo.segment_reconstruction import (
    FULL_ESTIMATED_3D,
    PARTIAL_3D,
    Reconstructed3DSegment,
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
    reconstructed_2_5d = EventAnchoredTrajectoryReconstructor(ReconstructionConfig()).reconstruct(
        flight,
        primary_points,
        dict(events_by_id),
        homography,
    )
    trusted = [measurement for measurement in stereo_measurements if measurement.high_quality_anchor]
    valid_points = [primary_points[index] for index in flight.point_indices if primary_points[index].image_xy is not None]
    duration_sec = max(
        0.0,
        primary_points[flight.end_index].timestamp_sec - primary_points[flight.start_index].timestamp_sec,
    )

    if reconstructed_3d.status in {FULL_ESTIMATED_3D, PARTIAL_3D} and len(trusted) >= 2 and reconstructed_3d.samples:
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
        metric_validity = "approximate_multiview"
        display_level = "high" if reconstructed_3d.status == FULL_ESTIMATED_3D else "medium"
    elif len(trusted) >= 1 and len(valid_points) >= 4 and homography is not None:
        mode = HybridReconstructionMode.STEREO_ANCHORED_2_5D
        samples = _samples_2_5d(reconstructed_2_5d.samples, main_view.primary_view_id, primary_points)
        metric_validity = "visualization_only"
        display_level = "medium"
    elif (
        reconstructed_2_5d.reconstruction_mode != ReconstructionMode.IMAGE_ONLY.value
        and len(reconstructed_2_5d.samples) >= 4
    ):
        mode = HybridReconstructionMode.SINGLE_VIEW_EVENT_ANCHORED_2_5D
        samples = _samples_2_5d(reconstructed_2_5d.samples, main_view.primary_view_id, primary_points)
        metric_validity = "visualization_only"
        display_level = "medium"
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
    else:
        mode = HybridReconstructionMode.UNAVAILABLE
        samples = []
        metric_validity = "unavailable"
        display_level = "none"

    metric_eligibility = {
        "speed": mode == HybridReconstructionMode.STEREO_ESTIMATED_3D and reconstructed_3d.status == FULL_ESTIMATED_3D,
        "peak_height": mode == HybridReconstructionMode.STEREO_ESTIMATED_3D,
        "authoritative_landing": False,
        "reason": None if metric_validity == "approximate_multiview" else "visualization_only_estimate",
    }
    endpoint = _endpoint_payload(
        flight=flight,
        events_by_id=events_by_id,
        samples=samples,
        main_view=main_view,
        reconstructed_3d=reconstructed_3d,
        trusted_anchor_count=len(trusted),
    )
    return {
        **(base_3d_payload or {}),
        "segment_id": flight.segment_id,
        "reconstruction_mode": mode.value,
        "status": "available" if mode != HybridReconstructionMode.UNAVAILABLE else "unavailable",
        "display_level": display_level,
        "metric_validity": metric_validity,
        "metric_eligibility": metric_eligibility,
        "primary_view_id": main_view.primary_view_id,
        "secondary_view_id": main_view.secondary_view_id,
        "primary_view_reason": main_view.reason,
        "view_quality": {view_id: metric.to_dict() for view_id, metric in main_view.metrics_by_view.items()},
        "stereo_anchor_count": len(trusted),
        "samples": samples,
        "image_paths_by_view": {
            view_id: _image_path(points, flight)
            for view_id, points in points_by_view.items()
        },
        "start_endpoint": _event_endpoint(
            flight.start_event_id,
            events_by_id,
            "start",
            flight.start_event_type.value if flight.start_event_type is not None else "unknown",
        ),
        "end_endpoint": endpoint,
        "quality": {
            **dict((base_3d_payload or {}).get("quality") or {}),
            "display_level": display_level,
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
            "validity": "visualization_only",
            "gap_length_frames": sample.gap_length_frames,
            "reprojection_error_px": sample.reprojection_error_px,
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
                "validity": "visualization_only",
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
