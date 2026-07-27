import type { LiveCodingState } from "../types/report";
import type { QuickEventDef } from "./timelineQuickEvents";

export type MatchControlPhase = "awaiting_game" | "awaiting_rally" | "rally_active" | "completed";

export interface MatchControlViewModel {
  phase: MatchControlPhase;
  events: QuickEventDef[];
  canStartGame: boolean;
  canStartRally: boolean;
  canSubmitResult: boolean;
}

const event = (type: QuickEventDef["type"], label: string, group: QuickEventDef["group"]): QuickEventDef => ({
  type, label, group, source: "manual", note: "", payload: {},
});

const auxiliaryEvents: QuickEventDef[] = [
  event("start_timeout", "战术暂停", "auxiliary"),
  event("change_side", "换边", "auxiliary"),
  { ...event("add_note", "重点标记", "auxiliary"), payload: { highlight: true } },
  event("undo", "撤销", "auxiliary"),
];

export function buildMatchControlViewModel(liveState: LiveCodingState | null): MatchControlViewModel {
  if (liveState?.match_status === "completed") {
    return { phase: "completed", events: auxiliaryEvents, canStartGame: false, canStartRally: false, canSubmitResult: false };
  }
  if (!liveState?.current_game_segment_id) {
    const gameNumber = Math.min(5, (liveState?.games_won_a ?? 0) + (liveState?.games_won_b ?? 0) + 1);
    return {
      phase: "awaiting_game",
      events: [event("start_game", `开始第 ${gameNumber} 局`, "match"), ...auxiliaryEvents],
      canStartGame: true, canStartRally: false, canSubmitResult: false,
    };
  }
  if (!liveState.current_rally_segment_id) {
    const rallyNumber = (liveState.rally_ordinal ?? 0) + 1;
    return {
      phase: "awaiting_rally",
      events: [event("start_next_rally", `开始第 ${rallyNumber} 分`, "match"), ...auxiliaryEvents],
      canStartGame: false, canStartRally: true, canSubmitResult: false,
    };
  }
  return {
    phase: "rally_active",
    events: [
      event("rally_result_a", "A 方胜", "match"),
      event("rally_result_b", "B 方胜", "match"),
      event("rally_replay", "重打", "match"),
      ...auxiliaryEvents,
    ],
    canStartGame: false, canStartRally: false, canSubmitResult: true,
  };
}

export function withInitialServer(event: QuickEventDef, server: "A" | "B"): QuickEventDef {
  if (event.type !== "start_game") throw new Error("initial server only applies to start_game");
  return { ...event, payload: { initial_server_team: server } };
}
