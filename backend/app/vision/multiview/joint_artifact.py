"""fused_player_trajectory.v2 writer + 公共 version-aware reader。

Additive P1(design D9):
- `late_fusion_v1 → writer_v1 → fused_player_trajectory.v1`(P0 writer 永远保留)
- `joint_tracking_v2 → writer_v2 → fused_player_trajectory.v2`
- 公共 `load_fused_trajectory()` version-aware:按 schema_version 归一化为 Composer 消费的
  normalized internal model。不依赖"v1 reader 能读 v2 未知字段"的假设。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

V1_SCHEMA = "fused_player_trajectory.v1"
V2_SCHEMA = "fused_player_trajectory.v2"
TIMING_PROVENANCE_FIELDS = (
    "source_frame_index",
    "source_timestamp_ms",
    "mapped_take_timestamp_ms",
    "selection_error_ms",
    "timing_authority",
    "sync_quality",
)


@dataclass
class FusedSample:
    """Composer 消费的 normalized fused sample。"""

    global_player_id: str
    take_timestamp_ms: float
    reference_frame_index: int
    x_ft: float
    y_ft: float
    fusion_status: str
    metric_eligible: bool
    observation_origin: str = "base"
    view_observations: dict[str, dict] = field(default_factory=dict)
    contributing_views: list[str] = field(default_factory=list)
    authoritative_joint_eligible: bool = False
    # 可选秒级时间戳（2026-08-13 起 writer 必写；历史产物缺失时由 reader 回退 take_timestamp_ms/1000）
    timestamp_seconds: float | None = None


@dataclass
class NormalizedFusedTrajectory:
    schema_version: str
    run_id: str
    capture_take_id: str
    reference_view_id: str
    samples: list[FusedSample]


def write_fused_v2(
    *,
    run_id: str,
    capture_take_id: str,
    reference_view_id: str,
    samples: list[FusedSample],
    authoritative_run: bool = False,
) -> dict[str, object]:
    """写入 `fused_player_trajectory.v2`(observation_origin 与 fusion_status 正交)。"""
    if authoritative_run:
        for sample in samples:
            for view_id, detail in sample.view_observations.items():
                missing = [field for field in TIMING_PROVENANCE_FIELDS if field not in detail]
                if missing:
                    raise ValueError(
                        f"authoritative sample {sample.reference_frame_index}/{view_id} "
                        f"missing timing fields: {', '.join(missing)}"
                    )
    return {
        "schema_version": V2_SCHEMA,
        "run_id": run_id,
        "capture_take_id": capture_take_id,
        "reference_view_id": reference_view_id,
        "authoritative_run": authoritative_run,
        "players": sorted({s.global_player_id for s in samples}),
        "samples": [
            {
                "global_player_id": s.global_player_id,
                "take_timestamp_ms": s.take_timestamp_ms,
                "timestamp_seconds": (
                    s.timestamp_seconds
                    if s.timestamp_seconds is not None
                    else s.take_timestamp_ms / 1000.0
                ),
                "reference_frame_index": s.reference_frame_index,
                "x_ft": s.x_ft,
                "y_ft": s.y_ft,
                "fusion_status": s.fusion_status,
                "metric_eligible": s.metric_eligible,
                "observation_origin": s.observation_origin,
                "view_observations": s.view_observations,
                "contributing_views": s.contributing_views,
                "authoritative_joint_eligible": s.authoritative_joint_eligible,
            }
            for s in samples
        ],
    }


def load_fused_trajectory(payload: dict[str, object]) -> NormalizedFusedTrajectory:
    """按 schema_version 归一化读取 v1 / v2。"""
    version = str(payload.get("schema_version", V1_SCHEMA))
    raw_samples = payload.get("samples", []) if isinstance(payload.get("samples"), list) else []
    samples: list[FusedSample] = []
    for raw in raw_samples:
        if not isinstance(raw, dict):
            continue
        if version == V2_SCHEMA:
            samples.append(_normalize_v2_sample(raw))
        else:
            samples.append(_normalize_v1_sample(raw))
    return NormalizedFusedTrajectory(
        schema_version=version,
        run_id=str(payload.get("run_id", "")),
        capture_take_id=str(payload.get("capture_take_id", "")),
        reference_view_id=str(payload.get("reference_view_id", "")),
        samples=samples,
    )


def _normalize_v1_sample(raw: dict) -> FusedSample:
    x = raw.get("x_ft")
    y = raw.get("y_ft")
    return FusedSample(
        global_player_id=str(raw.get("global_player_id", "")),
        take_timestamp_ms=float(raw.get("take_timestamp_ms", 0.0)),
        reference_frame_index=int(raw.get("reference_frame_index", 0)),
        x_ft=float(x) if x is not None else 0.0,
        y_ft=float(y) if y is not None else 0.0,
        fusion_status=str(raw.get("fusion_status", "unknown")),
        metric_eligible=bool(raw.get("metric_eligible", False)),
        observation_origin="base",
        view_observations={},
        contributing_views=list(raw.get("contributing_views", [])),
        timestamp_seconds=_optional_float(raw.get("timestamp_seconds")),
    )


def _normalize_v2_sample(raw: dict) -> FusedSample:
    x = raw.get("x_ft")
    y = raw.get("y_ft")
    return FusedSample(
        global_player_id=str(raw.get("global_player_id", "")),
        take_timestamp_ms=float(raw.get("take_timestamp_ms", 0.0)),
        reference_frame_index=int(raw.get("reference_frame_index", 0)),
        x_ft=float(x) if x is not None else 0.0,
        y_ft=float(y) if y is not None else 0.0,
        fusion_status=str(raw.get("fusion_status", "unknown")),
        metric_eligible=bool(raw.get("metric_eligible", False)),
        observation_origin=str(raw.get("observation_origin", "base")),
        view_observations=dict(raw.get("view_observations", {})),
        contributing_views=list(raw.get("contributing_views", [])),
        authoritative_joint_eligible=bool(raw.get("authoritative_joint_eligible", False)),
        timestamp_seconds=_optional_float(raw.get("timestamp_seconds")),
    )


def _optional_float(value: object) -> float | None:
    """读取可选浮点字段；None / 空串 / 非数值返回 None。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---- offline refinement(F1)产物 --------------------------------------------


RefinementStatus = Literal[
    "skipped_no_windows",
    "completed",
    "rejected_by_safety_gate",
    "failed_fallback",
]

F0_SNAPSHOT_SCHEMA = "f0_refinement_snapshot.v1"
REFINEMENT_DIAGNOSTICS_SCHEMA = "refinement_diagnostics.v1"


def write_recovered_observations(recovered: list[dict[str, object]]) -> dict[str, object]:
    """写入 `recovered_view_observations.v1.json`(F1 recovery provenance,不覆盖 F0)。"""
    return {
        "schema_version": "recovered_view_observations.v1",
        "observations": list(recovered),
    }


def write_f0_refinement_snapshot(snapshot: Any) -> dict[str, object]:
    """Serialize the immutable F0 evidence consumed by F1."""
    payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else dict(snapshot)
    payload["schema_version"] = F0_SNAPSHOT_SCHEMA
    return payload


def write_refinement_diagnostics(
    *,
    status: RefinementStatus,
    final_source: Literal["refined_f1", "first_pass_f0"],
    diagnostics: dict[str, object] | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Stable diagnostics artifact; never doubles as the parent manifest."""
    return {
        "schema_version": REFINEMENT_DIAGNOSTICS_SCHEMA,
        "status": status,
        "final_source": final_source,
        "reason": reason,
        **(diagnostics or {}),
    }


def build_refinement_manifest(
    *,
    status: RefinementStatus,
    final_source: Literal["refined_f1", "first_pass_f0"],
    first_pass_artifact: str | None = None,
    recovered_artifact: str | None = None,
    refined_artifact: str | None = None,
    f0_snapshot_artifact: str | None = None,
    diagnostics_artifact: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """manifest 的 `refinement` 字段(4 状态,对应 final_source)。"""
    return {
        "status": status,
        "final_source": final_source,
        "first_pass_artifact": first_pass_artifact,
        "recovered_observations": recovered_artifact,
        "refined_artifact": refined_artifact,
        "f0_snapshot_artifact": f0_snapshot_artifact,
        "diagnostics_artifact": diagnostics_artifact,
        "reason": reason,
    }
