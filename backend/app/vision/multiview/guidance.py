"""CrossViewGuidance + CrossViewGuidancePolicy。

强 guidance 仅对 `confirmed AND cross_view_anchored` 的 global player 生成(design D6/D7)。
guidance 只提供 ROI 搜索先验,不直接制造 observation(invariant 3)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.vision.multiview.court_frame import CourtOrientation, canonical_to_local
from app.vision.multiview.global_state import GlobalPlayerState


@dataclass
class GuidanceDecision:
    """side-effect-free guidance 决策可观测（player-display-diagnostics 消费）。

    仅记录"生成 / 未生成 + 原因"，不改变 generate() 的返回与触发语义。

    - `trigger_source`：为什么有资格（`visibility_age | available_miss | None`）；
    - `reason`：最终为什么生成 / 拒绝（不包含 trigger 语义）。
    """

    global_player_id: str
    target_view: str
    tick: int
    status: str  # generated | not_eligible
    reason: str | None = None
    guidance_id: str | None = None
    trigger_source: str | None = None  # visibility_age | available_miss | None


@dataclass
class CrossViewGuidancePolicy:
    """guidance 触发语义(参数值留实验调,语义冻结)。"""

    min_global_confidence: float = 0.6
    max_uncertainty_ft: float = 8.0
    missing_after_ms: float = 300.0      # binding 超过该 gap 视为 weak
    lost_after_ms: float = 1000.0        # binding 超过该 gap 视为 lost
    guidance_cooldown_ticks: int = 3
    max_regions_per_view_per_tick: int = 4
    base_roi_margin_px: float = 40.0
    uncertainty_to_px_scale: float = 12.0
    max_roi_margin_px: float = 160.0
    min_donor_quality: float = 0.55
    donor_max_age_ms: float = 300.0
    donor_origins: tuple[str, ...] = ("base",)
    # available-miss fast path：由 MultiViewJointRun.__init__ 从
    # P1OnlineRecoveryConfig.fast_recovery_enabled 同步（配置真源唯一）。
    fast_recovery_enabled: bool = True
    # same-tick usable-candidate recovery（B-Phase-2）：由 MultiViewJointRun.__init__ 同步。
    same_tick_recovery_enabled: bool = True
    pre_association_gate_ft: float = 3.0
    ambiguity_margin: float = 0.15


@dataclass
class CrossViewGuidance:
    """一次跨视角搜索先验。"""

    global_player_id: str
    target_view: str
    predicted_canonical_position: tuple[float, float]
    uncertainty_ft: float
    predicted_local_position: tuple[float, float]
    expected_image_position: tuple[float, float]
    roi: tuple[float, float, float, float]  # (x1, y1, x2, y2) 目标视角图像空间
    confidence: float
    expires_at: float
    guidance_id: str = ""
    donor_view: str | None = None
    donor_view_player_id: str | None = None
    donor_source_frame_index: int | None = None
    donor_take_timestamp_ms: float | None = None
    donor_quality: float = 0.0
    donor_origin: str = "base"
    expected_global_player_id: str | None = None
    recovery_episode_id: str | None = None


class GuidanceGenerator:
    """按 policy 为 confirmed + anchored 的 global 生成 guidance。"""

    def __init__(self, policy: CrossViewGuidancePolicy | None = None) -> None:
        self.policy = policy or CrossViewGuidancePolicy()
        self._last_generated: dict[tuple[str, str], int] = {}  # (global, view) -> tick
        # side-effect-free 决策可观测：最近一次 generate 调用的原因记录
        self.last_decisions: list[GuidanceDecision] = []

    def _record(self, *, gid: str, target_view: str, tick: int, status: str, reason: str | None = None,
                guidance_id: str | None = None, trigger_source: str | None = None) -> None:
        """追加一条 GuidanceDecision（只读可观测，不改任何逻辑）。"""
        self.last_decisions.append(
            GuidanceDecision(
                global_player_id=gid,
                target_view=target_view,
                tick=tick,
                status=status,
                reason=reason,
                guidance_id=guidance_id,
                trigger_source=trigger_source,
            )
        )

    def generate(
        self,
        *,
        global_state: GlobalPlayerState,
        target_view: str,
        orientation: CourtOrientation,
        inverse_homography: Any,
        now_take_ms: float,
        tick: int,
        frame_width: int,
        frame_height: int,
        prediction: tuple[float, float, float] | None,
        donor_view: str | None = None,
        donor_binding: Any | None = None,
        target_frame_available: bool = True,
        strict_donor: bool = False,
    ) -> CrossViewGuidance | None:
        """对单个 confirmed+anchored global 生成 guidance;不满足条件返回 None。

        本方法为 side-effect-free 决策可观测记录 `last_decisions`（不改触发语义）。
        """
        p = self.policy
        gid = global_state.global_player_id
        if not target_frame_available:
            self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="target_frame_unavailable")
            return None
        if global_state.lifecycle != "confirmed" or not global_state.cross_view_anchored:
            self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="not_confirmed_anchored")
            return None
        if prediction is None:
            self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="prediction_unavailable")
            return None
        px, py, uncertainty = prediction
        if uncertainty > p.max_uncertainty_ft:
            self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="prediction_uncertain")
            return None

        binding = global_state.view_bindings.get(target_view)
        # 触发资格：共享 predicate（与 run 的 recovery opportunity/episode 同一语义，
        # 避免两处漂移产生幽灵 guidance）。fast path 允许 visibility 仍为 observed
        # 但上一 tick 出现 available miss 时提前触发。
        from app.vision.multiview.recovery_config import is_target_recovery_eligible

        if binding is None or not is_target_recovery_eligible(binding, p.fast_recovery_enabled):
            self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="target_not_missing")
            return None
        # trigger_source：visibility age 优先，fast path 次之（仅诊断，不影响逻辑）
        trigger_source = (
            "visibility_age"
            if binding.visibility in {"weak", "missing", "lost"}
            else "available_miss"
            if getattr(binding, "consecutive_available_misses", 0) >= 1
            else None
        )
        if strict_donor:
            if donor_binding is None or donor_view is None or donor_view == target_view:
                self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="donor_unavailable", trigger_source=trigger_source)
                return None
            last_donor_seen = donor_binding.last_seen_take_timestamp_ms
            donor_age = now_take_ms - (last_donor_seen if last_donor_seen is not None else now_take_ms)
            if (
                donor_binding.observation_origin != "base"
                or donor_binding.visibility not in {"observed", "weak"}
                or donor_age > p.donor_max_age_ms
            ):
                self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="donor_stale", trigger_source=trigger_source)
                return None
            if donor_binding.quality < p.min_donor_quality:
                self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="donor_low_quality", trigger_source=trigger_source)
                return None
        # cooldown
        key = (global_state.global_player_id, target_view)
        last_tick = self._last_generated.get(key, -10**9)
        if tick - last_tick < p.guidance_cooldown_ticks:
            self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="cooldown", trigger_source=trigger_source)
            return None

        # canonical → local → image；ROI 复用共享纯函数（与 diagnostics 同一几何）
        from app.vision.multiview.player_display_diagnostics import build_expected_player_region

        region = build_expected_player_region(
            predicted_canonical_position=(px, py),
            uncertainty_ft=uncertainty,
            orientation=orientation,
            inverse_homography=inverse_homography,
            frame_width=frame_width,
            frame_height=frame_height,
            policy=p,
        )
        if region.status != "available" or region.roi is None or region.expected_image_position is None:
            self._record(gid=gid, target_view=target_view, tick=tick, status="not_eligible", reason="geometry_unavailable")
            return None
        (ix, iy) = region.expected_image_position
        x1, y1, x2, y2 = region.roi
        r_px = region.radius_px if region.radius_px is not None else 0.0
        lx, ly = canonical_to_local(px, py, orientation)

        guidance_id = f"g_{global_state.global_player_id}_{target_view}_{tick}"
        guidance = CrossViewGuidance(
            global_player_id=global_state.global_player_id,
            target_view=target_view,
            predicted_canonical_position=(px, py),
            uncertainty_ft=uncertainty,
            predicted_local_position=(lx, ly),
            expected_image_position=(ix, iy),
            roi=(x1, y1, x2, y2),
            confidence=max(0.0, 1.0 - uncertainty / p.max_uncertainty_ft),
            expires_at=now_take_ms + 50.0,
            guidance_id=guidance_id,
            donor_view=donor_view,
            donor_view_player_id=getattr(donor_binding, "view_player_id", None),
            donor_source_frame_index=getattr(donor_binding, "last_source_frame_index", None),
            donor_take_timestamp_ms=getattr(donor_binding, "last_seen_take_timestamp_ms", None),
            donor_quality=float(getattr(donor_binding, "quality", 0.0) or 0.0),
            donor_origin=str(getattr(donor_binding, "observation_origin", "base")),
            expected_global_player_id=global_state.global_player_id,
        )
        self._record(
            gid=gid, target_view=target_view, tick=tick, status="generated", guidance_id=guidance_id,
            trigger_source=trigger_source,
        )
        return guidance

    def generate_for_view(
        self,
        *,
        registry,
        target_view: str,
        orientation: CourtOrientation,
        inverse_homography: Any,
        now_take_ms: float,
        tick: int,
        frame_width: int,
        frame_height: int,
        predictions: dict[str, tuple[float, float, float]],
        candidate_donor_views: tuple[str, ...] | None = None,
        target_frame_available: bool = True,
        strict_donor: bool = True,
    ) -> list[CrossViewGuidance]:
        """为目标视角生成全部符合条件的 guidance(受 max_regions_per_view_per_tick 限制)。"""
        out: list[CrossViewGuidance] = []
        for gid, state in registry.players.items():
            pred = predictions.get(gid)
            if pred is None:
                continue
            donor_view = None
            donor_binding = None
            if strict_donor:
                for candidate_view in candidate_donor_views or tuple(state.view_bindings):
                    if candidate_view == target_view:
                        continue
                    candidate = state.view_bindings.get(candidate_view)
                    if candidate is None:
                        continue
                    candidate_seen = candidate.last_seen_take_timestamp_ms
                    candidate_age = now_take_ms - (
                        candidate_seen if candidate_seen is not None else now_take_ms
                    )
                    if (
                        candidate.observation_origin not in self.policy.donor_origins
                        or candidate.visibility not in {"observed", "weak"}
                        or candidate_age > self.policy.donor_max_age_ms
                        or candidate.quality < self.policy.min_donor_quality
                    ):
                        continue
                    if donor_binding is None or candidate.quality > donor_binding.quality:
                        donor_view, donor_binding = candidate_view, candidate
            g = self.generate(
                global_state=state,
                target_view=target_view,
                orientation=orientation,
                inverse_homography=inverse_homography,
                now_take_ms=now_take_ms,
                tick=tick,
                frame_width=frame_width,
                frame_height=frame_height,
                prediction=pred,
                donor_view=donor_view,
                donor_binding=donor_binding,
                target_frame_available=target_frame_available,
                strict_donor=strict_donor,
            )
            if g is not None:
                out.append(g)
            if len(out) >= self.policy.max_regions_per_view_per_tick:
                break
        return out

    def commit(self, guidance: CrossViewGuidance, tick: int) -> None:
        """Consume cooldown only after target ROI detection was invoked."""
        self._last_generated[(guidance.global_player_id, guidance.target_view)] = tick


def court_to_image_single(point: tuple[float, float], inverse_homography: Any) -> tuple[float, float]:
    """把球场坐标投影到图像空间(复用 court_to_image,需传 H^-1)。"""
    from app.vision.courtvision_calibration_engine.homography import court_to_image

    result = court_to_image(point, inverse_homography)
    if isinstance(result, tuple):
        return float(result[0]), float(result[1])
    row = result[0]
    return float(row[0]), float(row[1])


def invert_homography(homography: list[list[float]]) -> np.ndarray:
    """H^-1(球场→图像方向)。"""
    return np.linalg.inv(np.asarray(homography, dtype=float))
