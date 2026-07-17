import { describe, expect, it } from "vitest";
import type { QuickEventDef } from "../services/timelineQuickEvents";
import { MATCH_QUICK_EVENTS } from "../services/timelineQuickEvents";

describe("Match mode quick events contain result buttons", () => {
  it("has rally_result_a button", () => {
    const btn = MATCH_QUICK_EVENTS.find((e: QuickEventDef) => e.type === "rally_result_a");
    expect(btn).toBeDefined();
    expect(btn!.label).toBe("A方胜");
  });

  it("has rally_result_b button", () => {
    const btn = MATCH_QUICK_EVENTS.find((e: QuickEventDef) => e.type === "rally_result_b");
    expect(btn).toBeDefined();
    expect(btn!.label).toBe("B方胜");
  });

  it("has rally_replay button", () => {
    const btn = MATCH_QUICK_EVENTS.find((e: QuickEventDef) => e.type === "rally_replay");
    expect(btn).toBeDefined();
    expect(btn!.label).toBe("重打");
  });

  it("does NOT have end_rally button in match mode", () => {
    const btn = MATCH_QUICK_EVENTS.find((e: QuickEventDef) => e.type === "end_rally");
    expect(btn).toBeUndefined();
  });

  it("has all expected match buttons", () => {
    const types = MATCH_QUICK_EVENTS.map((e: QuickEventDef) => e.type);
    expect(types).toContain("start_set");
    expect(types).toContain("start_game");
    expect(types).toContain("start_next_rally");
    expect(types).toContain("start_timeout");
    expect(types).toContain("change_side");
    expect(types).toContain("add_note");
    expect(types).toContain("undo");
  });

  it("start_game payload includes initial_server_team", () => {
    const btn = MATCH_QUICK_EVENTS.find((e: QuickEventDef) => e.type === "start_game");
    expect(btn).toBeDefined();
    expect(btn!.payload.initial_server_team).toBe("A");
  });

  it("three result buttons are ordered first", () => {
    const types = MATCH_QUICK_EVENTS.map((e: QuickEventDef) => e.type);
    expect(types[0]).toBe("rally_result_a");
    expect(types[1]).toBe("rally_result_b");
    expect(types[2]).toBe("rally_replay");
  });
});
