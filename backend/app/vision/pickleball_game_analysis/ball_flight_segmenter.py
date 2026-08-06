"""飞行段切分（ball_flight_segmenter）。

按优先级把轨迹切分为飞行段：
  confirmed_hit → confirmed_bounce → long_tracking_loss → high_confidence_serve_reset → end_of_stream

每个边界产生新的 `segment_id`。相邻段共享事件锚点（数据上硬切段、几何上连续）。
长丢失与无法解释的数据空洞处视觉上真正断开；短缺失由重建层以 model_predicted 虚线连接。
不构建权威 rally_id（S1：serve 仅作为可选上下文重置锚点）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    FlightSegment,
    ReconstructionConfig,
    TrajectoryEvent,
    TrajectoryEventType,
)
from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint

# 边界优先级（越小越优先；同帧冲突保留高优先级）
_BOUNDARY_PRIORITY = {
    TrajectoryEventType.HIT: 1,
    TrajectoryEventType.BOUNCE: 2,
    TrajectoryEventType.LOSS: 3,
    TrajectoryEventType.SERVE_RESET: 4,
    TrajectoryEventType.END_OF_STREAM: 5,
}


@dataclass
class SegmentBoundary:
    """一个切段边界（由事件或丢失缺口推导）。"""

    frame_index: int
    event_type: TrajectoryEventType
    event: TrajectoryEvent | None = None
    boundary_reason: str = ""
    priority: int = 0


class BallFlightSegmenter:
    """把清洗轨迹 + 边界事件切分为飞行段。"""

    def __init__(self, config: ReconstructionConfig | None = None) -> None:
        self.config = config or ReconstructionConfig()

    def segment(
        self,
        points: list[TrajectoryPoint],
        events: list[TrajectoryEvent] | None = None,
    ) -> list[FlightSegment]:
        """返回飞行段列表（按帧序）。"""
        boundaries = self._build_boundaries(points, events or [])
        segment_indices = self._cut_indices(points, boundaries)

        segments: list[FlightSegment] = []
        for order, (start, end, start_boundary, end_boundary) in enumerate(segment_indices):
            segment_points = points[start:end + 1]
            if len(segment_points) < self.config.min_points_per_segment:
                continue
            segment_id = f"flight-{order + 1}"
            segments.append(
                FlightSegment(
                    segment_id=segment_id,
                    start_index=start,
                    end_index=end,
                    start_event_id=start_boundary.event.event_id if start_boundary and start_boundary.event else None,
                    end_event_id=end_boundary.event.event_id if end_boundary and end_boundary.event else None,
                    start_event_type=start_boundary.event_type if start_boundary else None,
                    end_event_type=end_boundary.event_type if end_boundary else None,
                    boundary_reason=end_boundary.boundary_reason if end_boundary else "end_of_stream",
                    start_anchor_id=self._anchor_id_for(start_boundary),
                    end_anchor_id=self._anchor_id_for(end_boundary),
                    point_indices=list(range(start, end + 1)),
                )
            )
        return segments

    # ---- 边界构建 ----

    def _build_boundaries(
        self,
        points: list[TrajectoryPoint],
        events: list[TrajectoryEvent],
    ) -> list[SegmentBoundary]:
        boundaries: dict[int, SegmentBoundary] = {}

        # 1) 事件边界（hit / bounce / serve_reset）
        for event in events:
            if event.event_type in (
                TrajectoryEventType.HIT,
                TrajectoryEventType.BOUNCE,
                TrajectoryEventType.SERVE_RESET,
            ):
                self._upsert_boundary(
                    boundaries,
                    SegmentBoundary(
                        frame_index=event.frame_index,
                        event_type=event.event_type,
                        event=event,
                        boundary_reason=(
                            "serve_reset" if event.event_type == TrajectoryEventType.SERVE_RESET else event.event_type.value
                        ),
                        priority=_BOUNDARY_PRIORITY[event.event_type],
                    ),
                )

        # 2) 长时间丢失边界：有效点之间的帧缺口超过阈值
        valid_indices = [i for i, p in enumerate(points) if p.image_xy is not None]
        for left, right in zip(valid_indices[:-1], valid_indices[1:]):
            gap = points[right].frame_index - points[left].frame_index
            if gap > self.config.long_loss_gap_frames:
                self._upsert_boundary(
                    boundaries,
                    SegmentBoundary(
                        frame_index=points[right].frame_index,
                        event_type=TrajectoryEventType.LOSS,
                        event=None,
                        boundary_reason="long_tracking_loss",
                        priority=_BOUNDARY_PRIORITY[TrajectoryEventType.LOSS],
                    ),
                )

        # 3) 流结束边界（放在最后一个有效点之后）
        if valid_indices:
            self._upsert_boundary(
                boundaries,
                SegmentBoundary(
                    frame_index=points[valid_indices[-1]].frame_index,
                    event_type=TrajectoryEventType.END_OF_STREAM,
                    event=None,
                    boundary_reason="end_of_stream",
                    priority=_BOUNDARY_PRIORITY[TrajectoryEventType.END_OF_STREAM],
                ),
            )

        ordered = sorted(boundaries.values(), key=lambda b: b.frame_index)
        return ordered

    @staticmethod
    def _upsert_boundary(boundaries: dict[int, SegmentBoundary], boundary: SegmentBoundary) -> None:
        """同帧冲突时保留高优先级（优先级数字更小者优先）。"""
        existing = boundaries.get(boundary.frame_index)
        if existing is None or boundary.priority < existing.priority:
            boundaries[boundary.frame_index] = boundary

    def _cut_indices(
        self,
        points: list[TrajectoryPoint],
        boundaries: list[SegmentBoundary],
    ) -> list[tuple[int, int, SegmentBoundary | None, SegmentBoundary | None]]:
        """在有效点序列上按边界切分，返回 (start, end, start_boundary, end_boundary) 列表。

        边界归属规则（语义断开 vs 几何连续）：
          - 击球/弹地/serve：边界点是两段的共享锚点，归入前后两段（几何连续）；
          - 长时间丢失：边界点是"重新捕获点"，只归入后一段（语义断开，前段到丢失前为止）；
          - end_of_stream：只闭合最后一段。
        """
        valid_indices = [i for i, p in enumerate(points) if p.image_xy is not None]
        if not valid_indices:
            return []

        cuts: list[tuple[int, SegmentBoundary]] = []  # (目标有效点下标, 边界)
        for boundary in boundaries:
            target = next(
                (i for i in valid_indices if points[i].frame_index >= boundary.frame_index),
                None,
            )
            if target is None:
                continue
            # 同一有效点撞上多个边界 → 保留高优先级
            if cuts and target == cuts[-1][0]:
                existing = cuts[-1][1]
                if _BOUNDARY_PRIORITY.get(boundary.event_type, 99) < _BOUNDARY_PRIORITY.get(existing.event_type, 99):
                    cuts[-1] = (target, boundary)
                continue
            cuts.append((target, boundary))

        segments: list[tuple[int, int, SegmentBoundary | None, SegmentBoundary | None]] = []
        left: tuple[int, SegmentBoundary] | None = None
        for right in [*cuts, None]:
            start = valid_indices[0] if left is None else left[0]
            end = valid_indices[-1] if right is None else self._segment_end(right, valid_indices)
            if end >= start:
                segments.append((start, end, left[1] if left else None, right[1] if right else None))
            left = right
        return segments

    @staticmethod
    def _segment_end(
        right: tuple[int, SegmentBoundary],
        valid_indices: list[int],
    ) -> int:
        """计算右边界之前段的结束有效点下标。

        击球/弹地/serve（共享锚点）→ 结束于边界点本身；
        end_of_stream → 结束于最后有效点；
        丢失 → 结束于边界点之前最后一个有效点（不把重新捕获点并入前段）。
        """
        target, boundary = right
        if boundary.event_type in (
            TrajectoryEventType.HIT,
            TrajectoryEventType.BOUNCE,
            TrajectoryEventType.SERVE_RESET,
            TrajectoryEventType.END_OF_STREAM,
        ):
            return target
        idx = valid_indices.index(target)
        return valid_indices[idx - 1] if idx > 0 else -1

    @staticmethod
    def _anchor_id_for(boundary: SegmentBoundary | None) -> str | None:
        """为可作空间锚点的边界生成锚点 ID；不可作锚点的返回 None。"""
        if boundary is None or boundary.event is None:
            return None
        if boundary.event_type in (
            TrajectoryEventType.HIT,
            TrajectoryEventType.BOUNCE,
            TrajectoryEventType.SERVE_RESET,
        ):
            return f"anchor-{boundary.event.event_id}"
        return None
