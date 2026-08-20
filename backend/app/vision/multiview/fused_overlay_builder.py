"""FusedPlayerOverlayBuilder —— post-fusion 球员叠加层的核心构建器。

按**分支决策链**（非机械排序）为每个 (Player_N, canonical_tick) 判定参考画面
的展示证据（spec `multiview-fused-player-overlay`）：

```text
reference view 有 F0 strong observation（origin=base/guided_roi）
    → base_observed / guided_observed
否则 final_source == refined_f1 且该 view/tick 有 accepted recovered observation
    → refined_observed
否则 reference view 有弱 F0 observation
    → base_observed / guided_observed
否则 donor view 有真实 observation 且 fused sample 非 predicted/conflict 且 geometry 有效
    → cross_view_projected（投影 footpoint + reanchor bbox）
否则存在短时 predicted sample 且 TTL 未过
    → predicted_only（淡化光圈）
否则
    → 不渲染
```

包含：
- `classify_f0_origin()`：F0 origin provenance mapper（系统实际命名 `guided_roi`，
  `joint_types.py:12`；禁止 builder 内字符串直判 `"guided"`）；
- `TargetViewBBoxMemory`：仅合格真实观测刷新的 bbox 记忆 + 纯平移 reanchor。

**只读消费**：builder 绝不反写 tracker / association / metrics / roster。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.vision.multiview.fused_overlay_bundle import JointOverlayEvidenceBundle
from app.vision.multiview.fused_overlay_projection import (
    TargetImageProjection,
    canonical_to_target_image,
)
from app.vision.multiview.fused_overlay_types import (
    FusedPlayerOverlayFrame,
    FusedPlayerOverlayPlayer,
)
from app.vision.multiview.overlay_display_state import (
    DisplayContext,
    DisplayPlan,
    OverlayDisplayStateMachine,
    ViewPersonScaleProfile,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# F0 origin provenance mapper
# ---------------------------------------------------------------------------


def classify_f0_origin(origin: str | None) -> str:
    """F0 detection origin → 展示证据类型（base/guided 分支）。

    `DetectionOrigin = Literal["base", "guided_roi", "offline_refinement"]`
    （`joint_types.py:12`）。`guided_roi → guided_observed`；`base →
    base_observed`；未知 origin 按 base 兜底并记录 warning。
    """
    if origin == "guided_roi":
        return "guided_observed"
    if origin == "base":
        return "base_observed"
    if origin != "base" and origin is not None:
        logger.warning("classify_f0_origin: unknown origin %r, falling back to base_observed", origin)
    return "base_observed"


# ---------------------------------------------------------------------------
# Builder 配置
# ---------------------------------------------------------------------------


@dataclass
class OverlayBuilderConfig:
    """fused overlay builder 的可配门限（V1 默认值，visual acceptance 后校准）。"""

    # F0 strong observation 判定：quality（= detector confidence）>= 此值
    strong_quality_threshold: float = 0.5
    # cross_view donor view 的观测质量门限
    donor_quality_threshold: float = 0.5
    # donor 观测与当前 tick 的最大时间差（ms）—— recency gate
    donor_recency_ms: float = 500.0
    # bbox 记忆 TTL（ms）：超过后从 reanchor bbox 降级为 footpoint 光圈
    bbox_memory_ttl_ms: float = 2000.0
    # bbox 记忆 grace（ms）：ttl 过期后、ttl+grace 内仍允许 reanchor（stale 标记）
    bbox_memory_grace_ms: float = 500.0
    # predicted_only 的预测 TTL（ms）：超过后不渲染
    predicted_ttl_ms: float = 500.0
    # 合格真实 bbox 的最小/最大宽高（px），超出视为错误框，不刷新记忆
    min_bbox_side_px: float = 12.0
    max_bbox_side_px: float = 2000.0
    # ---- 展示稳定性（stabilize-multiview-overlay-display）----
    # 迟滞状态机：真实框短暂漏检的保持窗口（ms）
    hysteresis_grace_ms: float = 100.0
    # synthetic projected box 的保持窗口（ms）
    projected_box_hold_ms: float = 400.0
    # synthetic upgrade（PROJECTED_POINT → PROJECTED_BOX）需连续确认帧数
    synthetic_upgrade_confirm_ticks: int = 3
    # synthetic 确认的最大间隔（ms），超过不算连续
    confirm_max_gap_ms: float = 250.0
    # view scale profile：分桶数 / 最小样本量 / 每桶最小样本量
    scale_profile_bins: int = 32
    scale_profile_min_total_samples: int = 50
    scale_profile_min_samples_per_bin: int = 5


# ---------------------------------------------------------------------------
# TargetViewBBoxMemory
# ---------------------------------------------------------------------------


@dataclass
class BBoxMemoryEntry:
    """(global_player_id, target_view_id) 的最近合格真实 bbox。"""

    bbox: tuple[float, float, float, float]
    footpoint: tuple[float, float]
    width: float
    height: float
    last_real_observed_ms: float


class TargetViewBBoxMemory:
    """按 (global_player_id, target_view_id) 维护最近合格真实 bbox。

    仅允许合格观测刷新（bbox 几何合法 + quality 过门 + width/height 在合理
    范围），防止单个错误框污染后续 cross-view projected bbox。
    """

    def __init__(self, config: OverlayBuilderConfig) -> None:
        self._config = config
        self._entries: dict[tuple[str, str], BBoxMemoryEntry] = {}

    def is_qualifying_bbox(
        self,
        bbox: tuple[float, float, float, float] | None,
        quality: float,
    ) -> bool:
        if bbox is None or len(bbox) != 4:
            return False
        x1, y1, x2, y2 = (float(v) for v in bbox)
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            return False
        if width < self._config.min_bbox_side_px or height < self._config.min_bbox_side_px:
            return False
        if width > self._config.max_bbox_side_px or height > self._config.max_bbox_side_px:
            return False
        if quality < self._config.strong_quality_threshold:
            return False
        return True

    def update(
        self,
        *,
        global_player_id: str,
        view_id: str,
        bbox: tuple[float, float, float, float] | None,
        quality: float,
        observed_ms: float | None,
    ) -> None:
        """仅合格真实观测（base/guided/refined）刷新记忆。"""
        if not self.is_qualifying_bbox(bbox, quality):
            return
        x1, y1, x2, y2 = (float(v) for v in bbox)
        footpoint = ((x1 + x2) / 2.0, y2)
        self._entries[(global_player_id, view_id)] = BBoxMemoryEntry(
            bbox=(x1, y1, x2, y2),
            footpoint=footpoint,
            width=x2 - x1,
            height=y2 - y1,
            last_real_observed_ms=observed_ms if observed_ms is not None else 0.0,
        )

    def reanchor(
        self,
        *,
        global_player_id: str,
        view_id: str,
        new_footpoint: tuple[float, float],
        now_ms: float,
    ) -> BBoxMemoryEntry | None:
        """以新投影 footpoint 为锚点纯平移重建 bbox；过期返回 None（降级光圈）。

        V1 不做透视缩放：width/height 与最近合格真实 bbox 完全一致。
        grace 语义（stabilize-multiview-overlay-display）：`bbox_memory_ttl_ms`
        过期后、`ttl + bbox_memory_grace_ms` 内仍返回 reanchor 结果，
        调用方以 `stale` 标记淡化；超过 grace 返回 None。
        """
        entry = self._entries.get((global_player_id, view_id))
        if entry is None:
            return None
        age = now_ms - entry.last_real_observed_ms
        if age > self._config.bbox_memory_ttl_ms + self._config.bbox_memory_grace_ms:
            return None
        new_x1 = new_footpoint[0] - entry.width / 2.0
        new_x2 = new_footpoint[0] + entry.width / 2.0
        new_y1 = new_footpoint[1] - entry.height
        new_y2 = new_footpoint[1]
        return BBoxMemoryEntry(
            bbox=(new_x1, new_y1, new_x2, new_y2),
            footpoint=new_footpoint,
            width=entry.width,
            height=entry.height,
            last_real_observed_ms=entry.last_real_observed_ms,
        )

    def freshness(self, *, global_player_id: str, view_id: str, now_ms: float) -> tuple[bool, float | None]:
        """返回 (stale, age_ms)：记忆是否过期（ttl+grace 内）与 last real observed 距今。

        单一 freshness 权威：状态机只消费本方法结果，不维护独立过期判定。
        """
        entry = self._entries.get((global_player_id, view_id))
        if entry is None:
            return False, None
        age = now_ms - entry.last_real_observed_ms
        return age > self._config.bbox_memory_ttl_ms, age


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class FusedPlayerOverlayBuilder:
    """按分支决策链生成 `multiview-fused-player-overlay.v1` frames。"""

    def __init__(self, config: OverlayBuilderConfig | None = None) -> None:
        self.config = config or OverlayBuilderConfig()
        self.bbox_memory = TargetViewBBoxMemory(self.config)
        # 展示稳定性：跨 tick 迟滞状态机 + view scale profile（整场两遍式）
        self.display_state_machine = OverlayDisplayStateMachine(
            hysteresis_grace_ms=self.config.hysteresis_grace_ms,
            projected_box_hold_ms=self.config.projected_box_hold_ms,
            synthetic_upgrade_confirm_ticks=self.config.synthetic_upgrade_confirm_ticks,
            confirm_max_gap_ms=self.config.confirm_max_gap_ms,
            predicted_ttl_ms=self.config.predicted_ttl_ms,
        )
        self._scale_profiles: dict[str, ViewPersonScaleProfile] = {}

    # ---- 决策辅助 ----------------------------------------------------------

    def _f0_view_state(self, bundle: JointOverlayEvidenceBundle, tick, view_id: str, gid: str):
        """从 F0 snapshot 读取 (gid, view_id) 的 tick 观测状态。"""
        return tick.state_for(gid, view_id) if tick is not None else None

    def _is_strong(self, state) -> bool:
        return (
            state is not None
            and state.observed
            and (state.quality or 0.0) >= self.config.strong_quality_threshold
            and state.origin in {"base", "guided_roi"}
        )

    def _is_weak(self, state) -> bool:
        return (
            state is not None
            and state.observed
            and not self._is_strong(state)
            and state.origin in {"base", "guided_roi"}
        )

    def _donor_candidate(
        self, bundle: JointOverlayEvidenceBundle, tick, gid: str, now_ms: float
    ) -> tuple[str, Any] | None:
        """寻找当前 tick 真实观测同一 Player 的可信 donor view。"""
        best: tuple[str, Any] | None = None
        for view_id in bundle.view_ids:
            if view_id == bundle.reference_view_id:
                continue
            donor_state = self._f0_view_state(bundle, tick, view_id, gid)
            if donor_state is None or not donor_state.observed:
                continue
            if donor_state.origin not in {"base", "guided_roi"}:
                continue
            if (donor_state.quality or 0.0) < self.config.donor_quality_threshold:
                continue
            # recency gate：donor 观测时间与当前 canonical tick 时间差
            donor_ms = donor_state.mapped_take_timestamp_ms
            if donor_ms is None or abs(now_ms - donor_ms) > self.config.donor_recency_ms:
                continue
            if best is None or (donor_state.quality or 0.0) > (best[1].quality or 0.0):
                best = (view_id, donor_state)
        return best

    def _fused_is_usable(self, bundle: JointOverlayEvidenceBundle, gid: str, frame_index: int) -> bool:
        """final fused sample 非 predicted/conflict 才可用于 cross_view。"""
        sample = bundle.fused_sample_for(gid, frame_index)
        if sample is None:
            return False
        status = str(sample.get("fusion_status", "unknown"))
        return status not in {"predicted", "conflict"}

    # ---- 主入口 ------------------------------------------------------------

    def build(
        self,
        *,
        bundle: JointOverlayEvidenceBundle,
        expected_player_count: int = 4,
    ) -> list[FusedPlayerOverlayFrame]:
        """遍历 canonical ticks 生成 overlay frames。

        Pass 1：整场收集该 view 真实 bbox → 冻结 ViewPersonScaleProfile；
        Pass 2：逐 tick 生成 overlay（查询已冻结 profile）。
        """
        frames: list[FusedPlayerOverlayFrame] = []
        snapshot = bundle.f0_snapshot
        if snapshot is None:
            logger.warning("fused overlay builder: f0_snapshot is None, no frames generated")
            return frames

        # 跨 job 状态隔离：每次 build 重置状态机（new build / new job / roster reset）
        self.display_state_machine.reset()

        # ---- Pass 1：收集 view scale profile（只收真实 bbox）----
        self._build_scale_profiles(snapshot, bundle)

        for tick in snapshot.ticks:
            frame_index = tick.reference_frame_index
            now_ms = tick.canonical_timestamp_ms
            players: list[FusedPlayerOverlayPlayer] = []
            for gid in sorted(snapshot.global_player_ids):
                entity = self._decide_display_entity(
                    bundle=bundle, tick=tick, gid=gid, frame_index=frame_index, now_ms=now_ms
                )
                if entity is not None:
                    players.append(entity)
                if len(players) >= expected_player_count:
                    break
            frames.append(
                FusedPlayerOverlayFrame(
                    frame_index=frame_index,
                    timestamp_seconds=now_ms / 1000.0,
                    players=players,
                )
            )
        return frames

    def _build_scale_profiles(self, snapshot, bundle: JointOverlayEvidenceBundle) -> None:
        """Pass 1：整场收集该 view 真实 bbox 样本并冻结 scale profile。

        只收 `base/guided_roi/accepted refined` 的真实 target-view bbox；
        synthetic bbox（reanchor / scale profile）绝不回喂。
        """
        self._scale_profiles = {}
        geometry = bundle.geometry_for(bundle.reference_view_id)
        frame_height = int(geometry.frame_height) if geometry is not None else 0
        profile = ViewPersonScaleProfile(
            n_bins=self.config.scale_profile_bins,
            min_total_samples=self.config.scale_profile_min_total_samples,
            min_samples_per_bin=self.config.scale_profile_min_samples_per_bin,
            frame_height=frame_height,
            min_bbox_side_px=self.config.min_bbox_side_px,
            max_bbox_side_px=self.config.max_bbox_side_px,
        )
        for tick in snapshot.ticks:
            for gid in snapshot.global_player_ids:
                state = tick.state_for(gid, bundle.reference_view_id)
                if state is None or not state.observed:
                    continue
                if state.origin not in {"base", "guided_roi", "offline_refinement"}:
                    continue  # 只收真实 target-view bbox
                bbox = state.bbox
                if bbox is None or len(bbox) != 4:
                    continue
                footpoint_y = float(bbox[3])
                width = float(bbox[2]) - float(bbox[0])
                height = float(bbox[3]) - float(bbox[1])
                profile.collect(footpoint_y=footpoint_y, width=width, height=height)
        profile.freeze(frame_height=frame_height)
        self._scale_profiles[bundle.reference_view_id] = profile

    def _decide_display_entity(
        self,
        *,
        bundle: JointOverlayEvidenceBundle,
        tick,
        gid: str,
        frame_index: int,
        now_ms: float,
    ) -> FusedPlayerOverlayPlayer | None:
        """展示层包装器：raw evidence（_decide_entity 权威）→ 状态机 → DisplayPlan → entity。

        `_decide_entity` 保持证据判定权威（evidence_type 永不伪造）；
        状态机只决定 display_state（几何形态），并驱动 bbox fallback 来源。
        """
        raw = self._decide_entity(
            bundle=bundle, tick=tick, gid=gid, frame_index=frame_index, now_ms=now_ms
        )
        player_id = bundle.player_id_for(gid)
        if not (player_id.startswith("Player_") and player_id[len("Player_"):].isdigit()):
            return raw  # 身份异常交给原逻辑（返回 None）

        reference_view_id = bundle.reference_view_id
        # ---- 组装 display context（不改变证据判定）----
        fused_position = bundle.fused_position_for(gid, frame_index)
        geometry = bundle.geometry_for(reference_view_id)
        geometry_valid = bool(
            geometry is not None
            and geometry.orientation is not None
            and geometry.inverse_homography is not None
            and geometry.frame_width > 0
            and geometry.frame_height > 0
        )
        projection = None
        if fused_position is not None and geometry is not None:
            projection = canonical_to_target_image(
                canonical_position=fused_position,
                orientation=geometry.orientation,
                inverse_homography=geometry.inverse_homography,
                frame_width=geometry.frame_width,
                frame_height=geometry.frame_height,
            )
            if not projection.projection_valid:
                projection = None
        has_valid_point = projection is not None
        sample = bundle.fused_sample_for(gid, frame_index)
        prediction_expired = False
        if sample is not None and str(sample.get("fusion_status", "")) == "predicted":
            last_real_ms = bundle.last_real_observed_ms.get((gid, reference_view_id))
            prediction_expired = last_real_ms is not None and (now_ms - last_real_ms) > self.config.predicted_ttl_ms
        # bbox freshness（单一权威）
        stale, age_ms = self.bbox_memory.freshness(
            global_player_id=gid, view_id=reference_view_id, now_ms=now_ms
        )
        # cross_view 场景：是否有 synthetic bbox 可用（reanchor 或 scale profile）
        evidence_type = raw.evidence_type if raw is not None else None
        has_real_bbox = (
            evidence_type in ("base_observed", "guided_observed", "refined_observed", "bootstrap_backfill")
            and raw is not None
            and raw.bbox is not None
        )
        has_synthetic_bbox = False
        if evidence_type == "cross_view_projected" and projection is not None:
            reanchored = self.bbox_memory.reanchor(
                global_player_id=gid,
                view_id=reference_view_id,
                new_footpoint=projection.image_footpoint,
                now_ms=now_ms,
            )
            profile = self._scale_profiles.get(reference_view_id)
            scaled = None
            if profile is not None:
                scaled = profile.query(projection.image_footpoint[1])
            has_synthetic_bbox = reanchored is not None or scaled is not None

        ctx = DisplayContext(
            now_ms=now_ms,
            evidence_type=evidence_type,
            has_real_bbox=has_real_bbox,
            has_synthetic_bbox=has_synthetic_bbox,
            has_valid_point=has_valid_point,
            prediction_expired=prediction_expired,
            geometry_valid=geometry_valid,
            bbox_age_ms=age_ms,
            bbox_stale=stale,
        )
        plan = self.display_state_machine.step(player_id=player_id, view_id=reference_view_id, ctx=ctx)

        if not plan.render:
            return None

        # ---- 按 DisplayPlan materialize ----
        if raw is not None and plan.state in ("REAL_BOX", "ASSISTED_BOX") and has_real_bbox:
            entity = raw.model_copy(update={"display_state": plan.state})
            return entity

        if evidence_type == "cross_view_projected" and projection is not None:
            return self._build_cross_view_stable(
                gid=gid,
                player_id=player_id,
                donor_view=raw.donor_view if raw is not None else None,
                donor_quality=raw.donor_quality if raw is not None else 0.0,
                projection=projection,
                now_ms=now_ms,
                reference_view_id=reference_view_id,
                plan=plan,
            )

        if raw is not None:
            return raw.model_copy(update={"display_state": plan.state})
        return None

    def _decide_entity(
        self,
        *,
        bundle: JointOverlayEvidenceBundle,
        tick,
        gid: str,
        frame_index: int,
        now_ms: float,
    ) -> FusedPlayerOverlayPlayer | None:
        """分支决策链：返回展示实体或 None（不渲染）。"""
        player_id = bundle.player_id_for(gid)
        if not player_id.startswith("Player_"):
            logger.warning("fused overlay: non-canonical public player id %r for %r", player_id, gid)
            return None

        reference_state = self._f0_view_state(bundle, tick, bundle.reference_view_id, gid)

        # 1) F0 strong observation → base/guided
        if self._is_strong(reference_state):
            return self._build_real_observation(
                gid=gid, player_id=player_id, state=reference_state, evidence=classify_f0_origin(
                    reference_state.origin
                ), now_ms=now_ms, view_id=bundle.reference_view_id,
            )

        # 2) accepted F1 recovered observation（final_source == refined_f1）
        if bundle.has_recovered_evidence():
            recovered = bundle.recovered_for(gid, tick.canonical_tick)
            if recovered is not None and recovered.view_id == bundle.reference_view_id:
                return self._build_recovered(
                    gid=gid, player_id=player_id, recovered=recovered, now_ms=now_ms
                )

        # 3) F0 weak observation → base/guided（接受较低质量）
        if self._is_weak(reference_state):
            return self._build_real_observation(
                gid=gid, player_id=player_id, state=reference_state, evidence=classify_f0_origin(
                    reference_state.origin
                ), now_ms=now_ms, view_id=bundle.reference_view_id,
            )

        # 4) cross_view_projected：donor 真实观测 + fused 位置可信 + geometry 有效
        donor = self._donor_candidate(bundle, tick, gid, now_ms)
        if donor is not None and self._fused_is_usable(bundle, gid, frame_index):
            fused_position = bundle.fused_position_for(gid, frame_index)
            if fused_position is not None:
                geometry = bundle.geometry_for(bundle.reference_view_id)
                if geometry is not None:
                    projection = canonical_to_target_image(
                        canonical_position=fused_position,
                        orientation=geometry.orientation,
                        inverse_homography=geometry.inverse_homography,
                        frame_width=geometry.frame_width,
                        frame_height=geometry.frame_height,
                    )
                    if projection.projection_valid:
                        return self._build_cross_view(
                            gid=gid,
                            player_id=player_id,
                            donor_view=donor[0],
                            donor_state=donor[1],
                            projection=projection,
                            now_ms=now_ms,
                            reference_view_id=bundle.reference_view_id,
                        )

        # 5) predicted_only：短时预测 + TTL 未过
        sample = bundle.fused_sample_for(gid, frame_index)
        if sample is not None and str(sample.get("fusion_status", "")) == "predicted":
            last_real_ms = bundle.last_real_observed_ms.get((gid, bundle.reference_view_id))
            if last_real_ms is None or now_ms - last_real_ms <= self.config.predicted_ttl_ms:
                fused_position = bundle.fused_position_for(gid, frame_index)
                geometry = bundle.geometry_for(bundle.reference_view_id)
                projection = None
                if fused_position is not None and geometry is not None:
                    projection = canonical_to_target_image(
                        canonical_position=fused_position,
                        orientation=geometry.orientation,
                        inverse_homography=geometry.inverse_homography,
                        frame_width=geometry.frame_width,
                        frame_height=geometry.frame_height,
                    )
                return self._build_predicted_only(
                    gid=gid,
                    player_id=player_id,
                    sample=sample,
                    projection=projection if projection is not None and projection.projection_valid else None,
                )

        # 7) bootstrap_backfill：启动窗口内 retrospective 真实观测（最低优先级兜底）
        #    仅当五级证据全缺、且本 (Player_N, frame) 存在回填真实观测时启用；
        #    绝不覆盖更高级别证据（前 6 步已优先返回），也绝不编造（builder 只产出真实观测）。
        bb = bundle.bootstrap_for(player_id, frame_index)
        if bb is not None:
            bbox = bb.bbox  # reference image 真实检测框
            footpoint = (
                [(bbox[0] + bbox[2]) / 2.0, bbox[3]]
                if bbox is not None and len(bbox) == 4
                else None
            )
            canon = bb.canonical_court_position_ft
            return FusedPlayerOverlayPlayer(
                player_id=player_id,
                label=_player_label(player_id),
                bbox=list(bbox) if bbox is not None else None,
                footpoint=footpoint,
                evidence_type="bootstrap_backfill",
                source_confidence=round(float(bb.source_confidence or 0.0), 4),
                overlay_confidence=round(float(bb.source_confidence or 0.0), 4),
                canonical_court_position_ft=(
                    [float(canon[0]), float(canon[1])] if canon is not None and len(canon) == 2 else None
                ),
            )

        # 6) 全部证据不足 → 不渲染
        return None

    # ---- 各 evidence 分支的实体构造 -----------------------------------------

    def _build_real_observation(
        self,
        *,
        gid: str,
        player_id: str,
        state,
        evidence: str,
        now_ms: float,
        view_id: str,
    ) -> FusedPlayerOverlayPlayer:
        bbox = tuple(float(v) for v in state.bbox) if state.bbox is not None else None
        footpoint = None
        if bbox is not None and len(bbox) == 4:
            footpoint = [(bbox[0] + bbox[2]) / 2.0, bbox[3]]
            self.bbox_memory.update(
                global_player_id=gid,
                view_id=view_id,
                bbox=bbox,
                quality=state.quality or 0.0,
                observed_ms=state.mapped_take_timestamp_ms,
            )
        return FusedPlayerOverlayPlayer(
            player_id=player_id,
            label=_player_label(player_id),
            bbox=list(bbox) if bbox else None,
            footpoint=footpoint,
            evidence_type=evidence,  # type: ignore[arg-type]
            source_confidence=round(float(state.detector_confidence or 0.0), 4),
            overlay_confidence=round(float(state.quality or 0.0), 4),
            bbox_source="last_good_bbox_reanchored" if bbox is not None else "none",
        )

    def _build_recovered(
        self, *, gid: str, player_id: str, recovered, now_ms: float
    ) -> FusedPlayerOverlayPlayer:
        bbox = tuple(float(v) for v in recovered.bbox) if recovered.bbox is not None else None
        footpoint = None
        if bbox is not None and len(bbox) == 4:
            footpoint = [(bbox[0] + bbox[2]) / 2.0, bbox[3]]
            self.bbox_memory.update(
                global_player_id=gid,
                view_id=recovered.view_id,
                bbox=bbox,
                quality=float(recovered.confidence or 0.0),
                observed_ms=recovered.mapped_take_timestamp_ms,
            )
        return FusedPlayerOverlayPlayer(
            player_id=player_id,
            label=_player_label(player_id),
            bbox=list(bbox) if bbox else None,
            footpoint=footpoint,
            evidence_type="refined_observed",
            source_confidence=round(float(recovered.confidence or 0.0), 4),
            overlay_confidence=round(float(recovered.confidence or 0.0), 4),
            bbox_source="last_good_bbox_reanchored" if bbox is not None else "none",
            provenance="offline_refinement",
        )

    def _build_cross_view(
        self,
        *,
        gid: str,
        player_id: str,
        donor_view: str,
        donor_state,
        projection: TargetImageProjection,
        now_ms: float,
        reference_view_id: str,
    ) -> FusedPlayerOverlayPlayer:
        footpoint = [projection.image_footpoint[0], projection.image_footpoint[1]]
        bbox = None
        bbox_source = "none"
        reanchored = self.bbox_memory.reanchor(
            global_player_id=gid,
            view_id=reference_view_id,
            new_footpoint=projection.image_footpoint,
            now_ms=now_ms,
        )
        if reanchored is not None:
            bbox = list(reanchored.bbox)
            bbox_source = "last_good_bbox_reanchored"
        donor_quality = float(getattr(donor_state, "quality", 0.0) or 0.0)
        return FusedPlayerOverlayPlayer(
            player_id=player_id,
            label=_player_label(player_id),
            bbox=bbox,
            footpoint=footpoint,
            evidence_type="cross_view_projected",
            source_confidence=round(donor_quality, 4),
            overlay_confidence=round(donor_quality, 4),
            donor_quality=round(donor_quality, 4),
            donor_view=donor_view,
            bbox_source=bbox_source,
        )

    def _build_cross_view_stable(
        self,
        *,
        gid: str,
        player_id: str,
        donor_view: str | None,
        donor_quality: float,
        projection: TargetImageProjection,
        now_ms: float,
        reference_view_id: str,
        plan: DisplayPlan,
    ) -> FusedPlayerOverlayPlayer:
        """跨摄补全的稳定版：按 DisplayPlan 决定 bbox 来源（fallback 层级 + 状态标注）。

        bbox fallback（freshness 优先）：
        1. fresh personal memory（age ≤ ttl）→ last_good_bbox_reanchored
        2. view scale profile（当前 footpoint 深度）→ view_scale_profiled
        3. stale personal memory grace（age ≤ ttl+grace，仅 profile 不可用）→ stale reanchor
        4. footpoint 光圈
        """
        footpoint = [projection.image_footpoint[0], projection.image_footpoint[1]]
        bbox = None
        bbox_source: str = "none"
        stale = plan.bbox_stale
        age_ms = plan.bbox_age_ms

        reanchored = self.bbox_memory.reanchor(
            global_player_id=gid,
            view_id=reference_view_id,
            new_footpoint=projection.image_footpoint,
            now_ms=now_ms,
        )
        profile = self._scale_profiles.get(reference_view_id)
        scaled = None
        if profile is not None:
            scaled = profile.query(projection.image_footpoint[1])
        if reanchored is not None and not stale:
            # fresh personal memory（age ≤ ttl）
            bbox = list(reanchored.bbox)
            bbox_source = "last_good_bbox_reanchored"
        elif scaled is not None:
            # view scale profile（当前 footpoint 深度估计，优先于 stale memory）
            cx = projection.image_footpoint[0]
            cy = projection.image_footpoint[1]
            w, h = scaled
            bbox = [cx - w / 2.0, cy - h, cx + w / 2.0, cy]
            bbox_source = "view_scale_profiled"
        elif reanchored is not None:
            # stale personal memory grace（仅 profile 不可用时兜底）
            bbox = list(reanchored.bbox)
            bbox_source = "last_good_bbox_reanchored"
            stale = True

        return FusedPlayerOverlayPlayer(
            player_id=player_id,
            label=_player_label(player_id),
            bbox=bbox,
            footpoint=footpoint,
            evidence_type="cross_view_projected",
            source_confidence=round(float(donor_quality or 0.0), 4),
            overlay_confidence=round(float(donor_quality or 0.0), 4),
            donor_quality=round(float(donor_quality or 0.0), 4),
            donor_view=donor_view,
            bbox_source=bbox_source,  # type: ignore[arg-type]
            display_state=plan.state,
            bbox_stale=stale,
            bbox_age_ms=age_ms,
        )

    def _build_predicted_only(
        self,
        *,
        gid: str,
        player_id: str,
        sample: dict[str, Any],
        projection: TargetImageProjection | None,
    ) -> FusedPlayerOverlayPlayer:
        # predicted_only 只渲染 footpoint / halo（淡化），不渲染人体框
        footpoint = None
        if projection is not None:
            footpoint = [projection.image_footpoint[0], projection.image_footpoint[1]]
        return FusedPlayerOverlayPlayer(
            player_id=player_id,
            label=_player_label(player_id),
            bbox=None,
            footpoint=footpoint,
            evidence_type="predicted_only",
            source_confidence=0.0,
            overlay_confidence=0.0,
            bbox_source="none",
        )


def _player_label(player_id: str) -> str:
    """Player_3 → P3。"""
    if player_id.startswith("Player_") and player_id[len("Player_"):].isdigit():
        return f"P{int(player_id[len('Player_'):])}"
    return player_id
