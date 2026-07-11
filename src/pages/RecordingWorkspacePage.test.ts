import { describe, expect, it } from "vitest";
import type { RecordingSession, SessionTimelineEvent } from "../types/report";
import { eventsForRecording } from "./RecordingWorkspacePage";

const recording: RecordingSession = {
  session_id: "rec-current",
  capture_take_id: "take-current",
  camera_id: "camera-1",
  court_name: "Court 1",
  match_format: "singles",
  camera_angle: "baseline_high",
  fps: 60,
  resolution: "1920x1080",
  auto_analyze_after_stop: false,
  status: "completed",
  started_at: "2026-07-11T02:45:06.000Z",
  stopped_at: "2026-07-11T02:46:46.000Z",
  duration_sec: 100,
};

function event(id: string, overrides: Partial<SessionTimelineEvent> = {}): SessionTimelineEvent {
  return {
    id,
    field_session_id: "fs-1",
    timestamp_ms: 1000,
    occurred_at: "2026-07-11T02:45:30.000Z",
    event_type: "session_note",
    source: "manual",
    label: "重点片段",
    note: "",
    payload_json: { highlight: true },
    created_at: "2026-07-11T02:45:30.000Z",
    updated_at: "2026-07-11T02:45:30.000Z",
    ...overrides,
  };
}

describe("eventsForRecording", () => {
  it("keeps Take and recording-scoped events", () => {
    const events = eventsForRecording([
      event("take", { capture_take_id: "take-current" }),
      event("recording", { recording_session_id: "rec-current" }),
    ], recording);

    expect(events.map((item) => item.id)).toEqual(["take", "recording"]);
  });

  it("keeps legacy unscoped events only inside the recording window", () => {
    const events = eventsForRecording([
      event("legacy-in-window"),
      event("legacy-outside", { occurred_at: "2026-07-11T02:47:00.000Z" }),
    ], recording);

    expect(events.map((item) => item.id)).toEqual(["legacy-in-window"]);
  });

  it("does not mix events explicitly assigned to another recording or Take", () => {
    const events = eventsForRecording([
      event("other-take", { capture_take_id: "take-other" }),
      event("other-recording", { recording_session_id: "rec-other" }),
    ], recording);

    expect(events).toEqual([]);
  });
});
