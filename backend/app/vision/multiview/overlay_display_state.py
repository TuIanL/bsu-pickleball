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
    preferred_bbox_source: str = "none"  # real | reanchor | scale_profile | none
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
    last_box_ts: float | None = None
    last_point_ts: float | None = None


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

        # 1) 硬 stop：prediction 超 TTL 且无有效 point → 必须 HIDDEN
        if ctx.prediction_expired and not ctx.has_valid_point:
            st.state = "HIDDEN"
            return DisplayPlan(state="HIDDEN", render=False)

        # 2) 真实 bbox 立即升级（最高优先，清空 confirm counter）
        if ctx.has_real_bbox and evidence in REAL_BBOX_EVIDENCES:
            target = EVIDENCE_TO_STATE.get(evidence, "REAL_BOX")
            st.state = target
            st.synthetic_confirm_count = 0
            st.last_synthetic_tick_ts = None
            st.last_box_ts = ctx.now_ms
            return DisplayPlan(
                state=target,
                preferred_bbox_source="real",
                bbox_stale=False,
                bbox_age_ms=0.0,
            )

        # 3) 真实证据但无当前 bbox（如 weak base 无 bbox）→ 按 evidence 映射
        if evidence in REAL_BBOX_EVIDENCES:
            target = EVIDENCE_TO_STATE.get(evidence, "REAL_BOX")
            st.state = target
            st.last_box_ts = ctx.now_ms
            return DisplayPlan(state=target, preferred_bbox_source="none")

        # 4) 硬 stop：geometry invalid → 禁 synthetic box
        if not ctx.geometry_valid:
            st.state = "PROJECTED_POINT" if ctx.has_valid_point else "HIDDEN"
            st.synthetic_confirm_count = 0
            return DisplayPlan(
                state=st.state,
                preferred_bbox_source="none",
                render=st.state != "HIDDEN",
            )

        # 5) cross_view_projected：donor 有可靠位置
        if evidence == "cross_view_projected":
            # 5a) 有 synthetic bbox（reanchor / scale profile）→ PROJECTED_BOX
            if ctx.has_synthetic_bbox:
                if st.state in ("REAL_BOX", "ASSISTED_BOX"):
                    # 真实框短暂漏检：诚实降级 evidence（builder 已改 evidence_type），
                    # 但保持框形态（虚线），不立即变点
                    st.state = "PROJECTED_BOX"
                    st.last_box_ts = ctx.now_ms
                elif st.state == "PROJECTED_BOX":
                    # 已处于 projected box：保持（几何形态稳定）
                    st.last_box_ts = ctx.now_ms
                else:
                    # HIDDEN / PROJECTED_POINT / PREDICTED_POINT：synthetic upgrade
                    # 需稳定确认（连续 + gap 约束）
                    if self._confirm_synthetic(st, ctx.now_ms):
                        st.state = "PROJECTED_BOX"
                        st.last_box_ts = ctx.now_ms
                    else:
                        st.state = "PROJECTED_POINT"
                return DisplayPlan(
                    state=st.state,
                    preferred_bbox_source=("reanchor" if not ctx.bbox_stale else "scale_profile"),
                    bbox_stale=ctx.bbox_stale,
                    bbox_age_ms=ctx.bbox_age_ms,
                )
            # 5b) 无 synthetic bbox → PROJECTED_POINT
            st.state = "PROJECTED_POINT"
            st.last_point_ts = ctx.now_ms
            st.synthetic_confirm_count = 0
            return DisplayPlan(state="PROJECTED_POINT", preferred_bbox_source="none")

        # 6) predicted_only：prediction 未超 TTL → PREDICTED_POINT
        if evidence == "predicted_only":
            if not ctx.prediction_expired:
                st.state = "PREDICTED_POINT"
                st.last_point_ts = ctx.now_ms
                return DisplayPlan(state="PREDICTED_POINT", preferred_bbox_source="none")
            st.state = "HIDDEN"
            return DisplayPlan(state="HIDDEN", render=False)

        # 7) 无证据 → HIDDEN
        st.state = "HIDDEN"
        return DisplayPlan(state="HIDDEN", render=False)

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
