import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { LiveCodingState } from "../../types/report";
import { CompactScoreStrip } from "./CompactScoreStrip";

const state: LiveCodingState = {
  revision: 4, set_ordinal: 1, game_ordinal: 2, rally_ordinal: 7,
  non_play: false, match_phase: "rally_active", current_set_segment_id: "set",
  current_game_segment_id: "game", current_rally_segment_id: "rally",
  server_team: "B", score_a: 20, score_b: 20,
  scoring_mode: "hybrid_21_best_of_5_v1", scoring_ruleset_version: "hybrid_21_best_of_5_v1",
  recent_results: [], games_won_a: 1, games_won_b: 0,
  scoring_phase: "serve_only", serving_side: "right",
  match_status: "in_progress", match_winner: null,
};

describe("CompactScoreStrip", () => {
  it("shows games, score, serving side, and active rally", () => {
    const { container } = render(<CompactScoreStrip liveState={state} />);
    expect(container.textContent).toContain("胜局 1:0");
    expect(container.textContent).toContain("A 20");
    expect(container.textContent).toContain("B 20");
    expect(container.textContent).toContain("B 方右区发球");
    expect(container.textContent).toContain("第 7 分进行中");
  });

  it("shows the match winner after completion", () => {
    const { container } = render(<CompactScoreStrip liveState={{ ...state, current_rally_segment_id: undefined, games_won_a: 3, match_status: "completed", match_winner: "A" }} />);
    expect(container.textContent).toContain("A 方胜");
  });
});
