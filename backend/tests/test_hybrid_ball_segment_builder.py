"""混合 3D/2.5D/视觉弧段级降级测试。"""

from __future__ import annotations

import numpy as np

from app.vision.multiview.ball_stereo.hybrid_segment_builder import build_hybrid_segment
from app.vision.multiview.ball_stereo.segment_reconstruction import (
    FULL_ESTIMATED_3D,
    UNAVAILABLE,
    Reconstructed3DSample,
    Reconstructed3DSegment,
)
from app.vision.multiview.ball_stereo.segment_view_selection import (
    compute_view_segment_metrics,
    select_main_view,
)
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    FlightSegment,
    TrajectoryEvent,
    TrajectoryEventType,
)
from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint


PROJECTION = np.array(
    [[10.0, 0.0, 0.0, 0.0], [0.0, 10.0, 0.0, 0.0], [0.0, 0.0, 1.0, 1.0]],
    dtype=float,
)


def _points(view: str):
    return [
        TrajectoryPoint(
            frame_index=index,
            timestamp_sec=index / 30.0,
            image_xy=(20.0 + index * 2.0, 30.0 + index),
            court_xy=None,
            confidence=0.8,
            source="detector",
            diagnostics={"view_id": view},
        )
        for index in range(8)
    ]


def _flight(start_event_id="hit-0", end_event_id="bounce-7"):
    return FlightSegment(
        segment_id="flight-1",
        start_index=0,
        end_index=7,
        start_event_id=start_event_id,
        end_event_id=end_event_id,
        start_event_type=TrajectoryEventType.HIT if start_event_id else None,
        end_event_type=TrajectoryEventType.BOUNCE if end_event_id else None,
        boundary_reason="bounce" if end_event_id else "end_of_stream",
        point_indices=list(range(8)),
    )


def _events():
    return {
        "hit-0": TrajectoryEvent(
            "hit-0", TrajectoryEventType.HIT, 0, 0.0, image_xy=(20.0, 30.0), court_xy=(2.0, 3.0), confidence=0.8
        ),
        "bounce-7": TrajectoryEvent(
            "bounce-7", TrajectoryEventType.BOUNCE, 7, 7 / 30.0, image_xy=(34.0, 37.0), court_xy=(3.4, 3.7), confidence=0.9
        ),
    }


def _selection(points_by_view):
    metrics = {view: compute_view_segment_metrics(view, points) for view, points in points_by_view.items()}
    return select_main_view(metrics)


def _measurement(timestamp_ms: float, *, trusted: bool = True):
    return BallStereoMeasurement(
        take_timestamp_ms=timestamp_ms,
        cam1_timestamp_ms=timestamp_ms,
        cam2_timestamp_ms=timestamp_ms + 2.0,
        cam1_image_xy=(20.0, 30.0),
        cam2_image_xy=(21.0, 30.0),
        estimated_x_ft=2.0,
        estimated_y_ft=3.0,
        estimated_z_ft=2.5,
        sync_error_ms=2.0,
        reprojection_error_cam1_px=2.0,
        reprojection_error_cam2_px=2.0,
        epipolar_residual_px=2.0,
        geometry_quality=0.8,
        confidence=0.9,
        depth_valid=True,
        high_quality_anchor=trusted,
    )


def _build(*, flight=None, events=None, measurements=None, reconstructed_3d=None, base=None):
    points_by_view = {"cam_a": _points("cam_a"), "cam_b": _points("cam_b")}
    return build_hybrid_segment(
        flight=flight or _flight(),
        points_by_view=points_by_view,
        events_by_id=events if events is not None else _events(),
        main_view=_selection(points_by_view),
        projections={"cam_a": PROJECTION, "cam_b": PROJECTION},
        reconstructed_3d=reconstructed_3d or Reconstructed3DSegment("flight-1", UNAVAILABLE),
        stereo_measurements=measurements or [],
        base_3d_payload=base,
    )


def test_event_anchored_single_view_segment_is_delivered_with_endpoint_heights():
    segment = _build()
    assert segment["reconstruction_mode"] == "single_view_event_anchored_2_5d"
    assert segment["metric_validity"] == "visualization_only"
    assert segment["samples"][0]["estimated_height_ft"] > 0.0
    assert segment["samples"][-1]["estimated_height_ft"] == 0.0
    assert not segment["metric_eligibility"]["speed"]
    assert segment["samples"][0]["source_view_id"] in {"cam_a", "cam_b"}
    assert segment["samples"][0]["provenance"] in {"anchor", "detected", "interpolated", "model_predicted"}
    assert set(segment["image_paths_by_view"]) == {"cam_a", "cam_b"}
    assert segment["end_endpoint"]["event_type"] == "bounce"
    assert segment["end_endpoint"]["outcome_classification"] == "in_court"
    assert segment["end_endpoint"]["automatic_adjudication"] is False


def test_sparse_trusted_stereo_anchor_enhances_but_does_not_claim_true_3d():
    segment = _build(measurements=[_measurement(100.0)])
    assert segment["reconstruction_mode"] == "stereo_anchored_2_5d"
    assert segment["stereo_anchor_count"] == 1
    assert segment["metric_validity"] == "visualization_only"


def test_two_trusted_anchors_and_qualified_fit_publish_estimated_3d():
    reconstructed = Reconstructed3DSegment(
        "flight-1",
        FULL_ESTIMATED_3D,
        samples=[Reconstructed3DSample(0.0, 2.0, 3.0, 2.0), Reconstructed3DSample(1.0, 3.4, 3.7, 0.0)],
        reprojection_error_px=5.0,
        stereo_coverage=0.8,
    )
    base = {"segment_id": "flight-1", "samples": [{"timestamp_sec": 0.0}, {"timestamp_sec": 0.23}]}
    segment = _build(
        measurements=[_measurement(10.0), _measurement(200.0)],
        reconstructed_3d=reconstructed,
        base=base,
    )
    assert segment["reconstruction_mode"] == "stereo_estimated_3d"
    assert segment["metric_validity"] == "approximate_multiview"
    assert segment["metric_eligibility"]["peak_height"]


def test_no_anchor_visual_arc_fades_unknown_endpoints_and_remains_displayable():
    segment = _build(flight=_flight(None, None), events={})
    assert segment["reconstruction_mode"] == "single_view_visual_arc"
    assert segment["samples"][0]["height_confidence"] == 0.0
    assert segment["samples"][-1]["height_confidence"] == 0.0
    assert segment["display_level"] == "low"


def test_unqualified_3d_does_not_block_other_displayable_segments():
    degraded = _build(reconstructed_3d=Reconstructed3DSegment("flight-1", UNAVAILABLE))
    unavailable_points = {"cam_a": _points("cam_a")[:2], "cam_b": _points("cam_b")[:2]}
    short_flight = FlightSegment("flight-2", 0, 1, point_indices=[0, 1])
    unavailable = build_hybrid_segment(
        flight=short_flight,
        points_by_view=unavailable_points,
        events_by_id={},
        main_view=_selection(unavailable_points),
        projections={"cam_a": PROJECTION, "cam_b": PROJECTION},
        reconstructed_3d=Reconstructed3DSegment("flight-2", UNAVAILABLE),
        stereo_measurements=[],
        base_3d_payload=None,
    )
    assert degraded["display_level"] != "none"
    assert unavailable["reconstruction_mode"] == "unavailable"


def test_hybrid_segment_reconstruction_is_deterministic():
    assert _build() == _build()
