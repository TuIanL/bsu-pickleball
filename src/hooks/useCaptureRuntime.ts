/** useCaptureRuntime —— 统一前端录制生命周期 Hook */
import { useReducer, useState, useEffect, useCallback, useRef } from "react";
import type {
  CaptureRuntimeState, CaptureStartIntent, UnifiedCaptureSession, NormalizedCaptureStopResult, CaptureMode,
} from "../types/capture";
import {
  adaptRecordingSession, adaptSyncRecordingSession, normalizeCaptureStopResult,
  normalizeRecoveredSingleResult, normalizeRecoveredDualResult, phaseFromStopStatus,
} from "../services/captureAdapter";
import {
  startRecording, stopRecording, cancelRecording,
  startSyncRecording, stopSyncRecording, cancelSyncRecording,
  getRecording, getSyncRecording, getCaptureTake,
  listRecordings, listSyncRecordings,
} from "../services/analysisClient";
import type { RecordingStartRequest, SyncStartRequest, CaptureTakeSummary } from "../types/report";

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
  | { type: "RESET" }
  // ── Hydration actions ──
  | { type: "HYDRATE_REQUESTED" }
  | { type: "ACTIVE_SESSION_FOUND"; session: UnifiedCaptureSession }
  | { type: "NO_ACTIVE_SESSION" }
  | { type: "HYDRATE_FAILED"; error: string };

function captureRuntimeReducer(state: CaptureRuntimeState, action: RuntimeAction): CaptureRuntimeState {
  switch (action.type) {
    // ── Hydration ──
    case "HYDRATE_REQUESTED":
      return { phase: "hydrating" };
    case "ACTIVE_SESSION_FOUND":
      return { phase: "recording", session: action.session };
    case "NO_ACTIVE_SESSION":
      return { phase: "idle" };
    case "HYDRATE_FAILED":
      return { phase: "hydration_failed", error: action.error };
    // ── Start ──
    case "START":
      return { phase: "starting", intent: action.intent };
    case "STARTED":
      return { phase: "recording", session: action.session };
    case "START_FAILED":
      return { phase: "failed", session: null, result: null, error: action.error };
    case "STOP_REQUESTED":
      if (state.phase !== "recording" && state.phase !== "recovering") return state;
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
      const rPhase = action.result ? phaseFromStopStatus(action.result.status) : "failed" as const;
      if (rPhase === "failed") {
        return { phase: "failed", session: action.session, result: action.result ?? null, error: action.result?.warnings?.[0] ?? "恢复后状态未知" };
      }
      return { phase: rPhase, session: action.session, result: action.result! };
    }
    case "CANCEL_REQUESTED":
      if (state.phase !== "recording" && state.phase !== "stopping" && state.phase !== "recovering") return state;
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
  const [state, dispatch] = useReducer(captureRuntimeReducer, { phase: "hydrating" });
  const [elapsedMs, setElapsedMs] = useState(0);
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hydrationStartedRef = useRef<string | null>(null);
  const [recoveryAttemptCount, setRecoveryAttemptCount] = useState(0);
  const [recoveryTimedOut, setRecoveryTimedOut] = useState(false);
  const recoveryRef = useRef({
    startedAt: 0,
    attemptCount: 0,
    inFlight: false,
    timer: null as ReturnType<typeof setTimeout> | null,
  });

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

  // ── Hydration: 页面重进时发现活跃录制 ──
  const hydrate = useCallback(async () => {
    if (!fieldSessionId) return;
    dispatch({ type: "HYDRATE_REQUESTED" });

    try {
      const [singleSessions, dualSessions] = await Promise.all([
        listRecordings({ field_session_id: fieldSessionId, status: "recording" }).catch(() => []),
        listSyncRecordings({ field_session_id: fieldSessionId, status: "recording" }).catch(() => []),
      ]);

      const candidates: UnifiedCaptureSession[] = [
        ...singleSessions.map(adaptRecordingSession),
        ...dualSessions.map(adaptSyncRecordingSession),
      ];

      if (candidates.length === 0) {
        dispatch({ type: "NO_ACTIVE_SESSION" });
        return;
      }

      if (candidates.length > 1) {
        dispatch({
          type: "HYDRATE_FAILED",
          error: "当前采集任务存在多个活跃录制会话，请先检查服务端录制状态。",
        });
        return;
      }

      const session = candidates[0];

      if (!session.captureTakeId) {
        dispatch({
          type: "HYDRATE_FAILED",
          error: "找到了活跃录制，但缺少 CaptureTake，无法恢复实时事件标注。",
        });
        return;
      }

      dispatch({ type: "ACTIVE_SESSION_FOUND", session });
    } catch (error) {
      dispatch({
        type: "HYDRATE_FAILED",
        error: error instanceof Error ? error.message : "查询活跃录制失败",
      });
    }
  }, [fieldSessionId]);

  // Hydration Effect
  useEffect(() => {
    if (!fieldSessionId || hydrationStartedRef.current === fieldSessionId) return;
    hydrationStartedRef.current = fieldSessionId;
    void hydrate();
  }, [fieldSessionId, hydrate]);

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
    if (state.phase !== "recording" && state.phase !== "recovering") return;
    if (state.phase === "recovering" && recoveryRef.current.timer) {
      clearTimeout(recoveryRef.current.timer);
      recoveryRef.current.timer = null;
    }
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

      if (mode === "single") {
        const s = await getRecording(sid);
        if (!s) throw new Error("无法获取录制状态");
        const session = adaptRecordingSession(s);

        if (s.status === "recording") {
          recoveryRef.current.attemptCount++;
          setRecoveryAttemptCount(recoveryRef.current.attemptCount);
          return;
        }

        const takeId = s.capture_take_id;
        let take: CaptureTakeSummary | null = null;
        if (takeId) {
          try { take = await getCaptureTake(takeId); } catch { /* ignore */ }
        }

        const result = take
          ? normalizeRecoveredSingleResult(s, take)
          : {
              captureTakeId: session.captureTakeId,
              fieldSessionId,
              status: s.status as "completed" | "partial" | "failed",
              tracks: [],
              analysisAvailable: false,
              warnings: takeId ? ["服务器未返回 CaptureTake"] : [],
            };
        dispatch({ type: "RECOVERED", session, result });
      } else {
        const s = await getSyncRecording(sid);
        if (!s) throw new Error("无法获取录制状态");
        const session = adaptSyncRecordingSession(s);

        if (s.status === "recording") {
          recoveryRef.current.attemptCount++;
          setRecoveryAttemptCount(recoveryRef.current.attemptCount);
          return;
        }

        const takeId = s.capture_take_id;
        let take: CaptureTakeSummary | null = null;
        if (takeId) {
          try { take = await getCaptureTake(takeId); } catch { /* ignore */ }
        }

        const result = take
          ? normalizeRecoveredDualResult(s, take)
          : {
              captureTakeId: session.captureTakeId,
              fieldSessionId,
              status: s.status as "completed" | "partial" | "failed",
              tracks: [],
              analysisAvailable: false,
              warnings: takeId ? ["服务器未返回 CaptureTake"] : [],
            };
        dispatch({ type: "RECOVERED", session, result });
      }
    } catch (e: any) {
      recoveryRef.current.attemptCount++;
      setRecoveryAttemptCount(recoveryRef.current.attemptCount);
      dispatch({ type: "STOP_RESULT_UNKNOWN", error: e?.message ?? "恢复查询失败" });
    }
  }, [state.phase, fieldSessionId, (state as any).session]);

  // ── Auto-recovery: recovering 状态下自动查询服务器 ──
  useEffect(() => {
    if (state.phase !== "recovering") {
      recoveryRef.current.timer = null;
      setRecoveryTimedOut(false);
      return;
    }

    if (recoveryRef.current.startedAt === 0) {
      recoveryRef.current.startedAt = Date.now();
      recoveryRef.current.attemptCount = 0;
      setRecoveryAttemptCount(0);
      setRecoveryTimedOut(false);
    }

    const scheduleNext = (delayMs: number) => {
      recoveryRef.current.timer = setTimeout(async () => {
        if (recoveryRef.current.inFlight) return;
        recoveryRef.current.inFlight = true;
        try {
          await recover();
        } finally {
          recoveryRef.current.inFlight = false;
        }
      }, delayMs);
    };

    const elapsed = Date.now() - recoveryRef.current.startedAt;
    if (elapsed > 30000) {
      setRecoveryTimedOut(true);
      return;
    }

    const delay = recoveryRef.current.attemptCount === 0 ? 500 : 3000;
    scheduleNext(delay);

    return () => {
      if (recoveryRef.current.timer) {
        clearTimeout(recoveryRef.current.timer);
        recoveryRef.current.timer = null;
      }
    };
  }, [state.phase, recover]);

  const cancel = useCallback(async () => {
    if (state.phase !== "recording" && state.phase !== "stopping" && state.phase !== "recovering") return;
    if (state.phase === "recovering" && recoveryRef.current.timer) {
      clearTimeout(recoveryRef.current.timer);
      recoveryRef.current.timer = null;
    }
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

  const hydrationError = state.phase === "hydration_failed" ? state.error : "";

  const operationError = state.phase === "recovering"
    ? (state as any).operationError ?? ""
    : "";

  return {
    phase: state.phase,
    session: (state.phase === "recording" || state.phase === "stopping" || state.phase === "recovering" || state.phase === "completed" || state.phase === "partial")
      ? state.session : (state.phase === "canceled" ? state.session : null),
    result: (state.phase === "completed" || state.phase === "partial" || state.phase === "failed") ? state.result : null,
    error: state.phase === "failed" ? (state as any).error ?? "" : operationError,
    elapsedMs,
    captureTakeId,
    isRecording: state.phase === "recording" || state.phase === "stopping",
    isStopped: state.phase === "completed" || state.phase === "partial" || state.phase === "failed" || state.phase === "canceled",
    isHydrating: state.phase === "hydrating",
    hydrationError,
    recoveryTimedOut,
    recoveryAttemptCount,
    start,
    stop,
    cancel,
    recover,
    hydrate,
    reset,
  };
}

export { captureRuntimeReducer };
