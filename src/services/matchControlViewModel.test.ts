import { describe, expect, it } from "vitest";
import type { LiveCodingState } from "../types/report";
import { buildMatchControlViewModel, withInitialServer } from "./matchControlViewModel";

function state(overrides: Partial<LiveCodingState> = {}): LiveCodingState {
  return {
    revision: 0, set_ordinal: 1, game_ordinal: 0, rally_ordinal: 0,
    non_play: true, match_phase: "intermission", score_a: 0, score_b: 0,
    scoring_mode: "hybrid_21_best_of_5_v1", scoring_ruleset_version: "hybrid_21_best_of_5_v1",
    server_team: null, recent_results: [], games_won_a: 0, games_won_b: 0,
    scoring_phase: "rally", serving_side: null, match_status: "not_started", match_winner: null,
    ...overrides,
  };
}

describe("buildMatchControlViewModel", () => {
  it("only offers starting a game when no game is open", () => {
    const vm = buildMatchControlViewModel(state());
    expect(vm.phase).toBe("awaiting_game");
    expect(vm.events.filter(event => event.group === "match").map(event => event.type)).toEqual(["start_game"]);
    expect(vm.events[0].label).toBe("开始第 1 局");
  });

  it("only offers starting the next rally while waiting", () => {
    const vm = buildMatchControlViewModel(state({ current_game_segment_id: "game", game_ordinal: 2, rally_ordinal: 4 }));
    expect(vm.phase).toBe("awaiting_rally");
    expect(vm.events.filter(event => event.group === "match").map(event => event.type)).toEqual(["start_next_rally"]);
    expect(vm.events[0].label).toBe("开始第 5 分");
  });

  it("offers only explicit results while a rally is open", () => {
    const vm = buildMatchControlViewModel(state({ current_game_segment_id: "game", current_rally_segment_id: "rally" }));
    expect(vm.phase).toBe("rally_active");
    expect(vm.events.filter(event => event.group === "match").map(event => event.type)).toEqual([
      "rally_result_a", "rally_result_b", "rally_replay",
    ]);
    expect(vm.events.some(event => event.type === "end_rally")).toBe(false);
  });

  it("does not offer match progression after completion", () => {
    const vm = buildMatchControlViewModel(state({ match_status: "completed", match_winner: "A", games_won_a: 3 }));
    expect(vm.phase).toBe("completed");
    expect(vm.events.some(event => event.group === "match")).toBe(false);
  });

  it("adds the selected server to one start-game command", () => {
    const startGame = buildMatchControlViewModel(state()).events[0];
    expect(withInitialServer(startGame, "B").payload).toEqual({ initial_server_team: "B" });
    expect(startGame.payload).toEqual({});
  });
});
