import { describe, expect, it } from "vitest";
import { computeTicks, toTimelineMarkers } from "./timelineScale";
import type { TimelineEventType } from "../../types/report";

type MarkerEvent = Parameters<typeof toTimelineMarkers>[0][number];

function markerEvent(
  event_type: TimelineEventType,
  id: string,
  timestamp_ms: number,
  payload_json: MarkerEvent["payload_json"] = {},
): MarkerEvent {
  return { event_type, id, timestamp_ms, payload_json };
}

describe("computeTicks", () => {
  it("returns empty array for zero duration", () => {
    expect(computeTicks(0, 0, 600)).toEqual([]);
  });

  it("returns empty array for duration under 1s", () => {
    expect(computeTicks(0, 500, 600)).toEqual([]);
  });

  it("returns empty array for zero container width", () => {
    expect(computeTicks(0, 60000, 0)).toEqual([]);
  });

  it("generates ticks for 30s window at 600px", () => {
    const ticks = computeTicks(0, 30000, 600, 72);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    expect(ticks[ticks.length - 1].label).toBe("0:30");
    ticks.forEach(t => {
      expect(t.positionPct).toBeGreaterThanOrEqual(0);
      expect(t.positionPct).toBeLessThanOrEqual(100);
    });
  });

  it("generates ticks for 5min window", () => {
    const ticks = computeTicks(0, 300000, 600, 72);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    expect(ticks[0].label).toMatch(/^\d/);
    const lastLabel = ticks[ticks.length - 1].label;
    expect(lastLabel).toBe("5:00");
  });

  it("generates ticks for 90min window with hour format", () => {
    const ticks = computeTicks(0, 5400000, 600, 72);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    const lastLabel = ticks[ticks.length - 1].label;
    expect(lastLabel).toBe("1:30:00");
  });

  it("generates ticks for 6h window", () => {
    const ticks = computeTicks(0, 21600000, 600, 72);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    expect(ticks[ticks.length - 1].label).toBe("6:00:00");
  });

  it("handles non-zero window start", () => {
    const ticks = computeTicks(12345, 102345, 600, 72);
    expect(ticks.length).toBeGreaterThanOrEqual(1);
    ticks.forEach(t => {
      expect(t.positionPct).toBeGreaterThanOrEqual(0);
      expect(t.positionPct).toBeLessThanOrEqual(100);
    });
  });

  it("uses wider spacing for wider container", () => {
    const narrowTicks = computeTicks(0, 300000, 300, 72);
    const wideTicks = computeTicks(0, 300000, 1200, 72);
    expect(wideTicks.length).toBeGreaterThan(narrowTicks.length);
  });

  it("positions are monotonic increasing", () => {
    const ticks = computeTicks(0, 300000, 600, 72);
    for (let i = 1; i < ticks.length; i++) {
      expect(ticks[i].positionPct).toBeGreaterThan(ticks[i - 1].positionPct);
    }
  });
});

describe("toTimelineMarkers", () => {
  it("extracts side_change markers", () => {
    const events = [markerEvent("side_change", "e1", 5000)];
    const markers = toTimelineMarkers(events);
    expect(markers).toHaveLength(1);
    expect(markers[0].track).toBe("side_change");
    expect(markers[0].timestampMs).toBe(5000);
  });

  it("extracts highlight add_note markers", () => {
    const events = [markerEvent("add_note", "e2", 10000, { highlight: true })];
    const markers = toTimelineMarkers(events);
    expect(markers).toHaveLength(1);
    expect(markers[0].track).toBe("highlight");
  });

  it("extracts highlighted session_note", () => {
    const events = [markerEvent("session_note", "e3", 15000, { highlight: true })];
    const markers = toTimelineMarkers(events);
    expect(markers).toHaveLength(1);
    expect(markers[0].track).toBe("highlight");
  });

  it("extracts timeout markers", () => {
    const events = [markerEvent("non_play_start", "e4", 20000, { intermission_kind: "timeout" })];
    const markers = toTimelineMarkers(events);
    expect(markers).toHaveLength(1);
    expect(markers[0].track).toBe("timeout");
  });

  it("filters non-highlight add_note", () => {
    const events = [markerEvent("add_note", "e5", 25000, { highlight: false })];
    const markers = toTimelineMarkers(events);
    expect(markers).toHaveLength(0);
  });
});
