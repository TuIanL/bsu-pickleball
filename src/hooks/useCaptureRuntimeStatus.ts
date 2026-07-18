/**
 * useCaptureRuntimeStatus —— 按 captureTakeId 轮询 CaptureTake 运行状态快照。
 *
 * 设计依据：openspec/changes/redesign-live-recording-workspace-runtime-status
 * - recording/stopping/recovering 阶段每 2s 轮询
 * - completed/partial/failed/canceled 终态停止轮询，保留最后快照
 * - 用 seq 丢弃过期响应（captureTakeId 切换时旧响应不污染新状态）
 * - 首次请求 loading；失败时保留最后成功快照 + error + lastSuccessAt
 * - 页面不可见时停止轮询，恢复可见时重启
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getCaptureTakeRuntimeStatus, isAnalysisApiError } from "../services/analysisClient";
import type {
  CaptureRuntimeStatusState,
  CaptureTakeRuntimeStatus,
} from "../types/captureRuntimeStatus";

/** 轮询间隔（毫秒），spec 要求 ≤2s */
export const POLL_INTERVAL_MS = 2000;

/** 需要轮询的活跃阶段 */
export const ACTIVE_POLLING_PHASES = new Set([
  "recording",
  "stopping",
  "recovering",
]);

/** 终态：停止轮询 */
export const TERMINAL_PHASES = new Set([
  "completed",
  "partial",
  "failed",
  "canceled",
]);

export interface UseCaptureRuntimeStatusOptions {
  /** 当前 CaptureTake ID；idle/未开始时为 null */
  captureTakeId: string | null;
  /** useCaptureRuntime.phase 或等价录制阶段 */
  phase: string;
}

export interface UseCaptureRuntimeStatusResult {
  state: CaptureRuntimeStatusState;
  /** 是否正在轮询（活跃阶段且页面可见） */
  isPolling: boolean;
}

const INITIAL_STATE: CaptureRuntimeStatusState = {
  snapshot: null,
  isLoading: false,
  error: null,
  lastSuccessAt: null,
};

function describeError(err: unknown): string {
  if (isAnalysisApiError(err)) {
    return err.backendDetail || err.message;
  }
  if (err instanceof Error) return err.message;
  return "运行状态请求失败";
}

export function useCaptureRuntimeStatus({
  captureTakeId,
  phase,
}: UseCaptureRuntimeStatusOptions): UseCaptureRuntimeStatusResult {
  const [state, setState] = useState<CaptureRuntimeStatusState>(INITIAL_STATE);

  // 用 ref 保存最新的 captureTakeId / phase，避免闭包过期
  const takeIdRef = useRef<string | null>(captureTakeId);
  const phaseRef = useRef<string>(phase);
  // seq 用于丢弃同一 take 内的过期响应
  const seqRef = useRef(0);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);
  // 标记是否处于活跃轮询阶段（用于 visibilitychange 恢复）
  const shouldPollRef = useRef(false);

  takeIdRef.current = captureTakeId;
  phaseRef.current = phase;

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const fetchOnce = useCallback(async () => {
    const takeId = takeIdRef.current;
    if (!takeId) return;
    if (inFlightRef.current) return;
    const seq = seqRef.current;
    inFlightRef.current = true;
    try {
      const snapshot: CaptureTakeRuntimeStatus =
        await getCaptureTakeRuntimeStatus(takeId);
      // 丢弃过期响应：takeId 变化或 seq 过期
      if (takeIdRef.current !== takeId || seqRef.current !== seq) return;
      setState({
        snapshot,
        isLoading: false,
        error: null,
        lastSuccessAt: new Date().toISOString(),
      });
    } catch (err) {
      if (takeIdRef.current !== takeId || seqRef.current !== seq) return;
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: describeError(err),
        // 保留 prev.snapshot 和 prev.lastSuccessAt
      }));
    } finally {
      inFlightRef.current = false;
    }
  }, []);

  const startPolling = useCallback(() => {
    const takeId = takeIdRef.current;
    if (!takeId) return;
    // 切换 take 或重新启动时递增 seq，使进行中的旧请求失效
    seqRef.current += 1;
    // 首次请求标记 loading（仅当尚无快照时）
    setState((prev) => ({
      ...prev,
      isLoading: prev.snapshot === null,
      error: null,
    }));
    // 立即发起一次请求
    fetchOnce();
    // 按间隔轮询
    clearPollTimer();
    pollTimerRef.current = setInterval(() => {
      // takeId 变化时由 effect 负责清理，这里兜底
      if (takeIdRef.current !== takeId) {
        clearPollTimer();
        return;
      }
      fetchOnce();
    }, POLL_INTERVAL_MS);
  }, [clearPollTimer, fetchOnce]);

  const stopPolling = useCallback(() => {
    clearPollTimer();
    seqRef.current += 1;
    inFlightRef.current = false;
  }, [clearPollTimer]);

  // 主效应：根据 captureTakeId + phase 决定轮询生命周期
  useEffect(() => {
    const takeId = captureTakeId;
    const shouldPoll = takeId !== null && ACTIVE_POLLING_PHASES.has(phase);
    shouldPollRef.current = shouldPoll;

    if (shouldPoll && takeId) {
      startPolling();
    } else {
      stopPolling();
      if (TERMINAL_PHASES.has(phase)) {
        // 终态：保留最后快照，仅清 loading
        setState((prev) => ({ ...prev, isLoading: false }));
      } else if (!takeId) {
        // idle/未开始：重置整个状态
        setState(INITIAL_STATE);
      }
    }

    return () => {
      // 清理时停止轮询，但不清空 state（避免终态时闪烁）
      clearPollTimer();
      seqRef.current += 1;
      inFlightRef.current = false;
    };
  }, [captureTakeId, phase, startPolling, stopPolling, clearPollTimer]);

  // 可见性优化：页面隐藏时停止轮询，恢复时重启
  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) {
        clearPollTimer();
      } else if (shouldPollRef.current && !pollTimerRef.current) {
        startPolling();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [clearPollTimer, startPolling]);

  // 卸载时清理
  useEffect(() => {
    return () => {
      clearPollTimer();
    };
  }, [clearPollTimer]);

  const isPolling =
    captureTakeId !== null &&
    ACTIVE_POLLING_PHASES.has(phase) &&
    pollTimerRef.current !== null;

  return { state, isPolling };
}
