"""JointOverlayEvidenceBundle —— fused overlay 的只读证据载体。

把 F0RefinementSnapshot、accepted F1 recovered observations、final fused
trajectory、roster map、view geometry 组装为 immutable bundle，供
FusedPlayerOverlayBuilder 消费。**绝不反写 tracker / association / metrics**
（spec `multiview-fused-player-overlay`：overlay 只消费分析结果）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.vision.multiview.offline_refinement import F0RefinementSnapshot, RecoveredViewObservation
from app.vision.multiview.bootstrap_display_backfill import BootstrapBackfillObservation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ViewGeometry:
    """target view 的图像投影依赖。"""

    view_id: str
    orientation: Any
    inverse_homography: Any
    frame_width: int
    frame_height: int


@dataclass(frozen=True)
class JointOverlayEvidenceBundle:
    """fused overlay 的只读证据集合。"""

    f0_snapshot: F0RefinementSnapshot | None = None
    reference_view_id: str = "cam_1"
    view_ids: tuple[str, ...] = ("cam_1", "cam_2")
    # global_player_id → canonical Player_N（复用 _build_roster_map 产物）
    roster_map: dict[str, str] = field(default_factory=dict)
    # view_id → ViewGeometry（orientation / inverse_homography / frame size）
    view_geometry: dict[str, ViewGeometry] = field(default_factory=dict)
    # final fused trajectory samples：global_player_id → {reference_frame_index: sample}
    fused_samples: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    # final fused canonical 位置索引：global_player_id → {reference_frame_index: (x_ft, y_ft)}
    fused_positions: dict[str, dict[int, tuple[float, float]]] = field(default_factory=dict)
    # accepted F1 recovered observations：{(global_player_id, canonical_tick): RecoveredViewObservation}
    recovered_observations: dict[tuple[str, int], RecoveredViewObservation] = field(default_factory=dict)
    # final_source（refined_f1 / first_pass_f0）
    final_source: str = "first_pass_f0"
    # 每 view 最近真实观测时间（global_player_id, view_id) → take_timestamp_ms（供 recency gate）
    last_real_observed_ms: dict[tuple[str, str], float] = field(default_factory=dict)
    # bootstrap 启动窗口展示回填：(player_id, reference_frame_index) → 真实观测（display-only）
    bootstrap_backfill: dict[tuple[str, int], BootstrapBackfillObservation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "view_ids", tuple(self.view_ids))
        object.__setattr__(self, "roster_map", dict(self.roster_map))
        object.__setattr__(self, "view_geometry", dict(self.view_geometry))
        object.__setattr__(self, "fused_samples", {
            gid: dict(samples) for gid, samples in self.fused_samples.items()
        })
        object.__setattr__(self, "fused_positions", {
            gid: dict(positions) for gid, positions in self.fused_positions.items()
        })
        object.__setattr__(self, "recovered_observations", dict(self.recovered_observations))
        object.__setattr__(self, "last_real_observed_ms", dict(self.last_real_observed_ms))
        object.__setattr__(self, "bootstrap_backfill", dict(self.bootstrap_backfill))

    # ---- 只读查询 ----------------------------------------------------------

    def player_id_for(self, global_player_id: str) -> str:
        """global_player_id → canonical Player_N；无映射时按原样（调用方兜底）。"""
        return self.roster_map.get(global_player_id, global_player_id)

    def geometry_for(self, view_id: str) -> ViewGeometry | None:
        return self.view_geometry.get(view_id)

    def fused_sample_for(
        self, global_player_id: str, reference_frame_index: int
    ) -> dict[str, Any] | None:
        by_frame = self.fused_samples.get(global_player_id)
        return by_frame.get(reference_frame_index) if by_frame else None

    def fused_position_for(
        self, global_player_id: str, reference_frame_index: int
    ) -> tuple[float, float] | None:
        by_frame = self.fused_positions.get(global_player_id)
        return by_frame.get(reference_frame_index) if by_frame else None

    def recovered_for(
        self, global_player_id: str, canonical_tick: int
    ) -> RecoveredViewObservation | None:
        return self.recovered_observations.get((global_player_id, canonical_tick))

    def has_recovered_evidence(self) -> bool:
        return self.final_source == "refined_f1" and bool(self.recovered_observations)

    def bootstrap_for(
        self, player_id: str, reference_frame_index: int
    ) -> BootstrapBackfillObservation | None:
        """查询某 (Player_N, tick) 的 bootstrap 回填观测（display-only 兜底）。"""
        return self.bootstrap_backfill.get((player_id, reference_frame_index))


def build_overlay_evidence_bundle(
    *,
    f0_snapshot: F0RefinementSnapshot | None,
    reference_view_id: str,
    roster_map: dict[str, str],
    view_geometry: dict[str, ViewGeometry] | None = None,
    fused_trajectory: Mapping[str, Any] | None = None,
    recovered_observations: list[RecoveredViewObservation] | None = None,
    final_source: str = "first_pass_f0",
    bootstrap_backfill: list[BootstrapBackfillObservation] | None = None,
) -> JointOverlayEvidenceBundle:
    """从 joint run 产物组装只读 evidence bundle。

    - `fused_trajectory`：`fused_player_trajectory.v2` payload（含 samples）；
    - `recovered_observations`：F1 accepted observations（无则空）；
    - `bootstrap_backfill`：启动窗口 retrospective 真实观测回填（display-only）。
    """
    fused_samples: dict[str, dict[int, dict[str, Any]]] = {}
    fused_positions: dict[str, dict[int, tuple[float, float]]] = {}
    raw_samples = (
        fused_trajectory.get("samples", [])
        if isinstance(fused_trajectory, Mapping)
        else []
    )
    for raw in raw_samples:
        if not isinstance(raw, Mapping):
            continue
        gid = str(raw.get("global_player_id", ""))
        frame_index = int(raw.get("reference_frame_index", 0))
        x = raw.get("x_ft")
        y = raw.get("y_ft")
        if not gid or x is None or y is None:
            continue
        fused_samples.setdefault(gid, {})[frame_index] = dict(raw)
        fused_positions.setdefault(gid, {})[frame_index] = (float(x), float(y))

    recovered_map: dict[tuple[str, int], RecoveredViewObservation] = {}
    last_real_observed_ms: dict[tuple[str, str], float] = {}
    for observation in recovered_observations or []:
        key = (observation.global_player_id, observation.canonical_tick)
        recovered_map[key] = observation

    # 从 F0 snapshot 收集"最近真实观测"时间（供 cross_view recency gate）
    if f0_snapshot is not None:
        for tick in f0_snapshot.ticks:
            for gid, view_id, state in tick.observations:
                if not state.observed:
                    continue
                if state.origin == "base" or state.origin == "guided_roi":
                    key = (gid, view_id)
                    observed_ms = state.mapped_take_timestamp_ms
                    if observed_ms is not None:
                        current = last_real_observed_ms.get(key)
                        if current is None or observed_ms > current:
                            last_real_observed_ms[key] = observed_ms

    bootstrap_map: dict[tuple[str, int], BootstrapBackfillObservation] = {}
    for obs in bootstrap_backfill or []:
        bootstrap_map[(obs.player_id, obs.frame_index)] = obs

    return JointOverlayEvidenceBundle(
        f0_snapshot=f0_snapshot,
        reference_view_id=reference_view_id,
        view_ids=tuple(f0_snapshot.view_ids) if f0_snapshot is not None else ("cam_1", "cam_2"),
        roster_map=dict(roster_map),
        view_geometry=dict(view_geometry or {}),
        fused_samples=fused_samples,
        fused_positions=fused_positions,
        recovered_observations=recovered_map,
        final_source=str(final_source),
        last_real_observed_ms=last_real_observed_ms,
        bootstrap_backfill=bootstrap_map,
    )
