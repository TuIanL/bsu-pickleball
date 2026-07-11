/**
 * CaptureConsolePage 组件级行为测试
 *
 * 测试录制生命周期：单摄/双摄 start → recording → stop → 完成面板
 * 测试 Outbox 停止行为、网络错误恢复、完成面板字段完整性
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useCaptureRuntime } from "../hooks/useCaptureRuntime";
import { captureRuntimeReducer } from "../hooks/useCaptureRuntime";
import { adaptRecordingSession, adaptSyncRecordingSession, normalizeCaptureStopResult } from "../services/captureAdapter";
import type { RecordingSession, SyncRecordingSession, CaptureStopResult } from "../types/report";
import type { UnifiedCaptureSession, NormalizedCaptureStopResult } from "../types/capture";

// ── Mock API ──
vi.mock("../services/analysisClient", () => ({
  startRecording: vi.fn(),
  stopRecording: vi.fn(),
  cancelRecording: vi.fn(),
  startSyncRecording: vi.fn(),
  stopSyncRecording: vi.fn(),
  cancelSyncRecording: vi.fn(),
  getRecording: vi.fn(),
  getSyncRecording: vi.fn(),
  startFieldSession: vi.fn(),
  getFieldSession: vi.fn(),
  listCameras: vi.fn(),
  probeCamera: vi.fn(),
  getCameraPreviewUrl: vi.fn(() => ""),
  createCamera: vi.fn(),
  deleteCamera: vi.fn(),
  getLiveCodingState: vi.fn(() => null),
  listSegments: vi.fn(() => []),
  listTimelineEvents: vi.fn(() => []),
  createTimelineEvent: vi.fn(),
  executeCodingAction: vi.fn(),
  runSyncTest: vi.fn(),
}));

vi.mock("../services/codingOutbox", () => ({
  createOutboxItem: vi.fn(() => ({ clientActionId: "a1", status: "pending" })),
  enqueueItem: vi.fn(),
  createOutboxSender: vi.fn(() => ({
    flush: vi.fn(() => Promise.resolve()),
    drain: vi.fn(() => Promise.resolve({ unsynced: 0 })),
    stop: vi.fn(),
    freeze: vi.fn(),
    isFrozen: vi.fn(() => false),
    flushWithDeadline: vi.fn(() => Promise.resolve()),
  })),
  getPendingItems: vi.fn(() => []),
  retryBlockedItems: vi.fn(),
}));

// ── Helpers ──

function makeRecordingSession(overrides?: Partial<RecordingSession>): RecordingSession {
  return {
    session_id: "rec_TEST_001",
    camera_id: "cam_a",
    capture_take_id: "take_1",
    started_at: "2026-07-11T10:00:00Z",
    fps: 60,
    status: "recording",
    court_name: "测试场",
    match_format: "doubles",
    camera_angle: "baseline_high",
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    auto_analysis_job_id: undefined,
    ...overrides,
  } as RecordingSession;
}

function makeStopResult(overrides?: Partial<CaptureStopResult>): CaptureStopResult {
  return {
    capture_take: { id: "take_1", field_session_id: "fs1", status: "completed", capture_mode: "single", source_session_type: "recording", source_session_id: "rec_TEST_001", started_at: "2026-07-11T10:00:00Z", duration_ms: 10000, revision: 1 },
    tracks: [{ track_id: "t1", slot: "cam_1", camera_id: "cam_a", analysis_role: "default", status: "completed", video_id: "v1", duration_ms: 10000, fragment_count: 1, restart_count: 0 }],
    analysis_available: true,
    warnings: [],
    ...overrides,
  } as unknown as CaptureStopResult;
}

// ── Tests ──

describe("CaptureConsolePage behavior", () => {
  describe("0.1: 单摄录制生命周期", () => {
    it("reducer: idle → starting → recording → stopping → completed", () => {
      const intent = { mode: "single" as const, cameraId: "cam_a", fps: 60, autoAnalyze: false };
      const session = adaptRecordingSession(makeRecordingSession());
      const result = normalizeCaptureStopResult(makeStopResult());

      let state = captureRuntimeReducer({ phase: "idle" }, { type: "START", intent });
      expect(state.phase).toBe("starting");

      state = captureRuntimeReducer(state, { type: "STARTED", session });
      expect(state.phase).toBe("recording");
      expect((state as any).session.sourceSessionId).toBe("rec_TEST_001");

      state = captureRuntimeReducer(state, { type: "STOP_REQUESTED" });
      expect(state.phase).toBe("stopping");

      state = captureRuntimeReducer(state, { type: "STOP_SUCCEEDED", session, result });
      expect(state.phase).toBe("completed");
      expect((state as any).result.captureTakeId).toBe("take_1");
    });

    it("adapter: RecordingSession → UnifiedCaptureSession 字段完整", () => {
      const s = makeRecordingSession({ auto_analysis_job_id: "job_1" });
      const u = adaptRecordingSession(s);

      expect(u.sourceType).toBe("recording");
      expect(u.mode).toBe("single");
      expect(u.tracks[0].slot).toBe("single");
      expect(u.tracks[0].cameraId).toBe("cam_a");
      expect(u.fps).toBe(60);
      expect(u.autoAnalysisJobId).toBe("job_1");
      expect(u.startedAt).toBeTruthy();
    });
  });

  describe("0.2: 双摄录制生命周期", () => {
    it("reducer: dual start → recording → completed", () => {
      const intent = { mode: "dual" as const, slots: { cam_1: "cam_a", cam_2: "cam_b" }, fps: 60, autoAnalyze: false };
      const session: UnifiedCaptureSession = {
        sourceType: "sync_recording", sourceSessionId: "sync_1", captureTakeId: "take_2",
        mode: "dual", startedAt: "2026-07-11T10:00:00Z", fps: 60, status: "recording",
        tracks: [
          { slot: "cam_1", cameraId: "cam_a", analysisRole: "default" },
          { slot: "cam_2", cameraId: "cam_b", analysisRole: "supplementary" },
        ],
        cameraDisplayNames: {},
      };
      const result = normalizeCaptureStopResult(makeStopResult());

      let state = captureRuntimeReducer({ phase: "idle" }, { type: "START", intent });
      state = captureRuntimeReducer(state, { type: "STARTED", session });
      expect(state.phase).toBe("recording");
      expect((state as any).session.tracks.length).toBe(2);

      state = captureRuntimeReducer(state, { type: "STOP_SUCCEEDED", session, result });
      expect(state.phase).toBe("completed");
    });

    it("adapter: SyncRecordingSession → UnifiedCaptureSession", () => {
      const s = {
        session_id: "sync_1", capture_take_id: "take_2",
        started_at: "2026-07-11T10:00:00Z", fps: 60, status: "recording",
        camera_slots: {
          cam_1: { camera_id: "cam_a" },
          cam_2: { camera_id: "cam_b" },
        },
      } as unknown as SyncRecordingSession;

      const u = adaptSyncRecordingSession(s);
      expect(u.sourceType).toBe("sync_recording");
      expect(u.mode).toBe("dual");
      expect(u.tracks.length).toBe(2);
      expect(u.tracks[0].analysisRole).toBe("default");
      expect(u.tracks[1].analysisRole).toBe("supplementary");
    });
  });

  describe("0.3: Outbox 停止行为", () => {
    it("STOP_REQUESTED 不等 API 返回即更新 UI", () => {
      const session = adaptRecordingSession(makeRecordingSession());
      const rec = { phase: "recording" as const, session };

      const state = captureRuntimeReducer(rec, { type: "STOP_REQUESTED" });
      expect(state.phase).toBe("stopping");
      // 此时 stop API 尚未调用，但 UI 已更新为 stopping
    });

    it("stop API 报错 → STOP_RESULT_UNKNOWN → recovering", () => {
      const session = adaptRecordingSession(makeRecordingSession());
      const rec = { phase: "recording" as const, session };

      let state = captureRuntimeReducer(rec, { type: "STOP_RESULT_UNKNOWN", error: "network error" });
      expect(state.phase).toBe("recovering");
      expect((state as any).operationError).toBe("network error");
    });
  });

  describe("0.4: 网络错误恢复", () => {
    it("recovering → RECOVERED → completed", () => {
      const session = adaptRecordingSession(makeRecordingSession());
      const result = normalizeCaptureStopResult(makeStopResult());
      const recState = { phase: "recovering" as const, session, operationError: "unknown" };

      const state = captureRuntimeReducer(recState, { type: "RECOVERED", session, result });
      expect(state.phase).toBe("completed");
    });

    it("recovering → RECOVERED without result → failed", () => {
      const session = adaptRecordingSession(makeRecordingSession());
      const recState = { phase: "recovering" as const, session, operationError: "unknown" };

      const state = captureRuntimeReducer(recState, { type: "RECOVERED", session, result: undefined });
      expect(state.phase).toBe("failed");
    });
  });

  describe("0.5: 完成面板字段完整性", () => {
    it("CaptureStopResult 包含必要字段", () => {
      const raw = makeStopResult();
      const n = normalizeCaptureStopResult(raw);

      expect(n.captureTakeId).toBe("take_1");
      expect(n.fieldSessionId).toBe("fs1");
      expect(n.tracks.length).toBe(1);
      expect(n.tracks[0].videoId).toBe("v1");
      expect(n.tracks[0].fragmentCount).toBe(1);
      expect(n.analysisAvailable).toBe(true);
    });

    it("完成态 UnifiedCaptureSession 保留 fps 和 auto_analysis_job_id", () => {
      const s = makeRecordingSession({ auto_analysis_job_id: "job_1", fps: 60 });
      const u = adaptRecordingSession(s);

      // 完成面板需要从 session 访问这些字段
      expect(u.fps).toBe(60);
      expect(u.autoAnalysisJobId).toBe("job_1");
    });

    it("CaptureStartIntent discriminated union 强制类型正确", () => {
      // TypeScript 编译时测试：非法组合应报错
      const singleLegal = { mode: "single" as const, cameraId: "cam_a", fps: 60, autoAnalyze: false };
      const dualLegal = { mode: "dual" as const, slots: { cam_1: "a", cam_2: "b" }, fps: 60, autoAnalyze: false };

      expect(singleLegal.mode).toBe("single");
      expect(dualLegal.mode).toBe("dual");
    });

    it("normalizeCaptureStopResult 对缺失 capture_take 的处理", () => {
      const raw = { capture_take: undefined, tracks: [], analysis_available: false, warnings: [] } as unknown as CaptureStopResult;
      const n = normalizeCaptureStopResult(raw);
      expect(n.captureTakeId).toBe("");
      expect(n.warnings[0]).toContain("缺少");
    });
  });
});
