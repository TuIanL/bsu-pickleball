import type {
  NavigatePath,
  TaskCameraSlot,
  TaskListContext,
  TaskListSource,
} from "./navigationTypes";

const TASK_SOURCES: readonly TaskListSource[] = ["upload", "recorded", "sync_recording"];

function isTaskListSource(value: string | null): value is TaskListSource {
  return value !== null && TASK_SOURCES.includes(value as TaskListSource);
}

function isTaskCameraSlot(value: string | null): value is TaskCameraSlot {
  return value === "cam_1" || value === "cam_2";
}

export function parseTaskListContext(search: string): TaskListContext {
  const params = new URLSearchParams(search);
  const rawSource = params.get("source");
  const rawTaskSource = params.get("taskSource");
  const source: TaskListSource = isTaskListSource(rawSource)
    ? rawSource
    : isTaskListSource(rawTaskSource)
      ? rawTaskSource
      : "upload";

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
