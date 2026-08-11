import { useEffect, useState } from "react";
import { getShowcaseRuntimeStatus } from "../services/analysisClient";
import type { ShowcaseRuntimeStatus } from "../types/report";

export function useShowcaseRuntime(runtimeId: string | undefined, active: boolean) {
  const [status, setStatus] = useState<ShowcaseRuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedRuntimeId, setLoadedRuntimeId] = useState<string | null>(null);

  useEffect(() => {
    if (!runtimeId || !active) {
      return;
    }
    let disposed = false;
    const poll = async () => {
      try {
        const next = await getShowcaseRuntimeStatus(runtimeId);
        if (!disposed) {
          setStatus(next);
          setLoadedRuntimeId(runtimeId);
          setError(null);
        }
      } catch (err) {
        if (!disposed) {
          setLoadedRuntimeId(runtimeId);
          setError(err instanceof Error ? err.message : "展示状态不可用");
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [runtimeId, active]);

  const hasCurrentRuntime = Boolean(runtimeId && active && loadedRuntimeId === runtimeId);
  return {
    status: hasCurrentRuntime ? status : null,
    error: hasCurrentRuntime ? error : null,
  };
}
