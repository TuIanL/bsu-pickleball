/**
 * analysisRuntimeStore —— 分析运行时快照（纯 TS，不含 React）
 *
 * 职责：承载「某次 Job 的瞬时执行状态」，与素材身份（LibraryItemViewModel）解耦。
 * - `AnalysisRuntimeSnapshot`：jobId / status / progress / stage / stages / viewRuns。
 * - 单 scheduler 定向轮询：对 watch 的 active job ids 逐个调 `getAnalysisJob(jobId)`，
 *   不重跑 `buildLibraryItems()`，也不全量轮询 `listAnalysisJobs`。
 * - `document.hidden` 暂停；无 active job 即停；concurrency 受限。
 * - React 侧通过 `src/hooks/useAnalysisJobWatch.ts`（useSyncExternalStore）订阅。
 */

import type { AnalysisJobSummary } from "../types/report";
import { getAnalysisJob } from "./analysisClient";

export interface AnalysisRuntimeSnapshot {
  jobId: string;
  status: AnalysisJobSummary["status"];
  progress: number;
  /** 当前阶段文案（active/failed stage 优先，否则 job.stage） */
  stage?: string;
  stages: AnalysisJobSummary["stages"];
  viewRuns?: AnalysisJobSummary["viewRuns"];
}

type Listener = () => void;

const ACTIVE_STATUSES: AnalysisJobSummary["status"][] = ["uploaded", "queued", "processing"];
const DEFAULT_INTERVAL_MS = 5000;
const CONCURRENCY_LIMIT = 4;

const snapshots = new Map<string, AnalysisRuntimeSnapshot>();
const listeners = new Set<Listener>();

let watchedJobIds = new Set<string>();
let intervalMs = DEFAULT_INTERVAL_MS;
let schedulerTimer: number | undefined;
let documentVisible = typeof document === "undefined" ? true : !document.hidden;

function emit() {
  for (const listener of listeners) listener();
}

function isActiveStatus(status: AnalysisJobSummary["status"]): boolean {
  return ACTIVE_STATUSES.includes(status);
}

function toSnapshot(job: AnalysisJobSummary): AnalysisRuntimeSnapshot {
  const currentStage =
    job.stages.find((s) => s.status === "active") ?? job.stages.find((s) => s.status === "failed");
  return {
    jobId: job.id,
    status: job.status,
    progress: job.progress,
    stage: currentStage?.label ?? job.stage,
    stages: job.stages,
    viewRuns: job.viewRuns,
  };
}

async function tick() {
  if (!documentVisible || watchedJobIds.size === 0) {
    scheduleNext();
    return;
  }
  const ids = [...watchedJobIds];
  const chunks: string[][] = [];
  for (let i = 0; i < ids.length; i += CONCURRENCY_LIMIT) {
    chunks.push(ids.slice(i, i + CONCURRENCY_LIMIT));
  }
  for (const chunk of chunks) {
    await Promise.all(
      chunk.map((id) =>
        getAnalysisJob(id)
          .then((job) => {
            if (job) snapshots.set(job.id, toSnapshot(job));
          })
          .catch(() => {
            // 单 job 失败不拖垮整个调度
          }),
      ),
    );
  }
  emit();
  scheduleNext();
}

function scheduleNext() {
  if (schedulerTimer !== undefined || watchedJobIds.size === 0) return;
  schedulerTimer = window.setTimeout(() => {
    schedulerTimer = undefined;
    void tick();
  }, intervalMs);
}

// ── 对外 API ────────────────────────────────────────────────────────────────

/** 订阅运行时快照变化（React 侧经 useSyncExternalStore 消费） */
export function subscribeAnalysisRuntime(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 读取某 job 的运行时快照；未 watch / 无快照时 undefined */
export function getAnalysisRuntimeSnapshot(jobId: string): AnalysisRuntimeSnapshot | undefined {
  return snapshots.get(jobId);
}

/** 登记 active job 进入定向轮询（去重；不立即请求，由首个 tick 拉取） */
export function watchAnalysisJob(jobId: string) {
  if (watchedJobIds.has(jobId)) return;
  watchedJobIds.add(jobId);
  scheduleNext();
}

/** 停止 watch；`clearSnapshot` 为 true 时同时清理快照（terminal reconciliation 后） */
export function unwatchAnalysisJob(jobId: string, clearSnapshot = false) {
  watchedJobIds.delete(jobId);
  if (clearSnapshot) snapshots.delete(jobId);
}

/** 注入冷 build 的粗粒度快照（可选），避免等待首个 tick 才有进度 */
export function seedAnalysisRuntimeSnapshot(snapshot: AnalysisRuntimeSnapshot) {
  snapshots.set(snapshot.jobId, snapshot);
}

/** 当前被 watch 的 active job ids */
export function listWatchedAnalysisJobs(): string[] {
  return [...watchedJobIds];
}

/** 是否有 active job 在被 watch */
export function hasActiveAnalysisJobs(): boolean {
  return watchedJobIds.size > 0;
}

/** 设置轮询间隔（进度页 1.6s / Library 5s 差异化节流） */
export function setAnalysisWatchInterval(ms: number) {
  intervalMs = ms;
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    documentVisible = !document.hidden;
    if (documentVisible) {
      // 恢复可见立即 reconcile 一次
      void tick();
    }
  });
}
