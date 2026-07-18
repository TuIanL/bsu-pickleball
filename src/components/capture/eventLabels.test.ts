import { describe, expect, it } from "vitest";
import { formatTimelineEventLabel } from "./eventLabels";

describe("formatTimelineEventLabel", () => {
  const segments = [
    { segment_type: "set", ordinal: 1, start_ms: 0, end_ms: 60000 },
    { segment_type: "game", ordinal: 1, start_ms: 5000, end_ms: 60000 },
    { segment_type: "rally", ordinal: 1, start_ms: 5000, end_ms: 15000 },
    { segment_type: "rally", ordinal: 2, start_ms: 20000, end_ms: 35000 },
  ];

  it("returns event label when present and not matching event_type", () => {
    const label = formatTimelineEventLabel({ event_type: "add_note", label: "精彩扣杀", timestamp_ms: 10000 }, segments);
    expect(label).toBe("精彩扣杀");
  });

  it("maps known event type with ordinal", () => {
    const label = formatTimelineEventLabel({ event_type: "rally_start", timestamp_ms: 5000 }, segments);
    expect(label).toBe("第 1 分");
  });

  it("maps known event type without segment match", () => {
    const label = formatTimelineEventLabel({ event_type: "side_change", timestamp_ms: 99999 }, segments);
    expect(label).toBe("换边");
  });

  it("falls back to raw event_type for unknown types", () => {
    const label = formatTimelineEventLabel({ event_type: "unknown_event_x", timestamp_ms: 10000 }, segments);
    expect(label).toBe("unknown_event_x");
  });
});
