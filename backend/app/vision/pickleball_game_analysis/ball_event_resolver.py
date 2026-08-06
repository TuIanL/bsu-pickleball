"""击球与弹地事件仲裁（ball_event_resolver）。

仲裁层解决同一时间窗口内击球候选与弹地候选的冲突，不武断分类：
  - 已有高可信 bounce → 抑制 hit candidate；
  - 明显靠近球员区域且 bounce 证据较弱 → 接受 hit candidate；
  - 两者都不充分 → 标记 ambiguous，仅用于切段或降低质量。

`player_motion_pixels` / 球员接近度仅作弱证据，不作为确定击球的硬条件。
输出统一的事件列表供飞行段切分消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.vision.pickleball_game_analysis.ball_contact_event_detector import HitCandidate
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    EventSource,
    TrajectoryEvent,
    TrajectoryEventType,
)
from app.vision.pickleball_game_analysis.schemas import BounceEvent


@dataclass(frozen=True)
class ResolverConfig:
    """事件仲裁超参数。"""

    bounce_suppression_window_frames: int = 8   # 高可信弹地抑制击球的时间窗（帧）
    bounce_suppress_confidence: float = 0.6     # 弹地置信度高于此则抑制击球
    player_proximity_strong: float = 0.7        # 球员接近度强证据阈值（0~1）


class BallEventResolver:
    """把击球候选与弹跳事件仲裁为统一的飞行段边界事件。"""

    def __init__(self, config: ResolverConfig | None = None) -> None:
        self.config = config or ResolverConfig()

    def resolve(
        self,
        candidates: list[HitCandidate],
        bounce_events: list[BounceEvent] | None = None,
        player_proximity: dict[int, float] | None = None,
    ) -> list[TrajectoryEvent]:
        """返回排序后的边界事件列表（击球 / 弹地 / ambiguous）。"""
        events: list[TrajectoryEvent] = []

        # 弹地事件直接进入边界列表（不修改其语义）
        for index, bounce in enumerate(bounce_events or []):
            events.append(
                TrajectoryEvent(
                    event_id=bounce.event_id or f"bounce-{index + 1}",
                    event_type=TrajectoryEventType.BOUNCE,
                    frame_index=bounce.frame_index,
                    timestamp_sec=bounce.timestamp_sec,
                    image_xy=(
                        (float(bounce.image_xy[0]), float(bounce.image_xy[1]))
                        if bounce.image_xy is not None
                        else None
                    ),
                    court_xy=(
                        (float(bounce.court_xy[0]), float(bounce.court_xy[1]))
                        if bounce.court_xy is not None
                        else None
                    ),
                    confidence=bounce.confidence,
                    source=EventSource.BOUNCE_DETECTOR.value,
                    diagnostics=dict(bounce.diagnostics),
                )
            )

        # 击球候选仲裁
        hit_events = self._arbitrate_hits(candidates, events, player_proximity or {})
        events.extend(hit_events)

        # 排序（确定性：同帧按时间）
        events.sort(key=lambda e: (e.frame_index, e.timestamp_sec))
        return events

    def _arbitrate_hits(
        self,
        candidates: list[HitCandidate],
        existing_events: list[TrajectoryEvent],
        player_proximity: dict[int, float],
    ) -> list[TrajectoryEvent]:
        """对每个 confirmed_hit 候选做弹地冲突仲裁。"""
        bounce_events = [e for e in existing_events if e.event_type == TrajectoryEventType.BOUNCE]
        window = self.config.bounce_suppression_window_frames
        resolved: list[TrajectoryEvent] = []
        for candidate in candidates:
            if candidate.status != "confirmed_hit":
                continue
            nearby_bounces = [
                e for e in bounce_events
                if abs(e.frame_index - candidate.frame_index) <= window
            ]
            strongest = max(nearby_bounces, key=lambda e: e.confidence) if nearby_bounces else None

            if strongest is not None and strongest.confidence >= self.config.bounce_suppress_confidence:
                # 高可信弹地 → 抑制击球
                resolved.append(
                    TrajectoryEvent(
                        event_id=f"hit-{candidate.frame_index}",
                        event_type=TrajectoryEventType.HIT,
                        frame_index=candidate.frame_index,
                        timestamp_sec=candidate.timestamp_sec,
                        image_xy=candidate.image_xy,
                        court_xy=None,
                        confidence=round(candidate.confidence, 3),
                        source=EventSource.HEURISTIC.value,
                        diagnostics={
                            "status": "suppressed_by_bounce",
                            "bounce_event_id": strongest.event_id,
                            "bounce_confidence": round(strongest.confidence, 3),
                        },
                    )
                )
            elif strongest is not None:
                # 弹地证据弱：靠近球员则接受，否则 ambiguous
                prox = player_proximity.get(candidate.frame_index)
                if prox is not None and prox >= self.config.player_proximity_strong:
                    resolved.append(
                        TrajectoryEvent(
                            event_id=f"hit-{candidate.frame_index}",
                            event_type=TrajectoryEventType.HIT,
                            frame_index=candidate.frame_index,
                            timestamp_sec=candidate.timestamp_sec,
                            image_xy=candidate.image_xy,
                            court_xy=None,
                            confidence=round(candidate.confidence, 3),
                            source=EventSource.HEURISTIC.value,
                            diagnostics={"status": "confirmed_near_player", "player_proximity": round(prox, 3)},
                        )
                    )
                else:
                    resolved.append(
                        TrajectoryEvent(
                            event_id=f"hit-{candidate.frame_index}",
                            event_type=TrajectoryEventType.HIT,
                            frame_index=candidate.frame_index,
                            timestamp_sec=candidate.timestamp_sec,
                            image_xy=candidate.image_xy,
                            court_xy=None,
                            confidence=round(candidate.confidence * 0.6, 3),
                            source=EventSource.HEURISTIC.value,
                            diagnostics={"event_type_ambiguous": True, "bounce_confidence": round(strongest.confidence, 3)},
                        )
                    )
            else:
                # 无附近弹地 → 确认击球
                resolved.append(
                    TrajectoryEvent(
                        event_id=f"hit-{candidate.frame_index}",
                        event_type=TrajectoryEventType.HIT,
                        frame_index=candidate.frame_index,
                        timestamp_sec=candidate.timestamp_sec,
                        image_xy=candidate.image_xy,
                        court_xy=None,
                        confidence=round(candidate.confidence, 3),
                        source=EventSource.HEURISTIC.value,
                        diagnostics={"status": "confirmed"},
                    )
                )
        return resolved
