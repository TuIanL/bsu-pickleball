"""击球与弹地事件仲裁（ball_event_resolver）。

仲裁层解决同一时间窗口内击球候选与弹地候选的冲突，不武断分类。
职责收敛为两阶段（设计 D1 / D2，不变量 I7 / I8）：

  - `prefilter()`：弹地抑制的**唯一权威**。使用有符号非对称时间窗口
    （bounce 前 0.07s / 后 0.10s）判定 suppressed；Detector 不参与弹地抑制。
  - `finalize()`：结合球员归属（PlayerAttribution）输出最终事件。
    suppressed / rejected 候选只进入 diagnostics，不生成正式边界事件。

`BallContactEventDetector` 只输出纯球侧运动突变候选，不再读取 bounce_events。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.vision.pickleball_game_analysis.ball_contact_event_detector import HitCandidate
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    EventSource,
    OwnershipStatus,
    PlayerAttribution,
    TrajectoryEvent,
    TrajectoryEventType,
)
from app.vision.pickleball_game_analysis.schemas import BounceEvent, Point2D

PrefilterStatus = Literal["survived", "suppressed", "rejected"]


@dataclass(frozen=True)
class ResolverConfig:
    """事件仲裁超参数（时间语义，兼容不同帧率）。"""

    bounce_suppress_before_sec: float = 0.07  # 弹地前抑制窗口（秒）
    bounce_suppress_after_sec: float = 0.10  # 弹地后抑制窗口（秒）
    bounce_suppress_confidence: float = 0.6  # 弹地置信度高于此则抑制击球


@dataclass(frozen=True)
class PrefilteredHitCandidate:
    """通过/未通过 prefilter 的击球候选（唯一带 prefilter 状态的载体）。"""

    candidate_id: str
    frame_index: int
    timestamp_sec: float
    image_xy: Point2D | None
    ball_evidence_confidence: float
    prefilter_status: PrefilterStatus
    prefilter_reason: str | None = None
    conflicting_bounce_event_id: str | None = None
    diagnostics: dict = field(default_factory=dict)


class BallEventResolver:
    """把击球候选与弹跳事件仲裁为统一的飞行段边界事件。"""

    def __init__(self, config: ResolverConfig | None = None) -> None:
        self.config = config or ResolverConfig()

    def prefilter(
        self,
        candidates: list[HitCandidate],
        bounce_events: list[BounceEvent] | None = None,
        fps: float = 30.0,
    ) -> list[PrefilteredHitCandidate]:
        """弹地抑制唯一权威（I7）：输出全部候选的 prefilter 状态。

        suppressed / rejected 候选只进 diagnostics，由调用方记录，
        不进入 finalize 的正式事件。
        """
        if fps <= 0:
            fps = 30.0
        results: list[PrefilteredHitCandidate] = []
        for index, candidate in enumerate(candidates):
            if candidate.status == "rejected_hit":
                results.append(
                    PrefilteredHitCandidate(
                        candidate_id=f"hit-cand-{index + 1}",
                        frame_index=candidate.frame_index,
                        timestamp_sec=candidate.timestamp_sec,
                        image_xy=candidate.image_xy,
                        ball_evidence_confidence=round(candidate.confidence, 3),
                        prefilter_status="rejected",
                        prefilter_reason=candidate.rejection_reason or "rejected_by_detector",
                        diagnostics=dict(candidate.diagnostics),
                    )
                )
                continue

            if candidate.status != "confirmed_hit":
                # 检测器 refractory 去重后未入选的重复候选：不进正式事件
                results.append(
                    PrefilteredHitCandidate(
                        candidate_id=f"hit-cand-{index + 1}",
                        frame_index=candidate.frame_index,
                        timestamp_sec=candidate.timestamp_sec,
                        image_xy=candidate.image_xy,
                        ball_evidence_confidence=round(candidate.confidence, 3),
                        prefilter_status="rejected",
                        prefilter_reason="refractory_deduplicated",
                        diagnostics=dict(candidate.diagnostics),
                    )
                )
                continue

            conflicting = self._conflicting_bounce(candidate, bounce_events or [])
            if conflicting is not None:
                results.append(
                    PrefilteredHitCandidate(
                        candidate_id=f"hit-cand-{index + 1}",
                        frame_index=candidate.frame_index,
                        timestamp_sec=candidate.timestamp_sec,
                        image_xy=candidate.image_xy,
                        ball_evidence_confidence=round(candidate.confidence, 3),
                        prefilter_status="suppressed",
                        prefilter_reason="within_bounce_suppression_window",
                        conflicting_bounce_event_id=conflicting.event_id,
                        diagnostics={
                            "bounce_event_id": conflicting.event_id,
                            "bounce_confidence": round(conflicting.confidence, 3),
                            "delta_sec": round(candidate.timestamp_sec - conflicting.timestamp_sec, 6),
                        },
                    )
                )
                continue

            results.append(
                PrefilteredHitCandidate(
                    candidate_id=f"hit-cand-{index + 1}",
                    frame_index=candidate.frame_index,
                    timestamp_sec=candidate.timestamp_sec,
                    image_xy=candidate.image_xy,
                    ball_evidence_confidence=round(candidate.confidence, 3),
                    prefilter_status="survived",
                    diagnostics=dict(candidate.diagnostics),
                )
            )
        return results

    def _conflicting_bounce(
        self,
        candidate: HitCandidate,
        bounce_events: list[BounceEvent],
    ) -> BounceEvent | None:
        """有符号非对称时间窗口内的高可信弹地（I8）。

        只抑制 `[-before_sec, +after_sec]` 内的候选；bounce 后超出容差的
        候选不得仅凭时间接近判死，必须进入球员归属阶段。
        """
        for bounce in bounce_events:
            if bounce.confidence < self.config.bounce_suppress_confidence:
                continue
            delta_sec = candidate.timestamp_sec - bounce.timestamp_sec
            if -self.config.bounce_suppress_before_sec <= delta_sec <= self.config.bounce_suppress_after_sec:
                return bounce
        return None

    def finalize(
        self,
        prefiltered: list[PrefilteredHitCandidate],
        bounce_events: list[BounceEvent] | None = None,
        attributions: dict[str, PlayerAttribution] | None = None,
    ) -> list[TrajectoryEvent]:
        """结合归属结果生成最终事件列表（含弹地事件）。

        suppressed / rejected 候选不生成事件（I1 / I11）。
        """
        attributions = attributions or {}
        events: list[TrajectoryEvent] = []

        for index, bounce in enumerate(bounce_events or []):
            events.append(
                TrajectoryEvent(
                    event_id=bounce.event_id or f"bounce-{index + 1}",
                    event_type=TrajectoryEventType.BOUNCE,
                    frame_index=bounce.frame_index,
                    timestamp_sec=bounce.timestamp_sec,
                    image_xy=(
                        (float(bounce.image_xy[0]), float(bounce.image_xy[1])) if bounce.image_xy is not None else None
                    ),
                    court_xy=(
                        (float(bounce.court_xy[0]), float(bounce.court_xy[1])) if bounce.court_xy is not None else None
                    ),
                    confidence=bounce.confidence,
                    source=EventSource.BOUNCE_DETECTOR.value,
                    diagnostics=dict(bounce.diagnostics),
                    ownership_status=OwnershipStatus.NOT_APPLICABLE.value,
                )
            )

        for candidate in prefiltered:
            if candidate.prefilter_status != "survived":
                continue
            attribution = attributions.get(candidate.candidate_id)
            events.append(
                TrajectoryEvent(
                    event_id=f"hit-{candidate.frame_index}",
                    event_type=TrajectoryEventType.HIT,
                    frame_index=candidate.frame_index,
                    timestamp_sec=candidate.timestamp_sec,
                    image_xy=candidate.image_xy,
                    court_xy=None,
                    confidence=candidate.ball_evidence_confidence,
                    source=EventSource.HEURISTIC.value,
                    diagnostics=dict(candidate.diagnostics),
                    event_status=(
                        "confirmed"
                        if attribution is None or attribution.status == OwnershipStatus.CONFIRMED.value
                        else "ambiguous"
                    ),
                    hitter_player_id=attribution.player_id if attribution else None,
                    hitter_render_slot=attribution.render_slot if attribution else None,
                    ownership_status=(attribution.status if attribution else OwnershipStatus.UNASSIGNED.value),
                    ownership_confidence=attribution.confidence if attribution else None,
                    ownership_source_event_id=candidate.candidate_id,
                    attribution=attribution,
                )
            )

        # 排序（确定性：同帧按时间）
        events.sort(key=lambda e: (e.frame_index, e.timestamp_sec))
        return events

    def resolve(
        self,
        candidates: list[HitCandidate],
        bounce_events: list[BounceEvent] | None = None,
        fps: float = 30.0,
    ) -> list[TrajectoryEvent]:
        """兼容入口：prefilter + 无归属 finalize（不启用球员归属时使用）。"""
        prefiltered = self.prefilter(candidates, bounce_events, fps=fps)
        return self.finalize(prefiltered, bounce_events)

    def suppression_config_snapshot(self, fps: float, frame_stride: int = 1) -> dict:
        """抑制窗口配置快照（写入产物 diagnostics，便于按数据集调参）。"""
        return {
            "bounce_suppress_before_sec": self.config.bounce_suppress_before_sec,
            "bounce_suppress_after_sec": self.config.bounce_suppress_after_sec,
            "effective_fps": fps,
            "frame_stride": frame_stride,
        }
