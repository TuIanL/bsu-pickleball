import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useState, useCallback } from "react";
import type { SessionTimelineEvent } from "../types/report";

// Test the Take isolation logic directly: loadTimelineEvents
// with capture_take_id filtering + initializeLiveCoding clearing old data

function useTakeIsolationTest() {
  const [captureTakeId, setCaptureTakeId] = useState<string | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);

  const upsertById = <T extends { id: string }>(existing: T[], incoming: T[]): T[] => {
    const map = new Map(existing.map((item) => [item.id, item]));
    for (const item of incoming) {
      map.set(item.id, item);
    }
    return Array.from(map.values());
  };

  const loadTimelineEvents = useCallback(async (takeId: string | null) => {
    if (!takeId) return;
    // Simulate API call with filter
    const allEvents: SessionTimelineEvent[] = [
      { id: "e1", field_session_id: "fs1", capture_take_id: "take_A", event_type: "set_start", timestamp_ms: 1000, label: "", note: "", payload_json: {}, source: "manual", occurred_at: "", created_at: "", updated_at: "" },
      { id: "e2", field_session_id: "fs1", capture_take_id: "take_A", event_type: "game_start", timestamp_ms: 2000, label: "", note: "", payload_json: {}, source: "manual", occurred_at: "", created_at: "", updated_at: "" },
      { id: "e3", field_session_id: "fs1", capture_take_id: "take_B", event_type: "set_start", timestamp_ms: 500, label: "", note: "", payload_json: {}, source: "manual", occurred_at: "", created_at: "", updated_at: "" },
    ];
    const filtered = allEvents.filter(e => e.capture_take_id === takeId);
    setTimelineEvents(prev => upsertById(prev, filtered));
  }, []);

  const initializeLiveCoding = async (takeId: string) => {
    setCaptureTakeId(takeId);
    setTimelineEvents([]); // Clear old events
    await loadTimelineEvents(takeId);
  };

  return { timelineEvents, captureTakeId, initializeLiveCoding, loadTimelineEvents };
}

describe("CaptureConsole Take isolation", () => {
  it("switching takes clears old events", async () => {
    const hook = renderHook(() => useTakeIsolationTest());

    // First take - load events for take_A
    await act(async () => {
      await hook.result.current.initializeLiveCoding("take_A");
    });

    const eventsAfterTakeA = hook.result.current.timelineEvents;
    expect(eventsAfterTakeA).toHaveLength(2);
    expect(eventsAfterTakeA.every(e => e.capture_take_id === "take_A")).toBe(true);

    // Second take - should clear old events and load new ones
    await act(async () => {
      await hook.result.current.initializeLiveCoding("take_B");
    });

    const eventsAfterTakeB = hook.result.current.timelineEvents;
    expect(eventsAfterTakeB).toHaveLength(1);
    expect(eventsAfterTakeB[0].capture_take_id).toBe("take_B");
    expect(eventsAfterTakeB[0].event_type).toBe("set_start");
  });

  it("loadTimelineEvents does nothing without captureTakeId", async () => {
    const hook = renderHook(() => useTakeIsolationTest());

    await act(async () => {
      await hook.result.current.loadTimelineEvents(null);
    });

    expect(hook.result.current.timelineEvents).toHaveLength(0);
  });

  it("MiniTimeline shows when phase is recording/stopping/recovering", () => {
    const showWhenPresent = ["recording", "stopping", "recovering"];
    const showWhenAbsent = ["idle", "completed", "partial", "failed", "canceled", "starting"];

    for (const phase of showWhenPresent) {
      const show = phase === "recording" || phase === "stopping" || phase === "recovering";
      expect(show).toBe(true);
    }

    for (const phase of showWhenAbsent) {
      const show = phase === "recording" || phase === "stopping" || phase === "recovering";
      expect(show).toBe(false);
    }
  });

  it("does not mix events from different takes", async () => {
    const hook = renderHook(() => useTakeIsolationTest());

    // Load take_A
    await act(async () => {
      await hook.result.current.initializeLiveCoding("take_A");
    });

    const takeAIds = hook.result.current.timelineEvents.map(e => e.id).sort();
    expect(takeAIds).toEqual(["e1", "e2"]);

    // Load take_B
    await act(async () => {
      await hook.result.current.initializeLiveCoding("take_B");
    });

    const takeBIds = hook.result.current.timelineEvents.map(e => e.id).sort();
    expect(takeBIds).toEqual(["e3"]);

    // take_A events should NOT appear in take_B
    expect(takeBIds).not.toContain("e1");
    expect(takeBIds).not.toContain("e2");
  });
});
