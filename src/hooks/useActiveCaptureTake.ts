import { useCallback, useEffect, useRef, useState } from "react";
import {
  getActiveCaptureTake,
  forceFinalizeActiveCaptureTake,
  listRecordings,
  listSyncRecordings,
} from "../services/analysisClient";

export interface ActiveCaptureTakeSummary {
  takeId: string;
  fieldSessionId: string;
  captureTakeId: string;
  sourceSessionId: string;
  sourceSessionType: string;
  startedAt: string;
  serverNow: string;
  status: "starting" | "recording" | "stopping" | "recovering" | "finalizing";
  title: string | null;
  courtName: string | null;
  captureMode: "single" | "dual";
  videoSpec: { width?: number; height?: number; fps?: number } | null;
}

const POLL_INTERVAL = 5000;
const CLOCK_INTERVAL = 1000;

export function useActiveCaptureTake() {
  const [activeTake, setActiveTake] = useState<ActiveCaptureTakeSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isOrphan, setIsOrphan] = useState(false);
  const [forceCancelling, setForceCancelling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const seqRef = useRef(0);
  const pollFnRef = useRef<(() => void) | null>(null);

  const checkOrphan = useCallback(async (take: ActiveCaptureTakeSummary) => {
    try {
      const [singleSessions, dualSessions] = await Promise.all([
        listRecordings({ field_session_id: take.fieldSessionId, status: "recording" }).catch(() => []),
        listSyncRecordings({ field_session_id: take.fieldSessionId, status: "recording" }).catch(() => []),
      ]);
      const hasActiveSession = singleSessions.length > 0 || dualSessions.length > 0;
      setIsOrphan(!hasActiveSession);
    } catch {
      setIsOrphan(false);
    }
  }, []);

  const fetchActive = useCallback(() => {
    const seq = ++seqRef.current;
    getActiveCaptureTake()
      .then((data) => {
        if (seq !== seqRef.current) return;
        setActiveTake(data);
        setIsLoading(false);
        if (data) {
          void checkOrphan(data);
        } else {
          setIsOrphan(false);
        }
      })
      .catch(() => {
        if (seq !== seqRef.current) return;
        setActiveTake(null);
        setIsOrphan(false);
        setIsLoading(false);
      });
  }, [checkOrphan]);

  const forceCancel = useCallback(async () => {
    if (!activeTake) return;
    setForceCancelling(true);
    try {
      await forceFinalizeActiveCaptureTake();
      setActiveTake(null);
      setIsOrphan(false);
    } catch {
      // keep forceCancelling false on failure
    } finally {
      setForceCancelling(false);
    }
  }, [activeTake]);

  const startPolling = useCallback(() => {
    stopPolling();
    fetchActive();
    pollRef.current = setInterval(fetchActive, POLL_INTERVAL);
    clockRef.current = setInterval(() => {
      setActiveTake((prev) => {
        if (!prev) return prev;
        return { ...prev };
      });
    }, CLOCK_INTERVAL);
  }, [fetchActive]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (clockRef.current) {
      clearInterval(clockRef.current);
      clockRef.current = null;
    }
    seqRef.current += 1;
  }, []);

  pollFnRef.current = startPolling;

  useEffect(() => {
    startPolling();
    const handleVisibility = () => {
      if (document.hidden) {
        stopPolling();
      } else {
        pollFnRef.current?.();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [startPolling, stopPolling]);

  return { activeTake, isLoading, isOrphan, forceCancel, forceCancelling };
}

export { computeCaptureElapsedMs as computeElapsedMs } from "../components/capture/captureClock";
