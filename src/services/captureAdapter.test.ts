import { describe, it, expect } from "vitest";
import { adaptRecordingSession, adaptSyncRecordingSession, normalizeCaptureStopResult } from "../services/captureAdapter";
import type { RecordingSession, SyncRecordingSession, CaptureStopResult } from "../types/report";

describe("captureAdapter", () => {
  it("adaptRecordingSession maps fields correctly", () => {
    const s = {
      session_id: "rec_TEST_001",
      capture_take_id: "take_1",
      camera_id: "cam_a",
      started_at: "2026-07-11T10:00:00Z",
      fps: 60,
      status: "recording",
      auto_analysis_job_id: "job_1",
    } as unknown as RecordingSession;

    const u = adaptRecordingSession(s);
    expect(u.sourceType).toBe("recording");
    expect(u.mode).toBe("single");
    expect(u.tracks[0].slot).toBe("single");
    expect(u.tracks[0].cameraId).toBe("cam_a");
    expect(u.startedAt).toBe("2026-07-11T10:00:00Z");
    expect(u.fps).toBe(60);
    expect(u.autoAnalysisJobId).toBe("job_1");
  });

  it("adaptRecordingSession throws when started_at missing", () => {
    const s = { session_id: "x", started_at: null } as unknown as RecordingSession;
    expect(() => adaptRecordingSession(s)).toThrow("started_at");
  });

  it("adaptSyncRecordingSession maps dual mode", () => {
    const s = {
      session_id: "sync_TEST_001",
      capture_take_id: "take_2",
      started_at: "2026-07-11T10:00:00Z",
      fps: 60,
      status: "recording",
      camera_slots: {
        cam_1: { camera_id: "cam_a" },
        cam_2: { camera_id: "cam_b" },
      },
    } as unknown as SyncRecordingSession;

    const u = adaptSyncRecordingSession(s);
    expect(u.sourceType).toBe("sync_recording");
    expect(u.mode).toBe("dual");
    expect(u.tracks.length).toBe(2);
    expect(u.tracks[0].slot).toBe("cam_1");
    expect(u.tracks[1].slot).toBe("cam_2");
    expect(u.tracks[0].analysisRole).toBe("default");
    expect(u.tracks[1].analysisRole).toBe("supplementary");
  });

  it("adaptSyncRecordingSession throws when started_at missing", () => {
    const s = { session_id: "x", started_at: null } as unknown as SyncRecordingSession;
    expect(() => adaptSyncRecordingSession(s)).toThrow("started_at");
  });

  it("normalizeCaptureStopResult handles missing capture_take", () => {
    const r = { capture_take: undefined, tracks: [], analysis_available: false, warnings: [] } as unknown as CaptureStopResult;
    const n = normalizeCaptureStopResult(r);
    expect(n.captureTakeId).toBe("");
    expect(n.warnings[0]).toContain("缺少 capture_take");
  });

  it("normalizeCaptureStopResult maps fields", () => {
    const r = {
      capture_take: { id: "take_1", field_session_id: "fs_1", status: "completed" },
      tracks: [{ track_id: "t1", slot: "cam_1", camera_id: "cam_a", status: "completed", fragment_count: 3, restart_count: 1 }],
      analysis_available: true,
      default_analysis_video_id: "v1",
    } as unknown as CaptureStopResult;

    const n = normalizeCaptureStopResult(r);
    expect(n.captureTakeId).toBe("take_1");
    expect(n.tracks[0].trackId).toBe("t1");
    expect(n.tracks[0].fragmentCount).toBe(3);
    expect(n.tracks[0].restartCount).toBe(1);
    expect(n.analysisAvailable).toBe(true);
    expect(n.defaultAnalysisVideoId).toBe("v1");
  });
});
