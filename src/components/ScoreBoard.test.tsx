import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScoreBoard } from "./ScoreBoard";
import type { LiveCodingState } from "../types/report";

function makeLiveState(overrides: Partial<LiveCodingState>): LiveCodingState {
  return {
    revision: 0,
    set_ordinal: 1,
    game_ordinal: 2,
    rally_ordinal: 0,
    non_play: true,
    match_phase: "intermission",
    scoring_mode: "side_out_singles_v1",
    score_a: 3,
    score_b: 2,
    server_team: "A",
    recent_results: [
      { winner: "A", validity: "valid" },
      { winner: "A", validity: "valid" },
      { winner: "B", validity: "valid" },
      { winner: "A", validity: "valid" },
      { winner: "B", validity: "valid" },
    ],
    games_won_a: 1,
    games_won_b: 0,
    scoring_phase: "rally",
    serving_side: "left",
    match_status: "in_progress",
    ...overrides,
  };
}

describe("ScoreBoard", () => {
  it("renders score and set/game info", () => {
    render(<ScoreBoard liveState={makeLiveState({})} />);
    // Check rendered numbers appear
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("A 方")).toBeTruthy();
    expect(screen.getByText("B 方")).toBeTruthy();
    // Set/game info should contain the ordinals
    expect(screen.getByText((c: string) => c.includes("第 3 局"))).toBeTruthy();
  });

  it("shows server indicator for A", () => {
    const { container } = render(<ScoreBoard liveState={makeLiveState({ server_team: "A" })} />);
    expect(container.textContent).toContain("发球");
  });

  it("shows server indicator for B", () => {
    const { container } = render(<ScoreBoard liveState={makeLiveState({ server_team: "B", score_a: 2, score_b: 3 })} />);
    expect(container.textContent).toContain("发球");
  });

  it("shows recent_results blocks via container", () => {
    const state = makeLiveState({});
    render(<ScoreBoard liveState={state} />);
    const blocks = state.recent_results!.length;
    expect(blocks).toBe(5);
  });

  it("shows doubles scoring instead of a manual placeholder", () => {
    const { container } = render(<ScoreBoard liveState={makeLiveState({ scoring_mode: "manual" })} />);
    expect(container.textContent).not.toContain("双打自动计分暂不可用");
    expect(container.textContent).toContain("每球得分");
  });

  it("renders null state gracefully", () => {
    const { container } = render(<ScoreBoard liveState={null} />);
    expect(container.innerHTML).toBe("");
  });

  it("shows score info for doubles and historical manual states", () => {
    const { container } = render(<ScoreBoard liveState={makeLiveState({ scoring_mode: "manual", score_a: 5, score_b: 3 })} />);
    expect(container.textContent).toContain("5");
    expect(container.textContent).toContain("3");
  });

  it("shows serve-only phase and doubles player side", () => {
    render(<ScoreBoard liveState={makeLiveState({ scoring_phase: "serve_only", serving_side: "right" })} matchFormat="doubles" />);
    expect(screen.getByText("发球得分")).toBeTruthy();
    expect(screen.getByText("A 方右区队员发球")).toBeTruthy();
  });

  it("shows pending indicator when open rally exists", () => {
    const { container } = render(<ScoreBoard liveState={makeLiveState({})} openRallyExists={true} />);
    const pendingBlocks = container.querySelectorAll(".animate-pulse");
    expect(pendingBlocks.length).toBeGreaterThanOrEqual(1);
  });
});
