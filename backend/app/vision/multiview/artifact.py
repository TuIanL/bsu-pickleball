"""Fused Artifact 与 Diagnostics（artifact）—— fused_player_trajectory.v1 的序列化与诊断。

- 每个 sample 保留 `measurement_source` 与 `metric_eligible`，可回答"该 fused 点由哪两个
  真实帧组成、是否可进入运动指标"；
- diagnostics 记录 orientation normalization / frame mapping errors / association
  decisions / view quality scores / view disagreement / fallback & conflict counts。
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from statistics import mean, median

from app.vision.multiview.association import PlayerAssociation
from app.vision.multiview.fusion import FusionMeasurement
from app.vision.multiview.pairing import FramePairingPlan

FUSED_TRAJECTORY_SCHEMA_VERSION = "fused_player_trajectory.v1"
FUSED_DIAGNOSTICS_SCHEMA_VERSION = "fused_diagnostics.v1"

# fused artifact 的约定文件名。
FUSED_TRAJECTORY_FILENAME = "fused_player_trajectory.json"
FUSED_DIAGNOSTICS_FILENAME = "fused_diagnostics.json"
NORMAL_MULTIVIEW_COVERAGE = 0.6


def evidence_summary_from_measurements(
    measurements: Sequence[FusionMeasurement],
    *,
    normal_coverage: float = NORMAL_MULTIVIEW_COVERAGE,
) -> dict[str, object]:
    """Derive user-visible multiview mode from actual samples, not execution intent."""
    secondary_available = sum(
        1 for m in measurements
        if "secondary" in m.view_observations or len(m.contributing_views) >= 2
    )
    dual_evidence = sum(
        1
        for m in measurements
        if m.fusion_status == "dual_observed"
        or {"reference", "secondary"}.issubset(m.view_observations)
        or len(m.contributing_views) >= 2
    )
    single_fallback = sum(1 for m in measurements if m.fusion_status == "single_view_fallback")
    predicted = sum(1 for m in measurements if m.fusion_status == "predicted")
    sample_count = len(measurements)
    ratio = dual_evidence / sample_count if sample_count else 0.0
    mode = (
        "single_view_fallback"
        if dual_evidence == 0
        else "multiview_degraded"
        if ratio < normal_coverage
        else "multiview_fused"
    )
    return {
        "secondary_available_samples": secondary_available,
        "dual_evidence_samples": dual_evidence,
        "single_view_fallback_samples": single_fallback,
        "predicted_samples": predicted,
        "effective_multiview_ratio": ratio,
        "effective_mode": mode,
    }


def evidence_summary_from_artifact(
    artifact: dict[str, object],
    *,
    normal_coverage: float = NORMAL_MULTIVIEW_COVERAGE,
) -> dict[str, object]:
    """Same evidence contract for Composer, which consumes serialized artifacts."""
    samples = artifact.get("samples", [])
    if not isinstance(samples, list):
        samples = []
    secondary_available = 0
    dual_evidence = 0
    single_fallback = 0
    predicted = 0
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        details = sample.get("view_observations")
        contributing = sample.get("contributing_views")
        has_multiple_views = isinstance(contributing, list) and len(contributing) >= 2
        if (isinstance(details, dict) and "secondary" in details) or has_multiple_views:
            secondary_available += 1
        if sample.get("fusion_status") == "dual_observed" or (
            isinstance(contributing, list)
            and ({"reference", "secondary"}.issubset(contributing) or has_multiple_views)
        ):
            dual_evidence += 1
        if sample.get("fusion_status") == "single_view_fallback":
            single_fallback += 1
        if sample.get("fusion_status") == "predicted":
            predicted += 1
    sample_count = len(samples)
    ratio = dual_evidence / sample_count if sample_count else 0.0
    mode = (
        "single_view_fallback"
        if dual_evidence == 0
        else "multiview_degraded"
        if ratio < normal_coverage
        else "multiview_fused"
    )
    return {
        "secondary_available_samples": secondary_available,
        "dual_evidence_samples": dual_evidence,
        "single_view_fallback_samples": single_fallback,
        "predicted_samples": predicted,
        "effective_multiview_ratio": ratio,
        "effective_mode": mode,
    }


def serialize_fused_sample(measurement: FusionMeasurement) -> dict[str, object]:
    """把 FusionMeasurement 序列化为 fused_player_trajectory.v1 的一个 sample。"""
    return {
        "global_player_id": measurement.global_player_id,
        "timestamp_seconds": measurement.timestamp_seconds,
        "take_timestamp_ms": measurement.take_timestamp_ms,
        "reference_frame_index": measurement.reference_frame_index,
        "x_ft": measurement.x_ft,
        "y_ft": measurement.y_ft,
        "fusion_status": measurement.fusion_status,
        "fusion_confidence": measurement.fusion_confidence,
        "contributing_views": list(measurement.contributing_views),
        "selected_view": measurement.selected_view,
        "view_observations": measurement.view_observations,
        "association_confidence": measurement.association_confidence,
        "sync_quality": measurement.sync_quality,
        "court_frame_version": measurement.court_frame_version,
        "measurement_source": measurement.measurement_source,
        "metric_eligible": measurement.metric_eligible,
    }


def build_fused_artifact(
    measurements: Sequence[FusionMeasurement],
    *,
    run_id: str,
    capture_take_id: str,
    reference_view_id: str,
    secondary_view_id: str,
    sync_quality: str,
    court_frame_version: str,
    canonical_frame_id: str | None = None,
) -> dict[str, object]:
    """构建 fused_player_trajectory.v1 artifact（samples 按时间排序）。"""
    ordered = sorted(measurements, key=lambda m: (m.take_timestamp_ms, m.global_player_id))
    players = sorted({m.global_player_id for m in ordered})
    return {
        "schema_version": FUSED_TRAJECTORY_SCHEMA_VERSION,
        "run_id": run_id,
        "capture_take_id": capture_take_id,
        "reference_view_id": reference_view_id,
        "secondary_view_id": secondary_view_id,
        "sync_quality": sync_quality,
        "court_frame_version": court_frame_version,
        "canonical_frame_id": canonical_frame_id,
        "players": players,
        "samples": [serialize_fused_sample(m) for m in ordered],
    }


def write_fused_artifact(
    output_dir: str | os.PathLike[str],
    artifact: dict[str, object],
    *,
    filename: str = FUSED_TRAJECTORY_FILENAME,
) -> Path:
    """把 fused artifact 写入 Run 产物目录。"""
    path = Path(output_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_fused_artifact(path: str | os.PathLike[str]) -> dict[str, object] | None:
    """读取 fused artifact；缺失/损坏返回 None。"""
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def _frame_mapping_errors(measurements: Sequence[FusionMeasurement]) -> dict[str, object]:
    """统计各视角配对映射误差（selection_error_ms）。"""
    reference_errors: list[float] = []
    secondary_errors: list[float] = []
    for measurement in measurements:
        for view_key, detail in measurement.view_observations.items():
            error = detail.get("selection_error_ms")
            if error is None or not isinstance(error, (int, float)):
                continue
            if view_key == "secondary":
                secondary_errors.append(float(error))
            else:
                reference_errors.append(float(error))
    return {
        "reference_count": len(reference_errors),
        "secondary_count": len(secondary_errors),
        "secondary_max_error_ms": max(secondary_errors, default=None),
        "secondary_mean_error_ms": mean(secondary_errors) if secondary_errors else None,
        "secondary_over_tolerance_ms": [
            float(e) for e in secondary_errors if e > 1000.0 / 30.0
        ][:10],
    }


def _view_disagreement(measurements: Sequence[FusionMeasurement]) -> dict[str, object]:
    """统计双观测时刻的 inter-view 距离分布（视角分歧）。"""
    distances: list[float] = []
    for measurement in measurements:
        ref_detail = measurement.view_observations.get("reference")
        sec_detail = measurement.view_observations.get("secondary")
        if not ref_detail or not sec_detail:
            continue
        ref_x = ref_detail.get("x_ft")
        ref_y = ref_detail.get("y_ft")
        sec_x = sec_detail.get("x_ft")
        sec_y = sec_detail.get("y_ft")
        if None in (ref_x, ref_y, sec_x, sec_y):
            continue
        distances.append(
            ((float(ref_x) - float(sec_x)) ** 2 + (float(ref_y) - float(sec_y)) ** 2) ** 0.5
        )
    return {
        "dual_samples": len(distances),
        "median_distance_ft": median(distances) if distances else None,
        "mean_distance_ft": mean(distances) if distances else None,
        "p90_distance_ft": (
            sorted(distances)[int(len(distances) * 0.9) - 1] if distances else None
        ),
    }


def build_fusion_diagnostics(
    measurements: Sequence[FusionMeasurement],
    *,
    run_id: str,
    global_players: Sequence[PlayerAssociation],
    orientations: dict[str, str],
    reference_view_id: str,
    secondary_view_id: str,
    pairing_plan: FramePairingPlan | None = None,
    canonical_frame_id: str | None = None,
    authority_reason: str | None = None,
    requested_mode: str | None = None,
) -> dict[str, object]:
    """构建 fused_diagnostics.v1 artifact。"""
    status_counts = Counter(m.fusion_status for m in measurements)
    eligible = sum(1 for m in measurements if m.metric_eligible)
    quality_scores = _view_quality_summary(measurements)

    diagnostics: dict[str, object] = {
        "schema_version": FUSED_DIAGNOSTICS_SCHEMA_VERSION,
        "run_id": run_id,
        "orientation_normalization": {
            "reference": orientations.get(reference_view_id),
            "secondary": orientations.get(secondary_view_id),
            "note": "各 view local→canonical 变换",
        },
        "association_decisions": [
            {
                "global_player_id": g.global_player_id,
                "reference_view_player_id": g.reference_view_player_id,
                "secondary_view_player_id": g.secondary_view_player_id,
                "confidence": g.confidence,
            }
            for g in global_players
        ],
        "view_quality_scores": quality_scores,
        "view_disagreement": _view_disagreement(measurements),
        "frame_mapping_errors": _frame_mapping_errors(measurements),
        "fusion_status_counts": dict(status_counts),
        "sample_count": len(measurements),
        "metric_eligible_count": eligible,
    }
    diagnostics.update(evidence_summary_from_measurements(measurements))
    diagnostics["canonical_frame_id"] = canonical_frame_id
    diagnostics["requested_mode"] = requested_mode
    diagnostics["authority_reason"] = authority_reason
    if pairing_plan is not None:
        diagnostics["pairing_plan"] = {
            "reference_view_id": pairing_plan.reference_view_id,
            "secondary_view_id": pairing_plan.secondary_view_id,
            "secondary_camera_id": pairing_plan.secondary_camera_id,
            "max_pairing_error_ms": pairing_plan.max_pairing_error_ms,
            "decision_count": len(pairing_plan.decisions),
            "available_count": pairing_plan.available_count,
            "unavailable_count": len(pairing_plan.decisions) - pairing_plan.available_count,
            "source_frame_indices": [
                decision.secondary_frame_index
                for decision in pairing_plan.decisions
                if decision.available
            ],
            "decisions": [
                {
                    "reference_frame_index": decision.reference_frame_index,
                    "secondary_frame_index": decision.secondary_frame_index,
                    "secondary_timestamp_seconds": decision.secondary_timestamp_seconds,
                    "mapped_secondary_timestamp_seconds": decision.mapped_secondary_timestamp_seconds,
                    "selection_error_ms": decision.selection_error_ms,
                    "status": decision.status,
                    "reason": decision.reason,
                }
                for decision in pairing_plan.decisions
            ],
        }
    return diagnostics


def _view_quality_summary(measurements: Sequence[FusionMeasurement]) -> dict[str, object]:
    """各视角观测质量分摘要（来自 view_observations 的 quality 字段）。"""
    by_view: dict[str, list[float]] = {"reference": [], "secondary": []}
    for measurement in measurements:
        for view_key, detail in measurement.view_observations.items():
            quality = detail.get("quality")
            if isinstance(quality, (int, float)):
                by_view.setdefault(view_key, []).append(float(quality))
    return {
        view: {
            "count": len(values),
            "mean": mean(values) if values else None,
        }
        for view, values in by_view.items()
    }


def write_fusion_diagnostics(
    output_dir: str | os.PathLike[str],
    diagnostics: dict[str, object],
    *,
    filename: str = FUSED_DIAGNOSTICS_FILENAME,
) -> Path:
    path = Path(output_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
