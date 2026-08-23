import { useSyncExternalStore } from "react";
import {
  getAnalysisRuntimeSnapshot,
  subscribeAnalysisRuntime,
  type AnalysisRuntimeSnapshot,
} from "../services/analysisRuntimeStore";

/**
 * 订阅单个分析 job 的运行时快照。
 * 使用 useSyncExternalStore 订阅模块级 store，StrictMode / 并发渲染下稳定。
 * 未 watch 或无快照时返回 undefined。
 */
export function useAnalysisJobWatch(jobId?: string | null): AnalysisRuntimeSnapshot | undefined {
  return useSyncExternalStore(
    subscribeAnalysisRuntime,
    () => (jobId ? getAnalysisRuntimeSnapshot(jobId) : undefined),
    () => (jobId ? getAnalysisRuntimeSnapshot(jobId) : undefined),
  );
}
