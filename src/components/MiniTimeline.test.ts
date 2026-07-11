import { describe, expect, it } from "vitest";
import { deriveNonPlayRanges } from "./MiniTimeline";
import type { SessionTimelineEvent } from "../types/report";

function makeEvent(
  event_type: string,
  timestamp_ms: number,
  overrides?: Partial<SessionTimelineEvent>,
): SessionTimelineEvent {
  return {
    id: `evt_${timestamp_ms}`,
    field_session_id: "fs_test",
    timestamp_ms,
    occurred_at: new Date().toISOString(),
    event_type: event_type as any,
    source: "manual",
    label: "",
    note: "",
    payload_json: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("deriveNonPlayRanges", () => {
  it("returns empty array for no events", () => {
    const ranges = deriveNonPlayRanges([], 10000);
    expect(ranges).toEqual([]);
  });

  it("returns empty array for non-relevant events", () => {
    const events = [
      makeEvent("side_change", 1000),
      makeEvent("session_note", 2000),
    ];
    const ranges = deriveNonPlayRanges(events, 10000);
    expect(ranges).toEqual([]);
  });

  it("creates one range from start to end", () => {
    const events = [
      makeEvent("non_play_start", 1000),
      makeEvent("non_play_end", 5000),
    ];
    const ranges = deriveNonPlayRanges(events, 10000);
    expect(ranges).toHaveLength(1);
    expect(ranges[0].startMs).toBe(1000);
    expect(ranges[0].endMs).toBe(5000);
  });

  it("uses elapsedMs for open range", () => {
    const events = [
      makeEvent("non_play_start", 2000),
    ];
    const ranges = deriveNonPlayRanges(events, 8000);
    expect(ranges).toHaveLength(1);
    expect(ranges[0].startMs).toBe(2000);
    expect(ranges[0].endMs).toBe(8000);
  });

  it("preserves timeout and side-change interval kinds", () => {
    const ranges = deriveNonPlayRanges([
      makeEvent("non_play_start", 1000, { payload_json: { intermission_kind: "timeout" } }),
      makeEvent("non_play_end", 2000),
      makeEvent("non_play_start", 3000, { payload_json: { intermission_kind: "side_change" } }),
    ], 5000);
    expect(ranges.map((range) => range.kind)).toEqual(["timeout", "side_change"]);
    expect(ranges[1].endMs).toBe(5000);
  });

  it("handles multiple start-end pairs", () => {
    const events = [
      makeEvent("non_play_start", 1000),
      makeEvent("non_play_end", 3000),
      makeEvent("non_play_start", 5000),
      makeEvent("non_play_end", 7000),
    ];
    const ranges = deriveNonPlayRanges(events, 10000);
    expect(ranges).toHaveLength(2);
    expect(ranges[0].startMs).toBe(1000);
    expect(ranges[0].endMs).toBe(3000);
    expect(ranges[1].startMs).toBe(5000);
    expect(ranges[1].endMs).toBe(7000);
  });

  it("ignores consecutive start (second start is skipped)", () => {
    const events = [
      makeEvent("non_play_start", 1000),
      makeEvent("non_play_start", 2000), // should be ignored
      makeEvent("non_play_end", 5000),
    ];
    const ranges = deriveNonPlayRanges(events, 10000);
    expect(ranges).toHaveLength(1);
    expect(ranges[0].startMs).toBe(1000);
    expect(ranges[0].endMs).toBe(5000);
  });

  it("ignores orphaned end (no matching start)", () => {
    const events = [
      makeEvent("non_play_end", 3000), // orphan, should be ignored
      makeEvent("non_play_start", 5000),
      makeEvent("non_play_end", 7000),
    ];
    const ranges = deriveNonPlayRanges(events, 10000);
    expect(ranges).toHaveLength(1);
    expect(ranges[0].startMs).toBe(5000);
    expect(ranges[0].endMs).toBe(7000);
  });


});
