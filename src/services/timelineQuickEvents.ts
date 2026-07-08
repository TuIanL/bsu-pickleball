/**
 * 快捷时间线事件映射 —— 按 capture_mode 生成稳定的 event_type、label、note 和 payload_json。
 */
import type { TimelineEventType, TimelineEventSource } from "../types/report";

export interface QuickEventDef {
  type: TimelineEventType;
  source: TimelineEventSource;
  label: string;
  note: string;
  payload: Record<string, unknown>;
}

// —— 比赛模式快捷事件 ——
export const MATCH_QUICK_EVENTS: QuickEventDef[] = [
  { type: "game_start", source: "manual", label: "局开始", note: "", payload: {} },
  { type: "game_end", source: "manual", label: "局结束", note: "", payload: {} },
  { type: "score_update", source: "manual", label: "比分更新", note: "", payload: { score_a: 0, score_b: 0 } },
  { type: "score_correction", source: "manual", label: "比分修正", note: "", payload: { score_a: 0, score_b: 0 } },
  { type: "side_change", source: "manual", label: "换边", note: "", payload: {} },
  { type: "non_play_start", source: "manual", label: "非比赛开始", note: "", payload: {} },
  { type: "non_play_end", source: "manual", label: "非比赛结束", note: "", payload: {} },
  { type: "session_note", source: "manual", label: "备注", note: "", payload: {} },
  { type: "custom_marker", source: "manual", label: "自定义标记", note: "", payload: {} },
];

// —— 练习模式快捷事件 ——
export const PRACTICE_QUICK_EVENTS: QuickEventDef[] = [
  { type: "drill_start", source: "manual", label: "练习开始", note: "", payload: {} },
  { type: "drill_end", source: "manual", label: "练习结束", note: "", payload: {} },
  { type: "non_play_start", source: "manual", label: "非练习开始", note: "", payload: {} },
  { type: "non_play_end", source: "manual", label: "非练习结束", note: "", payload: {} },
  { type: "session_note", source: "manual", label: "重点片段", note: "", payload: { highlight: true } },
  { type: "custom_marker", source: "manual", label: "自定义标记", note: "", payload: {} },
];

// —— 工程模式快捷事件 ——
export const ENGINEERING_QUICK_EVENTS: QuickEventDef[] = [
  { type: "session_note", source: "manual", label: "画面异常", note: "", payload: { issue: "visual_anomaly" } },
  { type: "session_note", source: "manual", label: "模型误检", note: "", payload: { issue: "false_detection" } },
  { type: "session_note", source: "manual", label: "遮挡严重", note: "", payload: { issue: "occlusion" } },
  { type: "session_note", source: "manual", label: "重点调试", note: "", payload: { debug: true } },
  { type: "custom_marker", source: "manual", label: "自定义标记", note: "", payload: {} },
];

export function quickEventsForMode(captureMode: string): QuickEventDef[] {
  switch (captureMode) {
    case "match":
      return MATCH_QUICK_EVENTS;
    case "practice":
      return PRACTICE_QUICK_EVENTS;
    case "engineering":
      return ENGINEERING_QUICK_EVENTS;
    default:
      return PRACTICE_QUICK_EVENTS;
  }
}
