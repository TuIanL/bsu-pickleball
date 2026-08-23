"""Ball 3D artifact builders（球 3D：立体证据 v1 与轨迹 v3 序列化）。

D9: `multiview_ball_stereo_evidence.v1`（不可变原始证据）+ `reconstructed_ball_trajectory.v3`
（reconstruction_mode=multiview_estimated_3d，指标级 validity 分级 + 分层可用状态）。
前端沿用统一 `reconstructed-ball-trajectory` slug，v1/v2 保留。
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from app.vision.multiview.ball_stereo.landing_authority import LandingPointResult
from app.vision.multiview.ball_stereo.metrics import BallMetrics
from app.vision.multiview.ball_stereo.segment_reconstruction import (
    FULL_ESTIMATED_3D,
    LANDING_ONLY,
    PARTIAL_3D,
    UNAVAILABLE,
    Reconstructed3DSegment,
    Reconstructed3DSample,
)
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement


def build_stereo_evidence_v1(
    *,
    take_id: str,
    measurements: Sequence[BallStereoMeasurement],
    pairings: Iterable[dict],
    diagnostics: dict | None = None,
    source_context: dict | None = None,
) -> dict:
    """不可变立体证据产物（两路候选、配对、测量、回投诊断）。"""
    return {
        "schema_version": "multiview_ball_stereo_evidence.v1",
        "take_id": take_id,
        "measurements": [m.to_dict() for m in measurements],
        "pairings": list(pairings),
        "diagnostics": dict(diagnostics or {}),
        "source_context": dict(source_context or {}),
    }


def _samples_payload(samples: Sequence[Reconstructed3DSample], duration_sec: float) -> list[dict]:
    out = []
    for frame_index, sample in enumerate(samples):
        timestamp_sec = round(sample.t_norm * duration_sec, 4)
        out.append({
            # 同时保留 v3 算法字段和前端重建轨迹统一消费字段。
            "t_sec": timestamp_sec,
            "timestamp_sec": timestamp_sec,
            "frame_index": frame_index,
            "x_ft": round(sample.x_ft, 3),
            "y_ft": round(sample.y_ft, 3),
            "z_ft": round(sample.z_ft, 3),
            "court_xy": [round(sample.x_ft, 3), round(sample.y_ft, 3)],
            "estimated_height_ft": round(sample.z_ft, 3),  # v3: estimated_multiview_height
            "source": "model_predicted" if sample.source == "predicted" else "detected",
            "validity": sample.validity,
            "confidence": None,
        })
    return out


def _overall_status(segments: Sequence[Reconstructed3DSegment], has_landing: bool) -> str:
    if any(s.status == FULL_ESTIMATED_3D for s in segments):
        return FULL_ESTIMATED_3D
    if any(s.status == PARTIAL_3D for s in segments):
        return PARTIAL_3D
    if has_landing:
        return LANDING_ONLY
    return UNAVAILABLE


def build_v3_trajectory(
    *,
    job_id: str,
    take_id: str,
    bounce_source: str,
    segments: Sequence[Reconstructed3DSegment],
    landing: LandingPointResult | None,
    metrics_by_segment: dict[str, BallMetrics],
    duration_by_segment: dict[str, float],
    quality_summary: dict | None = None,
    diagnostics: dict | None = None,
) -> dict:
    """构造 `reconstructed_ball_trajectory.v3` 产物字典。"""
    seg_payload = []
    for seg in segments:
        metrics = metrics_by_segment.get(seg.segment_id)
        display_level = (
            "high" if seg.status == FULL_ESTIMATED_3D
            else "medium" if seg.status == PARTIAL_3D
            else "none"
        )
        seg_payload.append({
            "segment_id": seg.segment_id,
            "reconstruction_mode": "multiview_estimated_3d",
            "status": seg.status,
            "reprojection_error_px": seg.reprojection_error_px,
            "stereo_coverage": seg.stereo_coverage,
            "prediction_ratio": seg.prediction_ratio,
            "quality": {
                "observation_coverage": seg.stereo_coverage,
                "image_fit_rmse_px": seg.reprojection_error_px,
                "predicted_ratio": seg.prediction_ratio,
                "display_level": display_level,
                "overall": max(0.0, min(1.0, 1.0 - float(seg.reprojection_error_px) / 60.0))
                if math.isfinite(seg.reprojection_error_px) else 0.0,
            },
            "samples": _samples_payload(seg.samples, duration_by_segment.get(seg.segment_id, 1.0)),
            "metrics": {
                "average_speed_kmh": metrics.average_speed_kmh if metrics else None,
                "average_speed_validity": (metrics.average_speed_validity if metrics else "unavailable"),
                "speed_eligibility_reason": (metrics.speed_eligibility_reason if metrics else None),
                "peak_height_ft": metrics.peak_height_ft if metrics else None,
                "net_height_ft": metrics.net_height_ft if metrics else None,
                "derived_from": "derived_from_estimated_3d",
            } if metrics else None,
        })

    landing_payload = None
    if landing is not None:
        landing_payload = {
            "landing_x_ft": landing.landing_xy[0] if landing.landing_xy is not None else None,
            "landing_y_ft": landing.landing_xy[1] if landing.landing_xy is not None else None,
            "landing_source": landing.landing_source,
            "landing_validity": landing.landing_validity,
            "geometry_quality": landing.geometry_quality,
        }

    overall_status = _overall_status(segments, landing is not None and landing.landing_xy is not None)
    return {
        "schema_version": "reconstructed_ball_trajectory.v3",
        "job_id": job_id,
        "take_id": take_id,
        "status": {
            FULL_ESTIMATED_3D: "available",
            PARTIAL_3D: "partial",
            LANDING_ONLY: "partial",
            UNAVAILABLE: "unavailable",
        }.get(overall_status, "unavailable"),
        "detail": {
            FULL_ESTIMATED_3D: "双摄三维球路可用",
            PARTIAL_3D: "双摄三维球路部分可用",
            LANDING_ONLY: "三维球路不可用，仅保留落点（如有）",
            UNAVAILABLE: "没有足够双摄证据生成球路",
        }.get(overall_status, "双摄球路不可用"),
        "reconstruction_mode": "multiview_estimated_3d",
        "bounce_source": bounce_source,
        "coordinate_semantics": {
            "xy": "canonical_court_ft",
            "z": "estimated_multiview_height_ft",
            "validity": "approximate_multiview",
        },
        "landing_point": landing_payload,
        "overall_status": overall_status,
        "events": [],
        "player_roster": [],
        "segments": seg_payload,
        "quality_summary": dict(quality_summary or {}),
        "diagnostics": dict(diagnostics or {}),
    }
