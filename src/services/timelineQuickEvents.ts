/**
 * 快捷时间线事件映射 —— 按 capture_mode 生成稳定的按钮定义。
 * type 字段直接使用 CodingActionType，便于 Outbox 发送；
 * 通过 ACTION_TO_EVENT_TYPE 映射为 TimelineEventType 用于直接 API。
 */
import type { TimelineEventType, TimelineEventSource, CodingActionType } from "../types/report";

/** 快捷事件按钮定义 */
export interface QuickEventDef {
  type: CodingActionType;       // 动作类型
  source: TimelineEventSource;  // 事件来源
  label: string;                // 按钮显示文本
  note: string;                 // 备注
  payload: Record<string, unknown>;  // 附加载荷
}

export const ACTION_TO_EVENT_TYPE: Record<string, TimelineEventType> = {
  start_set: "set_start",
  start_game: "game_start",
  start_next_rally: "rally_start",
  end_rally: "rally_end",
  rally_result_a: "rally_end",
  rally_result_b: "rally_end",
  rally_replay: "rally_end",
  change_side: "side_change",
  add_note: "add_note",
  undo: "custom_marker",
  toggle_non_play: "non_play_start",
  end_game: "game_end",
  end_set: "set_end",
};

// —— 比赛模式快捷事件（含计分结果按钮） ——
export const MATCH_QUICK_EVENTS: QuickEventDef[] = [
  { type: "rally_result_a", source: "manual", label: "A方胜", note: "", payload: {} },
  { type: "rally_result_b", source: "manual", label: "B方胜", note: "", payload: {} },
  { type: "rally_replay", source: "manual", label: "重打", note: "", payload: {} },
  { type: "start_set", source: "manual", label: "盘开始", note: "新的一盘开始", payload: {} },
  { type: "start_game", source: "manual", label: "局开始", note: "新的一局开始", payload: { initial_server_team: "A" } },
  { type: "start_next_rally", source: "manual", label: "分开始", note: "开始新的一分", payload: {} },
  { type: "start_timeout", source: "manual", label: "战术暂停", note: "进入战术暂停", payload: {} },
  { type: "change_side", source: "manual", label: "换边", note: "双方交换场地", payload: {} },
  { type: "add_note", source: "manual", label: "重点标记", note: "标记重要时刻", payload: { highlight: true } },
  { type: "undo", source: "manual", label: "撤销", note: "撤销上一步操作", payload: {} },
];

// —— 练习模式快捷事件 ——
export const PRACTICE_QUICK_EVENTS: QuickEventDef[] = [
  { type: "add_note", source: "manual", label: "练习开始", note: "drill_start", payload: {} },
  { type: "add_note", source: "manual", label: "练习结束", note: "drill_end", payload: {} },
  { type: "toggle_non_play", source: "manual", label: "非练习", note: "", payload: {} },
  { type: "add_note", source: "manual", label: "重点片段", note: "", payload: { highlight: true } },
  { type: "add_note", source: "manual", label: "自定义标记", note: "", payload: {} },
];

// —— 工程模式快捷事件 ——
export const ENGINEERING_QUICK_EVENTS: QuickEventDef[] = [
  { type: "add_note", source: "manual", label: "画面异常", note: "", payload: { issue: "visual_anomaly" } },
  { type: "add_note", source: "manual", label: "模型误检", note: "", payload: { issue: "false_detection" } },
  { type: "add_note", source: "manual", label: "遮挡严重", note: "", payload: { issue: "occlusion" } },
  { type: "add_note", source: "manual", label: "重点调试", note: "", payload: { debug: true } },
  { type: "add_note", source: "manual", label: "自定义标记", note: "", payload: {} },
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
