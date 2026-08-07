"""Shot 生命周期与归属传播（ball_shot_assembler）。

`shot_id` 表示"一次击球产生的完整球路"，跨弹地段落传播击球者归属。

生命周期（设计 D7 / 不变量 I3 / I11 / I12）：

  边界                       对当前 Shot       是否开启新 Shot
  confirmed / ambiguous hit  关闭              是
  serve reset                关闭              是
  bounce                     保持（只切段）     否
  suppressed / rejected hit  完全忽略           否
  long loss / stream end     关闭              否

半场交替校验（设计 D8 / 任务 6）：Shot 序列上连续两次击球归属到同一半场，
且证据不强时降级为 ambiguous；证据强时保留并记录诊断。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.vision.pickleball_game_analysis.player_attribution_context import PlayerAttributionContext
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    FlightSegment,
    OwnershipStatus,
    TrajectoryEvent,
    TrajectoryEventType,
)


@dataclass
class ShotRecord:
    """一次 Shot 的摘要（供序列校验与统计）。"""

    shot_id: str
    hitter_player_id: str | None
    hitter_render_slot: str | None
    ownership_status: str
    ownership_confidence: float | None
    score_margin: float | None
    contact_timestamp_sec: float
    source_event_id: str


class BallShotAssembler:
    """把飞行段组装为 Shot 并回填归属字段。"""

    def __init__(self) -> None:
        self._shot_counter = 0

    def assemble(
        self,
        segments: list[FlightSegment],
        events_by_id: dict[str, TrajectoryEvent],
    ) -> list[ShotRecord]:
        """原地回填 segment 的 shot/owner 字段，返回 Shot 摘要列表。

        segment 归属规则（I5）：
          - 以 HIT / SERVE_RESET 起始的段开启新 Shot（继承该事件的归属）；
          - 其他段继承当前打开的 Shot；
          - 无 Shot 上下文的段输出 `shot_id=null, ownership_status=not_applicable`（I10）。
        """
        shots: list[ShotRecord] = []
        current: ShotRecord | None = None
        consumed_openers: set[str] = set()

        for segment in segments:
            start_event = events_by_id.get(segment.start_event_id) if segment.start_event_id else None
            if start_event is not None and start_event.event_type in (
                TrajectoryEventType.HIT,
                TrajectoryEventType.SERVE_RESET,
            ):
                current = self._open_shot(start_event)
                shots.append(current)
                consumed_openers.add(start_event.event_id)

            # 段本身属于其飞行期间打开的 Shot（I2：边界只切段，不中断归属）
            self._assign(segment, current)

            # LOSS / END_OF_STREAM 在段末关闭当前 Shot：影响的是后续段（I10）
            if segment.end_event_type in (
                TrajectoryEventType.LOSS,
                TrajectoryEventType.END_OF_STREAM,
            ):
                current = None

        # 段末击球（无后续段承载）也登记 Shot，保证统计完整（I5）
        for event_id, event_obj in events_by_id.items():
            if event_obj.event_type not in (
                TrajectoryEventType.HIT,
                TrajectoryEventType.SERVE_RESET,
            ):
                continue
            if event_id in consumed_openers:
                continue
            shots.append(self._open_shot(event_obj))

        return shots

    def _open_shot(self, event: TrajectoryEvent) -> ShotRecord:
        self._shot_counter += 1
        is_serve = event.event_type == TrajectoryEventType.SERVE_RESET
        if is_serve:
            hitter = event.hitter_player_id
            status = OwnershipStatus.CONFIRMED.value if hitter else OwnershipStatus.UNASSIGNED.value
            margin = 1.0 if hitter else 0.0
            confidence = 1.0 if hitter else None
        else:
            hitter = event.hitter_player_id
            status = event.ownership_status or OwnershipStatus.UNASSIGNED.value
            margin = event.attribution.score_margin if event.attribution else 0.0
            confidence = event.ownership_confidence

        return ShotRecord(
            shot_id=f"shot-{self._shot_counter:03d}",
            hitter_player_id=hitter,
            hitter_render_slot=event.hitter_render_slot,
            ownership_status=status,
            ownership_confidence=confidence,
            score_margin=margin,
            contact_timestamp_sec=event.timestamp_sec,
            source_event_id=event.event_id,
        )

    def _assign(self, segment: FlightSegment, current: ShotRecord | None) -> None:
        if current is None:
            segment.shot_id = None
            segment.hitter_player_id = None
            segment.hitter_render_slot = None
            segment.ownership_status = OwnershipStatus.NOT_APPLICABLE.value
            segment.ownership_confidence = None
            segment.ownership_source_event_id = None
            return
        segment.shot_id = current.shot_id
        segment.hitter_player_id = current.hitter_player_id
        segment.hitter_render_slot = current.hitter_render_slot
        segment.ownership_status = current.ownership_status
        segment.ownership_confidence = current.ownership_confidence
        segment.ownership_source_event_id = current.source_event_id


@dataclass(frozen=True)
class ShotSequenceValidatorConfig:
    """半场交替序列校验超参数。"""

    high_confidence_threshold: float = 0.85
    strong_margin_threshold: float = 0.25


class ShotSequenceValidator:
    """Shot 序列上的半场交替校验（sanity check，不硬改高可信结论）。"""

    def __init__(self, config: ShotSequenceValidatorConfig | None = None) -> None:
        self.config = config or ShotSequenceValidatorConfig()

    def validate(
        self,
        shots: list[ShotRecord],
        segments: list[FlightSegment],
        context: PlayerAttributionContext,
    ) -> list[ShotRecord]:
        """返回需要降级为 ambiguous 的 Shot（已同步改写其 segment 归属字段）。

        连续两次击球归属到同一半场时（使用接触时刻动态半场）：
          - 当前归属证据弱（置信度或 margin 低于阈值）→ 降级 ambiguous，player_id 置 None；
          - 证据强 → 保留结论，诊断写入该 Shot 的 segments。
        """
        downgraded: list[ShotRecord] = []
        confirmed = [
            shot
            for shot in shots
            if shot.hitter_player_id is not None and shot.ownership_status == OwnershipStatus.CONFIRMED.value
        ]
        for previous, current in zip(confirmed, confirmed[1:], strict=False):
            prev_side = context.side_at(previous.hitter_player_id, previous.contact_timestamp_sec)
            cur_side = context.side_at(current.hitter_player_id, current.contact_timestamp_sec)
            if prev_side is None or cur_side is None or prev_side != cur_side:
                continue

            strong = (current.ownership_confidence or 0.0) >= self.config.high_confidence_threshold and (
                current.score_margin or 0.0
            ) >= self.config.strong_margin_threshold
            if strong:
                self._mark_violation(segments, current, previous)
                continue

            self._downgrade(segments, current)
            downgraded.append(current)
        return downgraded

    @staticmethod
    def _segments_of(segments: list[FlightSegment], shot_id: str) -> list[FlightSegment]:
        return [segment for segment in segments if segment.shot_id == shot_id]

    def _mark_violation(
        self,
        segments: list[FlightSegment],
        current: ShotRecord,
        previous: ShotRecord,
    ) -> None:
        for segment in self._segments_of(segments, current.shot_id):
            segment.boundary_reason = (
                f"{segment.boundary_reason}; side_alternation_violation"
                if segment.boundary_reason
                else "side_alternation_violation"
            )

    def _downgrade(self, segments: list[FlightSegment], current: ShotRecord) -> None:
        for segment in self._segments_of(segments, current.shot_id):
            segment.hitter_player_id = None
            segment.hitter_render_slot = None
            segment.ownership_status = OwnershipStatus.AMBIGUOUS.value
            segment.boundary_reason = (
                f"{segment.boundary_reason}; side_alternation_downgraded"
                if segment.boundary_reason
                else "side_alternation_downgraded"
            )
