import type { SessionTimelineEvent, CaptureSegmentSummary } from "../../types/report";

const EVENT_LABELS: Record<string, string> = {
  set_start: "盘开始", set_end: "盘结束",
  game_start: "局开始", game_end: "局结束",
  rally_start: "分开始", rally_end: "分结束",
  non_play_start: "进入非比赛时间", non_play_end: "恢复比赛",
  side_change: "换边", add_note: "重点标记",
  timeout_start: "战术暂停", timeout_end: "暂停结束",
  score_update: "比分修正", undo: "撤销",
  session_note: "备注",
  rally_replay: "重打",
  rally_result_a: "A方得分", rally_result_b: "B方得分",
};

export function formatTimelineEventLabel(
  event: { event_type: string; label?: string | null; timestamp_ms: number },
  segments: { segment_type: string; ordinal: number; start_ms: number; end_ms?: number | null }[],
): string {
  if (event.label && event.label !== event.event_type) {
    return event.label;
  }
  const containing = segments
    .filter(s => s.start_ms <= event.timestamp_ms && (s.end_ms == null || event.timestamp_ms <= s.end_ms))
    .sort((a, b) => {
      const aDur = (a.end_ms ?? Infinity) - a.start_ms;
      const bDur = (b.end_ms ?? Infinity) - b.start_ms;
      return aDur - bDur;
    });
  const matched = containing[0];
  const label = EVENT_LABELS[event.event_type];
  if (!label) return event.event_type;
  if (matched && matched.ordinal > 0) {
    const segmentName =
      matched.segment_type === "set" ? "盘" :
      matched.segment_type === "game" ? "局" :
      matched.segment_type === "rally" ? "分" : "";
    if (segmentName) {
      const suffix = label.replace(segmentName, "").replace(/开始|结束/, "");
      return `第 ${matched.ordinal} ${segmentName}${suffix || ""}`;
    }
  }
  return label;
}
