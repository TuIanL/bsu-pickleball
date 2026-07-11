/** useCapturePreflight —— 双摄短录测试 */
import { useState, useCallback, useEffect } from "react";
import type { SyncTestResult } from "../types/report";
import { runSyncTest } from "../services/analysisClient";

type UseCapturePreflightOptions = {
  mode: "single" | "dual";
  slots?: { cam_1: string; cam_2: string };
};

type PreflightState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "passed"; result: SyncTestResult }
  | { status: "failed"; error: string };

export function useCapturePreflight({ mode, slots }: UseCapturePreflightOptions) {
  const [state, setState] = useState<PreflightState>({ status: "idle" });

  // slots 变化时自动 reset
  useEffect(() => {
    setState({ status: "idle" });
  }, [slots?.cam_1, slots?.cam_2]);

  const runTest = useCallback(async () => {
    if (mode !== "dual" || !slots?.cam_1 || !slots?.cam_2) return;
    setState({ status: "running" });
    try {
      const result = await runSyncTest({ cam_1_id: slots.cam_1, cam_2_id: slots.cam_2 } as any);
      setState({ status: "passed", result });
    } catch (e: any) {
      setState({ status: "failed", error: e?.message ?? "测试失败" });
    }
  }, [mode, slots?.cam_1, slots?.cam_2]);

  return { preflightState: state, runTest };
}
