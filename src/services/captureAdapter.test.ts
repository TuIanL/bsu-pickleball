import { describe, it, expect } from "vitest";
import { adaptRecordingSession, adaptSyncRecordingSession, normalizeCaptureStopResult, normalizeRecoveredSingleResult, normalizeRecoveredDualResult, phaseFromStopStatus } from "../services/captureAdapter";
import type { RecordingSession, SyncRecordingSession, CaptureStopResult, CaptureTakeSummary } from "../types/report";

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

  describe("phaseFromStopStatus", () => {
    it("maps completed", () => {
      expect(phaseFromStopStatus("completed")).toBe("completed");
    });
    it("maps partial", () => {
      expect(phaseFromStopStatus("partial")).toBe("partial");
    });
    it("maps failed", () => {
      expect(phaseFromStopStatus("failed")).toBe("failed");
    });
    it("maps unknown to failed", () => {
      expect(phaseFromStopStatus("unknown" as any)).toBe("failed");
    });
  });

  describe("normalizeRecoveredSingleResult", () => {
    const session = {
      session_id: "rec_001",
      camera_id: "cam_a",
      status: "completed",
      duration_sec: 45,
      video_id: "vid_001",
      field_session_id: "fs_001",
    } as unknown as RecordingSession;

    it("restores videoId and durationMs from completed take", () => {
      const take = { id: "take_001", status: "completed", duration_ms: 45000 } as CaptureTakeSummary;
      const r = normalizeRecoveredSingleResult(session, take);
      expect(r.captureTakeId).toBe("take_001");
      expect(r.status).toBe("completed");
      expect(r.tracks).toHaveLength(1);
      expect(r.tracks[0].videoId).toBe("vid_001");
      expect(r.tracks[0].durationMs).toBe(45000);
      expect(r.tracks[0].cameraId).toBe("cam_a");
      expect(r.analysisAvailable).toBe(true);
      expect(r.defaultAnalysisVideoId).toBe("vid_001");
    });

    it("maps partial take status", () => {
      const take = { id: "take_002", status: "partial" } as CaptureTakeSummary;
      const r = normalizeRecoveredSingleResult(session, take);
      expect(r.status).toBe("partial");
    });

    it("maps failed take status", () => {
      const take = { id: "take_003", status: "failed" } as CaptureTakeSummary;
      const r = normalizeRecoveredSingleResult(session, take);
      expect(r.status).toBe("failed");
    });

    it("sets analysisAvailable false when video_id missing", () => {
      const s = { ...session, video_id: undefined } as unknown as RecordingSession;
      const take = { id: "take_004", status: "completed" } as CaptureTakeSummary;
      const r = normalizeRecoveredSingleResult(s, take);
      expect(r.analysisAvailable).toBe(false);
      expect(r.defaultAnalysisVideoId).toBeUndefined();
    });
  });

  describe("normalizeRecoveredDualResult", () => {
    const session = {
      session_id: "sync_001",
      status: "completed",
      duration_sec: 60,
      field_session_id: "fs_001",
      default_analysis_video_id: "vid_cam1",
      registered_video_ids: { cam_1: "vid_cam1", cam_2: "vid_cam2" },
      camera_slots: {
        cam_1: { camera_id: "cam_a", role: "cam_1", camera_angle: "baseline_high", stream_url_snapshot: "" },
        cam_2: { camera_id: "cam_b", role: "cam_2", camera_angle: "baseline_high", stream_url_snapshot: "" },
      },
      segments: [{ segment_index: 1, status: "completed", files: [], restart_count: 0 }],
      total_restarts: 2,
    } as unknown as SyncRecordingSession;

    it("restores both tracks with videoIds", () => {
      const take = { id: "take_dual_001", status: "completed", duration_ms: 60000 } as CaptureTakeSummary;
      const r = normalizeRecoveredDualResult(session, take);
      expect(r.status).toBe("completed");
      expect(r.tracks).toHaveLength(2);
      expect(r.tracks[0].slot).toBe("cam_1");
      expect(r.tracks[0].videoId).toBe("vid_cam1");
      expect(r.tracks[0].analysisRole).toBe("default");
      expect(r.tracks[1].slot).toBe("cam_2");
      expect(r.tracks[1].videoId).toBe("vid_cam2");
      expect(r.tracks[1].analysisRole).toBe("supplementary");
      expect(r.analysisAvailable).toBe(true);
      expect(r.defaultAnalysisVideoId).toBe("vid_cam1");
      expect(r.tracks[0].restartCount).toBe(2);
    });

    it("maps partial take status to partial", () => {
      const take = { id: "take_dual_002", status: "partial" } as CaptureTakeSummary;
      const r = normalizeRecoveredDualResult(session, take);
      expect(r.status).toBe("partial");
    });
  });
});
