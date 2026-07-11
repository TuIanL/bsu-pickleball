import { describe, it, expect } from "vitest";
import { captureRuntimeReducer, type RuntimeAction } from "../hooks/useCaptureRuntime";
import type { NormalizedCaptureStopResult } from "../types/capture";

describe("captureRuntimeReducer", () => {
  const idle = { phase: "idle" as const };

  const intent = { mode: "single" as const, cameraId: "cam_a", fps: 60, autoAnalyze: false };
  const session = {
    sourceType: "recording" as const, sourceSessionId: "rec_1", captureTakeId: "t1",
    mode: "single" as const, startedAt: "2026-01-01T00:00:00Z", fps: 60,
    status: "recording" as const, tracks: [], cameraDisplayNames: {},
  };

  it("idle → start → recording", () => {
    let s = captureRuntimeReducer(idle, { type: "START", intent });
    expect(s.phase).toBe("starting");
    s = captureRuntimeReducer(s, { type: "STARTED", session });
    expect(s.phase).toBe("recording");
  });

  it("start failure goes to failed", () => {
    let s = captureRuntimeReducer(idle, { type: "START", intent });
    s = captureRuntimeReducer(s, { type: "START_FAILED", error: "no camera" });
    expect(s.phase).toBe("failed");
  });

  it("recording → stop_requested → completed", () => {
    const rec = { phase: "recording" as const, session };
    let s = captureRuntimeReducer(rec, { type: "STOP_REQUESTED" });
    expect(s.phase).toBe("stopping");
  });

  it("recording → stop_result_unknown → recovering → recovered", () => {
    const rec = { phase: "recording" as const, session };
    let s = captureRuntimeReducer(rec, { type: "STOP_RESULT_UNKNOWN", error: "network" });
    expect(s.phase).toBe("recovering");
    s = captureRuntimeReducer(s, { type: "RECOVERED", session, result: undefined });
    expect(s.phase).toBe("failed");
  });

  it("recording → cancel → canceled", () => {
    const rec = { phase: "recording" as const, session };
    let s = captureRuntimeReducer(rec, { type: "CANCEL_REQUESTED" });
    expect(s.phase).toBe("recording"); // CANCEL_REQUESTED doesn't change phase
    s = captureRuntimeReducer(s, { type: "CANCELED", session });
    expect(s.phase).toBe("canceled");
  });

  it("idle → start is rejected", () => {
    const s = captureRuntimeReducer(idle, { type: "STOP_REQUESTED" } as RuntimeAction);
    expect(s.phase).toBe("idle");
  });

  it("completed → reset → idle", () => {
    const comp = { phase: "completed" as const, session, result: { captureTakeId: "t1", fieldSessionId: "fs1", status: "completed", tracks: [], analysisAvailable: true, warnings: [] } };
    const s = captureRuntimeReducer(comp, { type: "RESET" });
    expect(s.phase).toBe("idle");
  });

  it("recovering → stop again → stopping", () => {
    const rec = { phase: "recovering" as const, session, operationError: "timeout" };
    let s = captureRuntimeReducer(rec, { type: "STOP_REQUESTED" });
    expect(s.phase).toBe("stopping");
  });

  it("recovering → cancel → canceled", () => {
    const rec = { phase: "recovering" as const, session, operationError: "timeout" };
    let s = captureRuntimeReducer(rec, { type: "CANCEL_REQUESTED" });
    expect(s.phase).toBe("recovering");
    s = captureRuntimeReducer(s, { type: "CANCELED", session });
    expect(s.phase).toBe("canceled");
  });

  describe("RECOVERED status mapping", () => {
    const rec = { phase: "recovering" as const, session, operationError: "test" };

    it("maps completed status to completed phase", () => {
      const result = { status: "completed", captureTakeId: "t1", fieldSessionId: "fs1", tracks: [{ trackId: "t1", slot: "single", cameraId: "cam_a", analysisRole: "default", status: "completed", fragmentCount: 1, restartCount: 0 }], analysisAvailable: true, warnings: [] } as NormalizedCaptureStopResult;
      const s = captureRuntimeReducer(rec, { type: "RECOVERED", session, result });
      expect(s.phase).toBe("completed");
    });

    it("maps partial status to partial phase", () => {
      const result = { status: "partial", captureTakeId: "t1", fieldSessionId: "fs1", tracks: [], analysisAvailable: false, warnings: [] } as NormalizedCaptureStopResult;
      const s = captureRuntimeReducer(rec, { type: "RECOVERED", session, result });
      expect(s.phase).toBe("partial");
    });

    it("maps failed status to failed phase", () => {
      const result = { status: "failed", captureTakeId: "t1", fieldSessionId: "fs1", tracks: [], analysisAvailable: false, warnings: ["录制失败"] } as NormalizedCaptureStopResult;
      const s = captureRuntimeReducer(rec, { type: "RECOVERED", session, result });
      expect(s.phase).toBe("failed");
    });

    it("maps missing result to failed phase", () => {
      const s = captureRuntimeReducer(rec, { type: "RECOVERED", session, result: undefined });
      expect(s.phase).toBe("failed");
    });
  });
});
