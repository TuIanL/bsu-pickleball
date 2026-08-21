"""OverlayDisplayStateMachine + ViewPersonScaleProfile —— fused overlay 展示稳定性。

`stabilize-multiview-overlay-display`：

1. `OverlayDisplayStateMachine`：跨 tick 展示状态机（迟滞稳定 geometry，不伪造 evidence）。
   - `evidence_type`（`base_observed / guided_observed / refined_observed /
     cross_view_projected / predicted_only`）由分支决策链权威决定，状态机 MUST NOT 修改；
   - `display_state`（`REAL_BOX | ASSISTED_BOX | PROJECTED_BOX | PROJECTED_POINT |
     PREDICTED_POINT | HIDDEN`）是正交的展示层状态，决定几何形态（框/点/隐藏 + 线型）；
   - 迟滞稳定几何形态：真实框短暂漏检 → 诚实降级 evidence 但保持框（虚线）；连续漏检 →
     渐进降级；synthetic upgrade 需稳定确认；真实 bbox 恢复立即升级；
   - 硬 stop：geometry invalid 禁 synthetic box；无有效 point 且 prediction 超 TTL → HIDDEN；
   - `reset()`：new build / new job / roster reset 必须调用（跨 job 状态隔离）。

2. `ViewPersonScaleProfile`：整场两遍式静态透视尺度模型（Pass1 收集冻结 / Pass2 查询）。
   - 只收真实 target-view bbox（base/guided/accepted refined）；synthetic 绝不回喂；
   - footpoint_y 分桶 robust median + 邻桶 linear interpolation（防逐 tick 跳跃）；
   - `min_total_samples` / `min_samples_per_bin` / physical bounds；样本不足 → None。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

DisplayState = Literal[
    "REAL_BOX",
    "ASSISTED_BOX",
    "PROJECTED_BOX",
    "PROJECTED_POINT",
    "PREDICTED_POINT",
    "HIDDEN",
]

# evidence_type → 展示状态 的冻结映射
EVIDENCE_TO_STATE: dict[str, DisplayState] = {
    "base_observed": "REAL_BOX",
    "guided_observed": "ASSISTED_BOX",
    "refined_observed": "ASSISTED_BOX",
    "cross_view_projected": "PROJECTED_POINT",  # 默认无 bbox；有 bbox 时 builder 升级为 PROJECTED_BOX
    "predicted_only": "PREDICTED_POINT",
    "bootstrap_backfill": "REAL_BOX",  # 回填基于真实检测框（display-only），按真实框展示
}

# 携带真实 target-view bbox 的 evidence（base/guided/refined + 启动回填）。
# 状态机按 REAL_BOX 渲染；bootstrap_backfill 是启动窗口 retrospective 真实观测，
# 其证据判定已由 builder 分支决策链权威产出，状态机只据此落地几何形态（不伪造）。
REAL_BBOX_EVIDENCES = ("base_observed", "guided_observed", "refined_observed", "bootstrap_backfill")


@dataclass(frozen=True)
class DisplayPlan:
    """状态机输出：决定几何形态与 bbox 来源（builder 据此 materialize entity）。"""

    state: DisplayState
    preferred_bbox_source: str = "none"  # real | reanchor | scale_profile | held_presentation | none
    bbox_stale: bool = False
    bbox_age_ms: float | None = None
    # 该 tick 是否仍渲染（HIDDEN 时为 False）
    render: bool = True


@dataclass
class DisplayContext:
    """状态机输入（builder 组装，不改变证据判定）。"""

    now_ms: float
    # raw evidence decision（_decide_entity 的权威输出；None = 不渲染）
    evidence_type: str | None
    # 当前 tick 是否有真实 target-view bbox（base/guided/accepted refined）
    has_real_bbox: bool = False
    # cross_view + bbox 可用（reanchor 或 scale profile）
    has_synthetic_bbox: bool = False
    # 有效 fused/projected point 或 prediction 存在
    has_valid_point: bool = False
    # prediction 是否已超 TTL
    prediction_expired: bool = False
    # geometry 是否有效（禁 synthetic box 的硬 gate）
    geometry_valid: bool = True
    # bbox freshness（单一权威，来自 last_real_observed_ms）
    bbox_age_ms: float | None = None
    bbox_stale: bool = False


@dataclass
class _PlayerDisplayState:
    state: DisplayState = "HIDDEN"
    synthetic_confirm_count: int = 0
    last_synthetic_tick_ts: float | None = None
    last_point_ts: float | None = None
    # 时间连续性（stabilize-multiview-overlay-temporal-continuity D3）：
    last_real_bbox_ts: float | None = None   # hysteresis_grace_ms 计时权威（真实观测）
    last_valid_box_ts: float | None = None   # projected_box_hold_ms 计时权威（最后有效演示 bbox 几何）
    last_state_transition_ts: float | None = None  # 诊断（跨状态转换时间戳）


class OverlayDisplayStateMachine:
    """跨 tick 展示状态机（无 I/O，可单测驱动 tick 序列验证）。

    迟滞语义（stabilize-multiview-overlay-display spec）：
    - `evidence_type` 永远反映真实证据来源（builder 权威），本状态机只决定 display_state；
    - 真实 bbox 恢复 → 立即 REAL_BOX/ASSISTED_BOX（清空 confirm counter）；
    - synthetic upgrade（PROJECTED_POINT → PROJECTED_BOX）需连续 confirm + gap 约束；
    - 短暂漏检（≤ hysteresis_grace_ms）保持框形态（builder 用 last_good/scale profile 补框，
      evidence_type 诚实降级为 cross_view_projected）；
    - 硬 stop：geometry invalid 禁 synthetic box；无 point 且 prediction 超 TTL → HIDDEN；
    - reset()：new build / new job / roster reset 必须调用。
    """

    def __init__(
        self,
        *,
        hysteresis_grace_ms: float = 100.0,
        projected_box_hold_ms: float = 400.0,
        synthetic_upgrade_confirm_ticks: int = 3,
        confirm_max_gap_ms: float = 250.0,
        predicted_ttl_ms: float = 500.0,
    ) -> None:
        self.hysteresis_grace_ms = hysteresis_grace_ms
        self.projected_box_hold_ms = projected_box_hold_ms
        self.synthetic_upgrade_confirm_ticks = max(1, int(synthetic_upgrade_confirm_ticks))
        self.confirm_max_gap_ms = confirm_max_gap_ms
        self.predicted_ttl_ms = predicted_ttl_ms
        self._states: dict[tuple[str, str], _PlayerDisplayState] = {}

    def reset(self) -> None:
        """跨 job 状态隔离：清空全部 (player, view) 状态。"""
        self._states.clear()

    # ---- 主入口 ------------------------------------------------------------

    def step(self, *, player_id: str, view_id: str, ctx: DisplayContext) -> DisplayPlan:
        key = (player_id, view_id)
        st = self._states.setdefault(key, _PlayerDisplayState())
        evidence = ctx.evidence_type
        now = ctx.now_ms

        def _emit(state: DisplayState, **plan) -> DisplayPlan:
            if st.state != state:
                st.last_state_transition_ts = now
                st.state = state
            return DisplayPlan(state=state, **plan)

        # 1) 硬 stop（最高优先级）：prediction 超 TTL 且无有效 point → 必须 HIDDEN
        if ctx.prediction_expired and not ctx.has_valid_point:
            return _emit("HIDDEN", render=False)

        # 2) 真实 bbox 立即升级（次高优先，清空 confirm counter）
        if ctx.has_real_bbox and evidence in REAL_BBOX_EVIDENCES:
            target = EVIDENCE_TO_STATE.get(evidence, "REAL_BOX")
            st.synthetic_confirm_count = 0
            st.last_synthetic_tick_ts = None
            st.last_real_bbox_ts = now
            st.last_valid_box_ts = now  # 真实 bbox 是最新有效几何（作 hold 起点）
            return _emit(
                target,
                preferred_bbox_source="real",
                bbox_stale=False,
                bbox_age_ms=0.0,
            )

        # 3) 真实证据但无当前 bbox（如 weak base 无 bbox）→ 按 evidence 映射
        if evidence in REAL_BBOX_EVIDENCES:
            target = EVIDENCE_TO_STATE.get(evidence, "REAL_BOX")
            st.last_real_bbox_ts = now
            return _emit(target, preferred_bbox_source="none")

        # 4) 硬 stop：geometry invalid → 禁 synthetic box
        if not ctx.geometry_valid:
            target = "PROJECTED_POINT" if ctx.has_valid_point else "HIDDEN"
            st.synthetic_confirm_count = 0
            return _emit(target, preferred_bbox_source="none", render=target != "HIDDEN")

        # 5) cross_view_projected：donor/global 有 projected 位置证据
        if evidence == "cross_view_projected":
            return self._cross_view(ctx, st, now)

        # 6) predicted_only：仅预测，无 projected 位置证据 → 绝不画人体框
        if evidence == "predicted_only":
            if not ctx.prediction_expired:
                return _emit("PREDICTED_POINT", preferred_bbox_source="none")
            return _emit("HIDDEN", render=False)

        # 7) 无证据 → HIDDEN
        return _emit("HIDDEN", render=False)

    def _cross_view(self, ctx: DisplayContext, st: _PlayerDisplayState, now: float) -> DisplayPlan:
        """cross_view 降级链：hysteresis_grace（真实刚丢）+ projected_box_hold（模板瞬失）。

        - 有具体模板（synthetic bbox）→ PROJECTED_BOX；刷新 hold 权威；点→框需稳定确认。
        - 无模板但距最后有效演示几何 ≤ projected_box_hold_ms → 保持 BOX（模板瞬失宽限）。
        - 无模板且真实刚丢 ≤ hysteresis_grace_ms → 保持 BOX（grace 保护）。
        - 否则 → PROJECTED_POINT（不凭空造框）。
        """
        had_box = st.state in ("REAL_BOX", "ASSISTED_BOX", "PROJECTED_BOX")
        within_grace = self._within_ts(st.last_real_bbox_ts, self.hysteresis_grace_ms, now)
        within_hold = self._within_ts(st.last_valid_box_ts, self.projected_box_hold_ms, now)

        if ctx.has_synthetic_bbox:
            st.last_valid_box_ts = now  # 具体模板 → 刷新 hold 权威
            upgrade = had_box or within_grace or self._confirm_synthetic(st, now)
            if not upgrade:
                # 点→框仍处于确认期：保留 confirm 计数继续累计（不 reset）
                return self._point(ctx, st, now)
            return self._plan_box(ctx, st, had_held=False)

        # 无模板：模板瞬失宽限（hold）或真实刚丢（grace）内保持上一份演示几何
        st.synthetic_confirm_count = 0  # 模板消失，确认计数作废
        if within_hold or within_grace:
            if had_box or within_grace:
                return self._plan_box(ctx, st, had_held=True)
        return self._point(ctx, st, now)

    def _plan_box(self, ctx: DisplayContext, st: _PlayerDisplayState, *, had_held: bool) -> DisplayPlan:
        """收敛到 PROJECTED_BOX，并给出 bbox source 提示（template / held presentation）。"""
        if st.state != "PROJECTED_BOX":
            st.last_state_transition_ts = ctx.now_ms
            st.state = "PROJECTED_BOX"
        bbox_source = "held_presentation" if had_held else (
            "reanchor" if not ctx.bbox_stale else "scale_profile"
        )
        return DisplayPlan(
            state="PROJECTED_BOX",
            preferred_bbox_source=bbox_source,
            bbox_stale=ctx.bbox_stale,
            bbox_age_ms=ctx.bbox_age_ms,
        )

    def _point(self, ctx: DisplayContext, st: _PlayerDisplayState, now: float) -> DisplayPlan:
        """收敛到 PROJECTED_POINT / PREDICTED_POINT（footpoint 光圈，不造框）。"""
        target: DisplayState = "PROJECTED_POINT"
        if st.state != target:
            st.last_state_transition_ts = now
            st.state = target
        if ctx.has_valid_point:
            st.last_point_ts = now
        return DisplayPlan(state=target, preferred_bbox_source="none")

    @staticmethod
    def _within_ts(ts: float | None, window_ms: float, now: float) -> bool:
        return ts is not None and (now - ts) <= window_ms

    def _confirm_synthetic(self, st: _PlayerDisplayState, now_ms: float) -> bool:
        """PROJECTED_POINT → PROJECTED_BOX 的稳定确认（连续 + gap 约束）。"""
        if st.last_synthetic_tick_ts is not None:
            gap = now_ms - st.last_synthetic_tick_ts
            if gap > self.confirm_max_gap_ms:
                st.synthetic_confirm_count = 0  # 间隔过长，不算连续
        st.last_synthetic_tick_ts = now_ms
        st.synthetic_confirm_count += 1
        return st.synthetic_confirm_count >= self.synthetic_upgrade_confirm_ticks


# ---------------------------------------------------------------------------
# ViewPersonScaleProfile
# ---------------------------------------------------------------------------


@dataclass
class _ScaleBin:
    widths: list[float] = field(default_factory=list)
    heights: list[float] = field(default_factory=list)

    def median(self) -> tuple[float, float] | None:
        if not self.widths:
            return None
        ws = sorted(self.widths)
        hs = sorted(self.heights)
        return ws[len(ws) // 2], hs[len(hs) // 2]


class ViewPersonScaleProfile:
    """整场两遍式静态透视尺度模型。

    Pass 1：`collect()` 收集该 view 真实 bbox 样本（footpoint_y, width, height），
    然后 `freeze()` 冻结。
    Pass 2：`query(footpoint_y)` 返回插值后的 (width, height)。

    硬约束：
    - 只收真实 target-view bbox（builder 负责只传 base/guided/accepted refined）；
    - synthetic bbox 绝不回喂（builder 负责不调用 collect）；
    - clipped / 极端长宽比 / 尺寸异常样本在 collect 内过滤。
    """

    def __init__(
        self,
        *,
        n_bins: int = 32,
        min_total_samples: int = 50,
        min_samples_per_bin: int = 5,
        frame_height: int = 0,
        min_bbox_side_px: float = 12.0,
        max_bbox_side_px: float = 2000.0,
        min_aspect_ratio: float = 0.15,
        max_aspect_ratio: float = 2.0,
    ) -> None:
        self.n_bins = max(4, int(n_bins))
        self.min_total_samples = min_total_samples
        self.min_samples_per_bin = min_samples_per_bin
        self.frame_height = frame_height
        self.min_bbox_side_px = min_bbox_side_px
        self.max_bbox_side_px = max_bbox_side_px
        self.min_aspect_ratio = min_aspect_ratio
        self.max_aspect_ratio = max_aspect_ratio
        self._bins: dict[int, _ScaleBin] = {}
        self._frozen = False
        self._total_samples = 0

    # ---- Pass 1 -----------------------------------------------------------

    def collect(self, *, footpoint_y: float, width: float, height: float) -> None:
        """收集一个真实 bbox 样本（Pass 1）。冻结后 SHALL NOT 再调用。"""
        if self._frozen:
            raise RuntimeError("ViewPersonScaleProfile.collect() called after freeze()")
        if width <= 0 or height <= 0:
            return
        if width < self.min_bbox_side_px or height < self.min_bbox_side_px:
            return
        if width > self.max_bbox_side_px or height > self.max_bbox_side_px:
            return
        aspect = width / height
        if aspect < self.min_aspect_ratio or aspect > self.max_aspect_ratio:
            return  # 极端长宽比（可能 clip 或错误框）
        bin_index = self._bin_for_y(footpoint_y)
        if bin_index is None:
            return
        self._bins.setdefault(bin_index, _ScaleBin()).widths.append(float(width))
        self._bins[bin_index].heights.append(float(height))
        self._total_samples += 1

    def freeze(self, frame_height: int | None = None) -> None:
        """冻结模型（Pass 1 结束）。此后只能 query。"""
        if frame_height is not None:
            self.frame_height = int(frame_height)
        self._frozen = True

    # ---- Pass 2 -----------------------------------------------------------

    def query(self, footpoint_y: float) -> tuple[float, float] | None:
        """查询 footpoint_y 处插值的 (width, height)；样本不足返回 None。"""
        if not self._frozen:
            raise RuntimeError("ViewPersonScaleProfile.query() called before freeze()")
        if self._total_samples < self.min_total_samples:
            return None
        bin_index = self._bin_for_y(footpoint_y)
        if bin_index is None:
            return None
        # 当前桶足够 → 直接用；不足 → 邻桶 linear interpolation
        cur = self._bins.get(bin_index)
        if cur is not None and len(cur.widths) >= self.min_samples_per_bin:
            return cur.median()  # type: ignore[return-value]
        return self._interpolate(bin_index)

    # ---- 内部 --------------------------------------------------------------

    def _bin_for_y(self, footpoint_y: float) -> int | None:
        if self.frame_height <= 0:
            return None
        y = max(0.0, min(float(footpoint_y), float(self.frame_height) - 1.0))
        return int(y / max(1.0, self.frame_height) * self.n_bins)

    def _interpolate(self, bin_index: int) -> tuple[float, float] | None:
        """邻桶 linear interpolation：用相邻可用桶的 median 线性插值。"""
        lower = self._nearest_bin_with_samples(bin_index, -1)
        upper = self._nearest_bin_with_samples(bin_index, +1)
        if lower is None and upper is None:
            return None
        if lower is None:
            return self._bins[upper].median()  # type: ignore[union-attr]
        if upper is None:
            return self._bins[lower].median()  # type: ignore[union-attr]
        low_m = self._bins[lower].median()
        up_m = self._bins[upper].median()
        if low_m is None or up_m is None:
            return None
        span = max(upper - lower, 1)
        t = (bin_index - lower) / span
        return (
            low_m[0] + (up_m[0] - low_m[0]) * t,
            low_m[1] + (up_m[1] - low_m[1]) * t,
        )

    def _nearest_bin_with_samples(self, start: int, direction: int) -> int | None:
        idx = start + direction
        while 0 <= idx < self.n_bins:
            b = self._bins.get(idx)
            if b is not None and len(b.widths) >= self.min_samples_per_bin:
                return idx
            idx += direction
        return None
