import type {
  AnalysisFlowOrigin,
  NavigatePath,
  TaskCameraSlot,
  TaskListContext,
  TaskListSource,
} from "./navigationTypes";

const TASK_SOURCES: readonly TaskListSource[] = ["upload", "recorded", "sync_recording"];

/** 任务上下文词汇表归一化：Library 入口历史遗留 `recording` 等价于 `recorded` */
function normalizeTaskListSource(value: string | null): TaskListSource | null {
  if (value === "recording") return "recorded";
  return value !== null && TASK_SOURCES.includes(value as TaskListSource)
    ? (value as TaskListSource)
    : null;
}

function isTaskCameraSlot(value: string | null): value is TaskCameraSlot {
  return value === "cam_1" || value === "cam_2";
}

export function parseTaskListContext(search: string): TaskListContext {
  const params = new URLSearchParams(search);
  const rawSource = params.get("source");
  const rawTaskSource = params.get("taskSource");
  const source: TaskListSource =
    normalizeTaskListSource(rawSource) ??
    normalizeTaskListSource(rawTaskSource) ??
    "upload";

  return {
    source,
    sessionId: params.get("session") || params.get("taskSession") || params.get("sessionId") || undefined,
    cameraSlot: isTaskCameraSlot(params.get("cam"))
      ? params.get("cam") as TaskCameraSlot
      : isTaskCameraSlot(params.get("taskCam"))
        ? params.get("taskCam") as TaskCameraSlot
        : undefined,
  };
}

export function taskListPath(context: TaskListContext): NavigatePath {
  const params = new URLSearchParams();
  params.set("source", context.source);
  if (context.sessionId) params.set("session", context.sessionId);
  if (context.cameraSlot) params.set("cam", context.cameraSlot);
  return `/analysis/tasks?${params.toString()}`;
}

export function withTaskListContext(path: string, context: TaskListContext): NavigatePath {
  const url = new URL(path, "http://pickleball.local");
  const isTaskListRoute = url.pathname === "/analysis/tasks" || url.pathname === "/tasks";
  const sourceParam = isTaskListRoute ? "source" : "taskSource";
  const sessionParam = isTaskListRoute ? "session" : "taskSession";
  const cameraParam = isTaskListRoute ? "cam" : "taskCam";
  url.searchParams.set(sourceParam, context.source);
  if (isTaskListRoute) url.searchParams.delete("taskSource");
  if (context.sessionId) url.searchParams.set(sessionParam, context.sessionId);
  else url.searchParams.delete(sessionParam);
  if (context.cameraSlot) url.searchParams.set(cameraParam, context.cameraSlot);
  else url.searchParams.delete(cameraParam);
  return `${url.pathname}${url.search}${url.hash}` as NavigatePath;
}

export function taskContextFromLocation(): TaskListContext {
  if (typeof window === "undefined") return { source: "upload" };
  return parseTaskListContext(window.location.search);
}

interface TaskContextJobLike {
  analysisKind?: string;
  recordingSessionId?: string;
  metadata?: {
    recording_session_id?: string;
  };
}

export function taskContextForJob(job?: TaskContextJobLike | null): TaskListContext {
  const locationContext = taskContextFromLocation();
  const params = typeof window === "undefined" ? null : new URLSearchParams(window.location.search);
  const hasExplicitContext = Boolean(
    params?.has("source") || params?.has("taskSource") || params?.has("session") || params?.has("taskSession"),
  );
  if (hasExplicitContext) return locationContext;

  const sessionId = job?.recordingSessionId ?? job?.metadata?.recording_session_id;
  if (job?.analysisKind === "multiview") {
    return { source: "sync_recording", sessionId };
  }
  if (sessionId) {
    return { source: "recorded", sessionId };
  }
  return { source: "upload" };
}

export function taskListPathForJob(job?: TaskContextJobLike | null): NavigatePath {
  return taskListPath(taskContextForJob(job));
}

// ── transient analysis flow origin（return 即 origin） ─────────────────────────

/**
 * 从 `return` 查询参数推导 analysis flow origin（纯函数，只读视图）。
 * - `/library/:kind/:sourceId` → `library`（解析 itemKind/sourceId）。
 * - `/capture/...` → `capture`。
 * - 缺失 / 非法 → `task-console`（回退工程任务控制台语义）。
 */
export function resolveAnalysisFlowOrigin(
  returnPath: string | null | undefined,
  taskContext?: TaskListContext,
): AnalysisFlowOrigin {
  if (returnPath) {
    const libraryMatch = returnPath.match(/^\/library\/(upload|recording|sync_recording)\/([^?]+)/);
    if (libraryMatch) {
      const [, itemKind, rawSourceId] = libraryMatch;
      let sourceId = rawSourceId;
      try {
        sourceId = decodeURIComponent(rawSourceId);
      } catch {
        // 解码失败保留原文
      }
      return {
        kind: "library",
        itemKind: itemKind as "upload" | "recording" | "sync_recording",
        sourceId,
        returnPath,
      };
    }
    if (returnPath.startsWith("/capture/")) {
      return { kind: "capture", returnPath };
    }
  }
  return { kind: "task-console", taskContext: taskContext ?? { source: "upload" } };
}

// ── URL builder 与 return 安全 ────────────────────────────────────────────────

/** return 安全校验：站内绝对 path、以 `/` 开头、禁止 `//` 前缀 */
export function isValidReturnPath(returnPath: string): boolean {
  return returnPath.startsWith("/") && !returnPath.startsWith("//");
}

/** 追加 `return` 查询参数；非法 return 安全忽略（返回原 path）。 */
export function appendReturnPath(path: string, returnPath?: string | null): NavigatePath {
  if (!returnPath || !isValidReturnPath(returnPath)) return path as NavigatePath;
  const url = new URL(path, "http://pickleball.local");
  url.searchParams.set("return", returnPath);
  return `${url.pathname}${url.search}${url.hash}` as NavigatePath;
}

/** 组装分析进度页 URL：`/analysis/:jobId?return=...`（可选携带任务上下文参数）。 */
export function buildAnalysisProgressPath(
  jobId: string,
  returnPath?: string | null,
  taskContext?: TaskListContext,
): NavigatePath {
  const base = `/analysis/${jobId}`;
  const withContext = taskContext ? withTaskListContext(base, taskContext) : base;
  return appendReturnPath(withContext, returnPath);
}

/** 组装 SyncCalibration URL：`/sync-calibration?take=:takeId&return=<encodeURIComponent(outerUrl)>`（嵌套 return）。 */
export function buildSyncCalibrationPath(takeId: string, outerUrl: string): NavigatePath {
  const params = new URLSearchParams();
  params.set("take", takeId);
  params.set("return", outerUrl);
  return `/sync-calibration?${params.toString()}`;
}

// ── job → Library ref 解析（capture origin 完成后的结果定位） ─────────────────

export interface LibraryRefLike {
  kind: "upload" | "recording" | "sync_recording";
  sourceId: string;
}

interface LibraryRefJobLike {
  analysisKind?: string;
  recordingSessionId?: string;
  videoId?: string;
  metadata?: {
    recording_session_id?: string;
    capture_take_id?: string;
  };
}

/**
 * 按 Library ownership 规则解析 job → Library ref，用于 capture origin 完成后的结果定位。
 * - multiview 或带 `capture_take_id` 的任务 → `sync_recording`（双摄 take 派生）。
 * - 带 recordingSessionId → `recording`。
 * - 仅带 videoId → `upload`。
 * - 无法归属 → null（调用方降级 legacy 工程结果）。
 */
export function resolveLibraryRefFromAnalysisJob(job?: LibraryRefJobLike | null): LibraryRefLike | null {
  if (!job) return null;
  const sessionId = job.recordingSessionId ?? job.metadata?.recording_session_id;
  const isDualCamDerived = job.analysisKind === "multiview" || Boolean(job.metadata?.capture_take_id);
  if (isDualCamDerived) {
    return sessionId ? { kind: "sync_recording", sourceId: sessionId } : null;
  }
  if (sessionId) return { kind: "recording", sourceId: sessionId };
  if (job.videoId) return { kind: "upload", sourceId: job.videoId };
  return null;
}
