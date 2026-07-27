import { describe, expect, it } from "vitest";
import { quickEventsForMode, MATCH_QUICK_EVENTS, PRACTICE_QUICK_EVENTS, ENGINEERING_QUICK_EVENTS } from "./timelineQuickEvents";

describe("timelineQuickEvents", () => {
  it("returns match events for 'match' mode", () => {
    const events = quickEventsForMode("match");
    expect(events).toBe(MATCH_QUICK_EVENTS);
    expect(events.length).toBeGreaterThan(3);
    expect(events.some((e) => e.type === "start_set")).toBe(true);
    expect(events.some((e) => e.type === "start_game")).toBe(true);
    expect(events.some((e) => e.type === "change_side")).toBe(true);
    expect(events.find((e) => e.type === "start_game")?.payload.initial_server_team).toBeUndefined();
  });

  it("returns practice events for 'practice' mode", () => {
    const events = quickEventsForMode("practice");
    expect(events).toBe(PRACTICE_QUICK_EVENTS);
    expect(events.some((e) => e.type === "add_note")).toBe(true);
  });

  it("returns engineering events for 'engineering' mode", () => {
    const events = quickEventsForMode("engineering");
    expect(events).toBe(ENGINEERING_QUICK_EVENTS);
    expect(events.some((e) => e.type === "add_note")).toBe(true);
  });

  it("defaults to practice events for unknown mode", () => {
    const events = quickEventsForMode("unknown");
    expect(events).toBe(PRACTICE_QUICK_EVENTS);
  });

  it("all events have valid type and source", () => {
    const allEvents = [...MATCH_QUICK_EVENTS, ...PRACTICE_QUICK_EVENTS, ...ENGINEERING_QUICK_EVENTS];
    for (const event of allEvents) {
      expect(event.source).toBe("manual");
      expect(typeof event.type).toBe("string");
      expect(event.type.length).toBeGreaterThan(0);
      expect(typeof event.label).toBe("string");
    }
  });
});
