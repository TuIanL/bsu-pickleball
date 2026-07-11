/** useCaptureRuntime —— 统一前端录制生命周期 Hook */
import { useReducer, useState, useEffect, useCallback, useRef } from "react";
import type {
  CaptureRuntimeState, CaptureStartIntent, UnifiedCaptureSession, NormalizedCaptureStopResult, CaptureMode,
} from "../types/capture";
import { adaptRecordingSession, adaptSyncRecordingSession, normalizeCaptureStopResult } from "../services/captureAdapter";
import {
  startRecording, stopRecording, cancelRecording,
  startSyncRecording, stopSyncRecording, cancelSyncRecording,
  getRecording, getSyncRecording,
} from "../services/analysisClient";
import type { RecordingStartRequest, SyncStartRequest } from "../types/report";

// ── Reducer ──────────────────────────────────────────────────────

export type RuntimeAction =
  | { type: "START"; intent: CaptureStartIntent }
  | { type: "STARTED"; session: UnifiedCaptureSession }
  | { type: "START_FAILED"; error: string }
  | { type: "STOP_REQUESTED" }
  | { type: "STOP_SUCCEEDED"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }
  | { type: "STOP_RESULT_UNKNOWN"; error: string }
  | { type: "RECOVERED"; session: UnifiedCaptureSession; result?: NormalizedCaptureStopResult }
  | { type: "CANCEL_REQUESTED" }
  | { type: "CANCELED"; session: UnifiedCaptureSession }
  | { type: "FAILED"; session: UnifiedCaptureSession | null; error: string }
  | { type: "RESET" };

function captureRuntimeReducer(state: CaptureRuntimeState, action: RuntimeAction): CaptureRuntimeState {
  switch (action.type) {
    case "START":
      return { phase: "starting", intent: action.intent };
    case "STARTED":
      return { phase: "recording", session: action.session };
    case "START_FAILED":
      return { phase: "failed", session: null, result: null, error: action.error };
    case "STOP_REQUESTED":
      if (state.phase !== "recording") return state;
      return { phase: "stopping", session: state.session, operationError: undefined };
    case "STOP_SUCCEEDED":
      return {
        phase: action.result.status === "partial" ? "partial" : "completed",
        session: action.session,
        result: action.result,
      };
    case "STOP_RESULT_UNKNOWN":
      if (state.phase !== "stopping" && state.phase !== "recording") return state;
      return { phase: "recovering", session: state.session, operationError: action.error };
    case "RECOVERED": {
      const rPhase = action.result ? (action.result.status === "partial" ? "partial" as const : "completed" as const) : "failed" as const;
      if (rPhase === "failed") {
        return { phase: "failed", session: action.session, result: action.result ?? null, error: "恢复后状态未知" };
      }
      return { phase: rPhase, session: action.session, result: action.result! };
    }
    case "CANCEL_REQUESTED":
      if (state.phase !== "recording" && state.phase !== "stopping") return state;
      return state;
    case "CANCELED":
      if (state.phase !== "stopping" && state.phase !== "recording" && state.phase !== "recovering") return state;
      return { phase: "canceled", session: action.session };
    case "FAILED":
      return { phase: "failed", session: action.session, result: null, error: action.error };
    case "RESET":
      return { phase: "idle" };
    default:
      return state;
  }
}

// ── Hook ─────────────────────────────────────────────────────────

type UseCaptureRuntimeOptions = {
  fieldSessionId: string;
  onFieldSessionStarted?: (fs: any) => void;
};

export function useCaptureRuntime({ fieldSessionId, onFieldSessionStarted }: UseCaptureRuntimeOptions) {
  const [state, dispatch] = useReducer(captureRuntimeReducer, { phase: "idle" });
  const [elapsedMs, setElapsedMs] = useState(0);
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startClock = useCallback((startedAt: string) => {
    clockRef.current = setInterval(() => {
      setElapsedMs(Math.max(0, Date.now() - Date.parse(startedAt)));
    }, 250);
  }, []);

  const stopClock = useCallback(() => {
    if (clockRef.current) { clearInterval(clockRef.current); clockRef.current = null; }
  }, []);

  // elapsedMs lifecycle
  useEffect(() => {
    if (state.phase === "recording") {
      startClock(state.session.startedAt);
    } else {
      stopClock();
      if (state.phase === "completed" || state.phase === "partial") {
        setElapsedMs(state.result.captureTakeId ? (
          state.result.tracks[0]?.durationMs ?? 0
        ) : 0);
      }
    }
    return stopClock;
  }, [state.phase]);

  // session-specific polling
  useEffect(() => {
    if (state.phase !== "recording") return;
    const sid = state.session.sourceSessionId;
    const mode = state.session.mode;
    const timer = setInterval(async () => {
      try {
        if (mode === "single") {
          const s = await getRecording(sid);
          if (s && (s.status === "failed" || s.status === "completed")) {
            const us = adaptRecordingSession(s);
            dispatch({ type: "FAILED", session: us, error: "录制已在服务端结束" });
          }
        } else {
          const s = await getSyncRecording(sid);
          if (s && (s.status === "failed" || s.status === "completed")) {
            dispatch({ type: "FAILED", session: state.session, error: "双摄录制已在服务端结束" });
          }
        }
      } catch { /* polling failure is non-critical */ }
    }, 5000);
    return () => clearInterval(timer);
  }, [state.phase, (state as any).session?.sourceSessionId]);

  const start = useCallback(async (intent: CaptureStartIntent) => {
    dispatch({ type: "START", intent });

    try {
      if (onFieldSessionStarted) {
        try {
          const { startFieldSession } = await import("../services/analysisClient");
          const fs = await startFieldSession(fieldSessionId);
          onFieldSessionStarted(fs);
        } catch { /* best-effort */ }
      }

      let session: UnifiedCaptureSession;
      if (intent.mode === "single") {
        const req: RecordingStartRequest = {
          camera_id: intent.cameraId,
          field_session_id: fieldSessionId,
          court_name: "",
          match_format: "doubles",
          camera_angle: "baseline_high",
          fps: intent.fps,
          resolution: "1920x1080",
          auto_analyze_after_stop: intent.autoAnalyze,
        };
        const s = await startRecording(req);
        session = adaptRecordingSession(s);
      } else {
        const req: SyncStartRequest = {
          cam_1_id: intent.slots.cam_1,
          cam_2_id: intent.slots.cam_2,
          cam_1_angle: "baseline_high",
          cam_2_angle: "baseline_high",
          field_session_id: fieldSessionId,
          court_name: "",
          match_format: "doubles",
          fps: intent.fps,
          resolution: "1920x1080",
          auto_analyze_after_stop: intent.autoAnalyze,
        };
        const s = await startSyncRecording(req);
        session = adaptSyncRecordingSession(s);
      }
      dispatch({ type: "STARTED", session });
    } catch (e: any) {
      dispatch({ type: "START_FAILED", error: e?.message ?? "启动录制失败" });
    }
  }, [fieldSessionId, onFieldSessionStarted]);

  const stop = useCallback(async () => {
    if (state.phase !== "recording") return;
    dispatch({ type: "STOP_REQUESTED" });

    try {
      const sid = state.session.sourceSessionId;
      const mode = state.session.mode;

      if (mode === "single") {
        const result = await stopRecording(sid);
        const ns = normalizeCaptureStopResult(result as any);
        const refreshed = await getRecording(sid).catch(() => null);
        const session = refreshed ? adaptRecordingSession(refreshed) : state.session;
        dispatch({ type: "STOP_SUCCEEDED", session, result: ns });
      } else {
        const result = await stopSyncRecording(sid);
        const ns = normalizeCaptureStopResult(result as any);
        const refreshed = await getSyncRecording(sid).catch(() => null);
        const session = refreshed ? adaptSyncRecordingSession(refreshed) : state.session;
        dispatch({ type: "STOP_SUCCEEDED", session, result: ns });
      }
    } catch (e: any) {
      dispatch({ type: "STOP_RESULT_UNKNOWN", error: e?.message ?? "停止请求结果未知" });
    }
  }, [state.phase, (state as any).session?.sourceSessionId, (state as any).session?.mode]);

  const recover = useCallback(async () => {
    if (state.phase !== "recovering") return;

    try {
      const sid = state.session.sourceSessionId;
      const mode = state.session.mode;

      let session: UnifiedCaptureSession;
      let result: NormalizedCaptureStopResult | undefined;

      if (mode === "single") {
        const s = await getRecording(sid);
        if (!s) throw new Error("无法获取录制状态");
        session = adaptRecordingSession(s);
        if (s.status === "completed" || s.status === "failed") {
          result = {
            captureTakeId: session.captureTakeId,
            fieldSessionId,
            status: s.status,
            tracks: [],
            analysisAvailable: false,
            warnings: ["从服务器恢复"],
          };
        }
      } else {
        const s = await getSyncRecording(sid);
        if (!s) throw new Error("无法获取录制状态");
        session = adaptSyncRecordingSession(s);
        if (s.status === "completed" || s.status === "failed") {
          result = {
            captureTakeId: session.captureTakeId,
            fieldSessionId,
            status: s.status,
            tracks: [],
            analysisAvailable: false,
            warnings: ["从服务器恢复"],
          };
        }
      }

      dispatch({ type: "RECOVERED", session, result });
    } catch (e: any) {
      dispatch({ type: "FAILED", session: state.session, error: e?.message ?? "恢复失败" });
    }
  }, [state.phase, fieldSessionId, (state as any).session]);

  const cancel = useCallback(async () => {
    if (state.phase !== "recording" && state.phase !== "stopping") return;
    dispatch({ type: "CANCEL_REQUESTED" });

    try {
      const sid = state.session.sourceSessionId;
      const mode = state.session.mode;
      if (mode === "single") {
        const s = await cancelRecording(sid);
        const us = adaptRecordingSession(s);
        dispatch({ type: "CANCELED", session: us });
      } else {
        const s = await cancelSyncRecording(sid);
        const us = adaptSyncRecordingSession(s as any);
        dispatch({ type: "CANCELED", session: us });
      }
    } catch (e: any) {
      dispatch({ type: "FAILED", session: state.session, error: e?.message ?? "取消失败" });
    }
  }, [state.phase, (state as any).session]);

  const reset = useCallback(() => {
    dispatch({ type: "RESET" });
    setElapsedMs(0);
  }, []);

  const captureTakeId = (() => {
    if (state.phase === "recording" || state.phase === "stopping" || state.phase === "recovering") {
      return state.session.captureTakeId;
    }
    if (state.phase === "completed" || state.phase === "partial") {
      return state.result.captureTakeId;
    }
    return null;
  })();

  return {
    phase: state.phase,
    session: (state.phase === "recording" || state.phase === "stopping" || state.phase === "recovering" || state.phase === "completed" || state.phase === "partial")
      ? state.session : (state.phase === "canceled" ? state.session : null),
    result: (state.phase === "completed" || state.phase === "partial" || state.phase === "failed") ? state.result : null,
    error: state.phase === "failed" || state.phase === "recovering" ? (state as any).error ?? "" : "",
    elapsedMs,
    captureTakeId,
    isRecording: state.phase === "recording" || state.phase === "stopping",
    isStopped: state.phase === "completed" || state.phase === "partial" || state.phase === "failed" || state.phase === "canceled",
    start,
    stop,
    cancel,
    recover,
    reset,
  };
}

export { captureRuntimeReducer };
