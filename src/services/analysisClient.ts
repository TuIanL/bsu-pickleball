import { demoAnalysisReport } from "../data/demoData";
import type {
  AnalysisJobSummary,
  AnalysisPipelineResult,
  AnalysisReport,
  AnalysisDeleteResult,
  AnalysisStage,
  AnalysisStageId,
  AnalysisUploadMetadata,
  AutomaticCalibrationResponse,
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  CalibrationPoint,
  ManualCalibrationResponse,
  PoseOverlayArtifact,
  ServeEventsArtifact,
  TrackingOverlayArtifact,
  StructuredVisualizationData,
  VisualizationManifest,
  VideoUploadResponse,
  RawPlayerRenderTrajectory,
  CodingActionRequest,
  CodingActionResponse,
  LiveCodingState,
  CaptureTakeSummary,
  CaptureSegmentSummary,
  AnalysisBatchCreateResponse,
  AnalysisBatchDetail,
} from "../types/report";

const API_BASE_URL = import.meta.env.VITE_ANALYSIS_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "pre-pickleball-analysis-jobs";
const RECENT_JOB_KEY = "pre-pickleball-recent-analysis-job";
export const RECENT_ANALYSIS_JOB_EVENT = "pre-pickleball-recent-analysis-job-change";

export interface AnalysisApiErrorInfo {
  backendDetail?: string;
  causeMessage?: string;
  isNetworkError: boolean;
  message: string;
  path: string;
  status?: number;
  statusText?: string;
  url: string;
}

export class AnalysisApiError extends Error {
  readonly backendDetail?: string;
  readonly causeMessage?: string;
  readonly isNetworkError: boolean;
  readonly path: string;
  readonly status?: number;
  readonly statusText?: string;
  readonly url: string;

  constructor(info: AnalysisApiErrorInfo) {
    super(info.message);
    this.name = "AnalysisApiError";
    this.backendDetail = info.backendDetail;
    this.causeMessage = info.causeMessage;
    this.isNetworkError = info.isNetworkError;
    this.path = info.path;
    this.status = info.status;
    this.statusText = info.statusText;
    this.url = info.url;
  }
}

export function isAnalysisApiError(error: unknown): error is AnalysisApiError {
  return error instanceof AnalysisApiError;
}

interface StoredJob {
  report: AnalysisReport;
  summary: AnalysisJobSummary;
}

const stageLabels: Record<AnalysisStageId, string> = {
  upload: "视频上传",
  queue: "任务排队",
  calibration: "场地标定",
  "video-read": "读取视频",
  "frame-sampling": "抽帧采样",
  detection: "目标检测",
  pose: "人体姿态",
  tracking: "轨迹跟踪",
  projection: "脚点投影",
  metrics: "运动指标",
  visualization: "可视化输出",
  report: "报告生成",
};

const orderedStages: AnalysisStageId[] = [
  "upload",
  "queue",
  "calibration",
  "video-read",
  "frame-sampling",
  "detection",
  "pose",
  "tracking",
  "projection",
  "metrics",
  "visualization",
  "report",
];

function buildStages(activeStage: AnalysisStageId, failed = false): AnalysisStage[] {
  const activeIndex = orderedStages.indexOf(activeStage);

  return orderedStages.map((stage, index) => {
    let status: AnalysisStage["status"] = "pending";

    if (index < activeIndex) {
      status = "done";
    }

    if (index === activeIndex) {
      status = failed ? "failed" : "active";
    }

    if (!failed && activeStage === "report" && index === activeIndex) {
      status = "done";
    }

    return {
      id: stage,
      label: stageLabels[stage] ?? stage,
      status,
      detail: getStageDetail(stage),
    };
  });
}

function getStageDetail(stage: AnalysisStageId) {
  const details: Record<AnalysisStageId, string> = {
    upload: "保存视频和基础比赛信息",
    queue: "等待视觉分析任务执行",
    calibration: "读取或跳过四角手工标定",
    "video-read": "读取上传视频元数据和帧流",
    "frame-sampling": "按时间轴抽取关键帧",
    detection: "预留 YOLO11 检测球员和场地元素",
    pose: "预留 RTMPose26 识别人体关键点",
    tracking: "关联球员移动轨迹",
    projection: "映射画面坐标到匹克球场",
    metrics: "计算移动距离、速度、厨房区停留和热力图",
    visualization: "生成可供前端展示的结果引用",
    report: "生成报告 JSON 并交给前端展示",
  };

  return details[stage] ?? "等待后端返回该阶段详情";
}

function getStoredJobs(): Record<string, StoredJob> {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}") as Record<string, StoredJob>;
  } catch {
    return {};
  }
}

function getStoredJobSummaries(): AnalysisJobSummary[] {
  return Object.values(getStoredJobs())
    .map((job) => job.summary)
    .filter((summary): summary is AnalysisJobSummary => Boolean(summary?.id))
    .sort((a, b) => Date.parse(b.updatedAt || b.createdAt) - Date.parse(a.updatedAt || a.createdAt));
}

function saveStoredJob(job: StoredJob) {
  const jobs = getStoredJobs();
  jobs[job.summary.id] = job;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
}

function deleteStoredJobs(jobIds: string[]): AnalysisDeleteResult[] {
  const jobs = getStoredJobs();
  const results = jobIds.map((jobId) => {
    if (!jobs[jobId]) {
      return { job_id: jobId, status: "not_found", detail: "Local demo job not found" } satisfies AnalysisDeleteResult;
    }
    delete jobs[jobId];
    return { job_id: jobId, status: "deleted", detail: "Deleted local demo job" } satisfies AnalysisDeleteResult;
  });
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
  return results;
}

export function getRecentAnalysisJob(): AnalysisJobSummary | null {
  try {
    const payload = window.localStorage.getItem(RECENT_JOB_KEY);
    if (!payload) {
      return null;
    }
    const job = JSON.parse(payload) as AnalysisJobSummary;
    return job?.id ? job : null;
  } catch {
    return null;
  }
}

export function rememberAnalysisJob(job?: AnalysisJobSummary | null) {
  if (!job) {
    return;
  }

  try {
    window.localStorage.setItem(RECENT_JOB_KEY, JSON.stringify(job));
    window.dispatchEvent(new CustomEvent(RECENT_ANALYSIS_JOB_EVENT, { detail: job }));
  } catch {
    // localStorage can be unavailable in private browsing; navigation still works for the current route.
  }
}

function buildMockJob(metadata: AnalysisUploadMetadata): StoredJob {
  const now = new Date().toISOString();
  const id = `job-${Date.now().toString(36)}`;
  const reportId = `PV-${id.toUpperCase()}`;

  const summary: AnalysisJobSummary = {
    id,
    status: "completed",
    stage: "report",
    progress: 100,
    createdAt: now,
    updatedAt: now,
    metadata,
    stages: buildStages("report"),
    reportId,
  };

  const report: AnalysisReport = {
    ...demoAnalysisReport,
    source: "job",
    jobId: id,
    reportId,
    generatedAt: now,
    metadata,
    match: {
      ...demoAnalysisReport.match,
      title: metadata.matchTitle,
      date: metadata.matchDate,
      venue: metadata.venue,
      subtitle: `${metadata.matchFormat === "doubles" ? "双打" : "单打"}训练样本 · ${metadata.level}`,
    },
    session: {
      ...demoAnalysisReport.session,
      athlete: metadata.athleteLabel,
      venue: metadata.venue,
      date: metadata.matchDate,
      level: metadata.level,
      reportId,
    },
  };

  return { summary, report };
}

function toApiUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : `${API_BASE_URL}${path}`;
}

function stringifyBackendDetail(detail: unknown): string | undefined {
  if (detail == null) {
    return undefined;
  }
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object" && "msg" in item && typeof item.msg === "string") {
          return item.msg;
        }
        return JSON.stringify(item);
      })
      .join("；");
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return String(detail);
}

async function parseErrorBody(response: Response): Promise<string | undefined> {
  const contentType = response.headers.get("content-type") ?? "";

  try {
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown; error?: unknown };
      return (
        stringifyBackendDetail(payload.detail) ??
        stringifyBackendDetail(payload.message) ??
        stringifyBackendDetail(payload.error) ??
        stringifyBackendDetail(payload)
      );
    }

    const text = await response.text();
    return text.trim() || undefined;
  } catch {
    return undefined;
  }
}

async function throwResponseError(path: string, url: string, response: Response): Promise<never> {
  const backendDetail = await parseErrorBody(response);
  throw new AnalysisApiError({
    backendDetail,
    isNetworkError: false,
    message: backendDetail
      ? `Analysis API ${response.status} ${response.statusText}: ${backendDetail}`
      : `Analysis API returned ${response.status} ${response.statusText}`.trim(),
    path,
    status: response.status,
    statusText: response.statusText,
    url,
  });
}

function toNetworkError(path: string, url: string, error: unknown): AnalysisApiError {
  const causeMessage = error instanceof Error ? error.message : String(error);
  return new AnalysisApiError({
    causeMessage,
    isNetworkError: true,
    message: `Analysis API request failed: ${causeMessage}`,
    path,
    url,
  });
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = toApiUrl(path);
  let response: Response;

  try {
    response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
      ...init,
    });
  } catch (error) {
    throw toNetworkError(path, url, error);
  }

  if (!response.ok) {
    await throwResponseError(path, url, response);
  }

  return response.json() as Promise<T>;
}

async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const url = toApiUrl(path);
  let response: Response;

  try {
    response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
      ...init,
    });
  } catch (error) {
    throw toNetworkError(path, url, error);
  }

  if (!response.ok) {
    await throwResponseError(path, url, response);
  }
}

async function requestForm<T>(path: string, body: FormData): Promise<T> {
  const url = toApiUrl(path);
  let response: Response;

  try {
    response = await fetch(url, {
      body,
      method: "POST",
    });
  } catch (error) {
    throw toNetworkError(path, url, error);
  }

  if (!response.ok) {
    await throwResponseError(path, url, response);
  }

  return response.json() as Promise<T>;
}

interface AnalysisJobRequest {
  calibrationId?: string;
  frameStride?: number;
  metadata: AnalysisUploadMetadata;
  priority?: number;
  requestNewVersion?: boolean;
  useDemoFallback?: boolean;
  videoId?: string;
}

export async function uploadVideo(file: File): Promise<VideoUploadResponse> {
  const body = new FormData();
  body.append("file", file);
  return requestForm<VideoUploadResponse>("/api/videos/upload", body);
}

export async function createManualCalibration(
  videoId: string,
  points: Record<"top_left" | "top_right" | "bottom_right" | "bottom_left", CalibrationPoint>
): Promise<ManualCalibrationResponse> {
  return requestJson<ManualCalibrationResponse>("/calibration/manual", {
    body: JSON.stringify({
      video_id: videoId,
      image_points: {
        top_left: [points.top_left.x, points.top_left.y],
        top_right: [points.top_right.x, points.top_right.y],
        bottom_right: [points.bottom_right.x, points.bottom_right.y],
        bottom_left: [points.bottom_left.x, points.bottom_left.y],
      },
    }),
    method: "POST",
  });
}

export async function requestAutomaticCalibration(videoId: string): Promise<AutomaticCalibrationResponse> {
  return requestJson<AutomaticCalibrationResponse>("/calibration/automatic", {
    body: JSON.stringify({
      video_id: videoId,
    }),
    method: "POST",
  });
}

export async function acceptAutomaticCalibration(
  videoId: string,
  points: Record<"top_left" | "top_right" | "bottom_right" | "bottom_left", CalibrationPoint>,
  source: "automatic" | "corrected" = "automatic"
): Promise<AutomaticCalibrationResponse> {
  return requestJson<AutomaticCalibrationResponse>("/calibration/automatic/accept", {
    body: JSON.stringify({
      video_id: videoId,
      source,
      image_points: {
        top_left: [points.top_left.x, points.top_left.y],
        top_right: [points.top_right.x, points.top_right.y],
        bottom_right: [points.bottom_right.x, points.bottom_right.y],
        bottom_left: [points.bottom_left.x, points.bottom_left.y],
      },
    }),
    method: "POST",
  });
}

export async function createAnalysisJob(request: AnalysisJobRequest): Promise<AnalysisJobSummary> {
  try {
    const job = await requestJson<AnalysisJobSummary>("/api/analysis/jobs", {
      body: JSON.stringify({
        metadata: request.metadata,
        videoId: request.videoId,
        calibrationId: request.calibrationId,
        frameStride: request.frameStride ?? 2,
        sourceFps: request.metadata.sourceFps,
        priority: request.priority ?? 0,
        requestNewVersion: request.requestNewVersion ?? false,
      }),
      method: "POST",
    });
    rememberAnalysisJob(job);
    return job;
  } catch (error) {
    if (request.videoId || request.useDemoFallback === false) {
      throw error;
    }

    const metadata = request.metadata;
    const job = buildMockJob(metadata);
    saveStoredJob(job);
    rememberAnalysisJob(job.summary);
    return job.summary;
  }
}

export async function listAnalysisJobs(): Promise<AnalysisJobSummary[]> {
  try {
    const jobs = await requestJson<AnalysisJobSummary[]>("/api/analysis/jobs");
    if (jobs.length) {
      rememberAnalysisJob(jobs[0]);
      return jobs;
    }
    const storedJobs = getStoredJobSummaries();
    if (storedJobs.length) {
      rememberAnalysisJob(storedJobs[0]);
    }
    return storedJobs;
  } catch (error) {
    const storedJobs = getStoredJobSummaries();
    if (storedJobs.length) {
      rememberAnalysisJob(storedJobs[0]);
      return storedJobs;
    }
    throw error;
  }
}

export async function deleteAnalysisJob(jobId: string): Promise<AnalysisDeleteResult> {
  try {
    const result = await requestJson<AnalysisDeleteResult>(`/api/analysis/jobs/${jobId}`, {
      method: "DELETE",
    });
    if (result.status === "deleted") {
      deleteStoredJobs([jobId]);
    }
    return result;
  } catch (error) {
    const stored = getStoredJobs()[jobId];
    if (stored?.summary) {
      return deleteStoredJobs([jobId])[0];
    }
    throw error;
  }
}

export async function deleteAnalysisJobs(jobIds: string[]): Promise<AnalysisDeleteResult[]> {
  try {
    const results = await requestJson<AnalysisDeleteResult[]>("/api/analysis/jobs/delete", {
      body: JSON.stringify({ job_ids: jobIds }),
      method: "POST",
    });
    const deletedJobIds = results.filter((result) => result.status === "deleted").map((result) => result.job_id);
    if (deletedJobIds.length) {
      deleteStoredJobs(deletedJobIds);
    }
    return results;
  } catch (error) {
    const storedJobs = getStoredJobs();
    const hasAnyStored = jobIds.some((jobId) => storedJobs[jobId]);
    if (hasAnyStored) {
      return deleteStoredJobs(jobIds);
    }
    throw error;
  }
}

export async function cancelAnalysisJob(jobId: string): Promise<AnalysisJobSummary> {
  const job = await requestJson<AnalysisJobSummary>(`/api/analysis/jobs/${jobId}/cancel`, {
    method: "POST",
  });
  rememberAnalysisJob(job);
  return job;
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJobSummary | null> {
  try {
    const job = await requestJson<AnalysisJobSummary>(`/api/analysis/jobs/${jobId}`);
    rememberAnalysisJob(job);
    return job;
  } catch (error) {
    const stored = getStoredJobs()[jobId];
    if (stored?.summary) {
      rememberAnalysisJob(stored.summary);
      return stored.summary;
    }
    if (isAnalysisApiError(error) && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function getAnalysisReport(jobId: string): Promise<AnalysisReport | null> {
  try {
    return await requestJson<AnalysisReport>(`/api/analysis/jobs/${jobId}/report`);
  } catch (error) {
    const stored = getStoredJobs()[jobId];
    if (stored?.report) {
      return stored.report;
    }
    if (isAnalysisApiError(error) && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function getAnalysisResult(jobId: string): Promise<AnalysisPipelineResult | AnalysisJobSummary | null> {
  try {
    return await requestJson<AnalysisPipelineResult | AnalysisJobSummary>(`/api/analysis/jobs/${jobId}/result`);
  } catch (error) {
    const stored = getStoredJobs()[jobId];
    if (stored?.summary) {
      return stored.summary;
    }
    if (isAnalysisApiError(error) && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function getVideoStreamUrl(videoId?: string): string | undefined {
  return videoId ? toApiUrl(`/api/videos/${videoId}/stream`) : undefined;
}

export function resolveAnalysisAssetUrl(path?: string): string | undefined {
  return path ? toApiUrl(path) : undefined;
}

export async function getTrackingOverlay(result: AnalysisPipelineResult): Promise<TrackingOverlayArtifact | null> {
  const path = result.artifacts.tracking_overlay_url;
  return path ? requestJson<TrackingOverlayArtifact>(path) : null;
}

export async function getPoseOverlay(result: AnalysisPipelineResult): Promise<PoseOverlayArtifact | null> {
  const path = result.artifacts.pose_overlay_url;
  return path ? requestJson<PoseOverlayArtifact>(path) : null;
}

export async function getServeEvents(result: AnalysisPipelineResult): Promise<ServeEventsArtifact | null> {
  const path = result.artifacts.serve_events_url;
  return path ? requestJson<ServeEventsArtifact>(path) : null;
}

export async function getBallTrajectory(result: AnalysisPipelineResult): Promise<BallTrajectoryArtifact | null> {
  const path = result.artifacts.cleaned_ball_trajectory_url ?? result.artifacts.ball_trajectory_url;
  return path ? requestJson<BallTrajectoryArtifact>(path) : null;
}

export async function getBounceEvents(result: AnalysisPipelineResult): Promise<BounceEventsArtifact | null> {
  const path = result.artifacts.bounce_events_url;
  return path ? requestJson<BounceEventsArtifact>(path) : null;
}

export function getAnalysisOverlayVideoUrl(result: AnalysisPipelineResult): string | undefined {
  return resolveAnalysisAssetUrl(result.artifacts.analysis_overlay_video_url);
}

export async function getPositionHeatmaps(result: AnalysisPipelineResult): Promise<VisualizationManifest | null> {
  const path = result.artifacts.heatmaps_url;
  return path ? requestJson<VisualizationManifest>(path) : null;
}

export async function getPositionScatterPlots(result: AnalysisPipelineResult): Promise<VisualizationManifest | null> {
  const path = result.artifacts.scatter_plots_url;
  return path ? requestJson<VisualizationManifest>(path) : null;
}

export async function getStructuredVizData(jobId: string): Promise<StructuredVisualizationData | null> {
  try {
    return await requestJson<StructuredVisualizationData>(`/api/analysis/jobs/${jobId}/visualization-data`);
  } catch {
    return null;
  }
}

export async function getPlayerRenderTrajectory(jobId: string): Promise<RawPlayerRenderTrajectory | null> {
  try {
    return await requestJson<RawPlayerRenderTrajectory>(`/api/analysis/jobs/${jobId}/artifacts/player-render-trajectories`);
  } catch (error: unknown) {
    if (error && typeof error === "object" && "status" in error && (error as { status: number }).status === 404) {
      return null;
    }
    throw error;
  }
}

// Camera API functions
import type {
  CameraCreateRequest,
  CameraInfo,
  FieldSession,
  FieldSessionCreate,
  FieldSessionDeleteResult,
  ProbeResult,
  RecordingSession,
  RecordingStartRequest,
  SessionTimelineEvent,
  SyncRecordingSession,
  SyncStartRequest,
  SyncStopResponse,
  SyncTestRequest,
  SyncTestResult,
  TimelineEventCreate,
  TimelineEventUpdate,
  TimelineEventListParams,
} from "../types/report";

export async function listCameras(): Promise<CameraInfo[]> {
  return requestJson<CameraInfo[]>("/api/cameras");
}

export async function createCamera(request: CameraCreateRequest): Promise<CameraInfo> {
  return requestJson<CameraInfo>("/api/cameras", {
    body: JSON.stringify(request),
    method: "POST",
  });
}

export async function deleteCamera(cameraId: string): Promise<{ deleted: boolean }> {
  return requestJson<{ deleted: boolean }>(`/api/cameras/${cameraId}`, {
    method: "DELETE",
  });
}

export async function probeCamera(cameraId: string): Promise<ProbeResult> {
  return requestJson<ProbeResult>(`/api/cameras/${cameraId}/probe`, {
    method: "POST",
  });
}

export async function startRecording(request: RecordingStartRequest): Promise<RecordingSession> {
  return requestJson<RecordingSession>("/api/recordings/start", {
    body: JSON.stringify(request),
    method: "POST",
  });
}

export async function stopRecording(sessionId: string): Promise<RecordingSession> {
  return requestJson<RecordingSession>(`/api/recordings/${sessionId}/stop`, {
    method: "POST",
  });
}

export async function cancelRecording(sessionId: string): Promise<RecordingSession> {
  return requestJson<RecordingSession>(`/api/recordings/${sessionId}/cancel`, {
    method: "POST",
  });
}

export async function listRecordings(params?: {
  camera_id?: string;
  status?: string;
  field_session_id?: string;
}): Promise<RecordingSession[]> {
  const searchParams = new URLSearchParams();
  if (params?.camera_id) searchParams.set("camera_id", params.camera_id);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.field_session_id) searchParams.set("field_session_id", params.field_session_id);
  const query = searchParams.toString();
  return requestJson<RecordingSession[]>(`/api/recordings${query ? `?${query}` : ""}`);
}

export async function getRecording(sessionId: string): Promise<RecordingSession> {
  return requestJson<RecordingSession>(`/api/recordings/${sessionId}`);
}

export async function deleteRecording(sessionId: string): Promise<{ session_id: string; status: string; detail: string }> {
  return requestJson<{ session_id: string; status: string; detail: string }>(`/api/recordings/${sessionId}`, {
    method: "DELETE",
  });
}

// ── Dual-Camera Sync Recording API ──

export async function startSyncRecording(request: SyncStartRequest): Promise<SyncRecordingSession> {
  return requestJson<SyncRecordingSession>("/api/sync-recordings/start", {
    body: JSON.stringify(request),
    method: "POST",
  });
}

export async function stopSyncRecording(sessionId: string): Promise<SyncStopResponse> {
  return requestJson<SyncStopResponse>(`/api/sync-recordings/${sessionId}/stop`, {
    method: "POST",
  });
}

export async function cancelSyncRecording(sessionId: string): Promise<SyncRecordingSession> {
  return requestJson<SyncRecordingSession>(`/api/sync-recordings/${sessionId}/cancel`, {
    method: "POST",
  });
}

export async function listSyncRecordings(params?: {
  status?: string;
  field_session_id?: string;
}): Promise<SyncRecordingSession[]> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.field_session_id) searchParams.set("field_session_id", params.field_session_id);
  const query = searchParams.toString();
  return requestJson<SyncRecordingSession[]>(`/api/sync-recordings${query ? `?${query}` : ""}`);
}

export async function getSyncRecording(sessionId: string): Promise<SyncRecordingSession> {
  return requestJson<SyncRecordingSession>(`/api/sync-recordings/${sessionId}`);
}

export async function getActiveSyncRecording(): Promise<SyncRecordingSession | null> {
  return requestJson<SyncRecordingSession | null>("/api/sync-recordings/active");
}

export async function runSyncTest(request: SyncTestRequest): Promise<SyncTestResult> {
  return requestJson<SyncTestResult>("/api/sync-recordings/test", {
    body: JSON.stringify(request),
    method: "POST",
  });
}

export async function deleteSyncRecording(sessionId: string): Promise<{ session_id: string; status: string; detail: string }> {
  return requestJson<{ session_id: string; status: string; detail: string }>(`/api/sync-recordings/${sessionId}`, {
    method: "DELETE",
  });
}

export function getCameraPreviewUrl(cameraId?: string): string | undefined {
  return cameraId ? toApiUrl(`/api/cameras/${cameraId}/preview`) : undefined;
}

// Field Session API functions
export async function createFieldSession(request: FieldSessionCreate): Promise<FieldSession> {
  return requestJson<FieldSession>("/api/field-sessions", {
    body: JSON.stringify(request),
    method: "POST",
  });
}

export async function listFieldSessions(params?: {
  status?: string;
  capture_mode?: string;
  match_format?: string;
  limit?: number;
  offset?: number;
}): Promise<FieldSession[]> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.capture_mode) sp.set("capture_mode", params.capture_mode);
  if (params?.match_format) sp.set("match_format", params.match_format);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const q = sp.toString();
  return requestJson<FieldSession[]>(`/api/field-sessions${q ? `?${q}` : ""}`);
}

export async function getFieldSession(id: string): Promise<FieldSession> {
  return requestJson<FieldSession>(`/api/field-sessions/${id}`);
}

export async function updateFieldSession(id: string, request: Partial<FieldSessionCreate>): Promise<FieldSession> {
  return requestJson<FieldSession>(`/api/field-sessions/${id}`, {
    body: JSON.stringify(request),
    method: "PATCH",
  });
}

export async function startFieldSession(id: string): Promise<FieldSession> {
  return requestJson<FieldSession>(`/api/field-sessions/${id}/start`, { method: "POST" });
}

export async function completeFieldSession(id: string): Promise<FieldSession> {
  return requestJson<FieldSession>(`/api/field-sessions/${id}/complete`, { method: "POST" });
}

export async function archiveFieldSession(id: string): Promise<FieldSession> {
  return requestJson<FieldSession>(`/api/field-sessions/${id}/archive`, { method: "POST" });
}

export async function deleteFieldSession(id: string): Promise<FieldSessionDeleteResult> {
  return requestJson<FieldSessionDeleteResult>(`/api/field-sessions/${id}`, { method: "DELETE" });
}

// —— Timeline Event API ——

export async function createTimelineEvent(
  fieldSessionId: string,
  payload: TimelineEventCreate,
): Promise<SessionTimelineEvent> {
  return requestJson<SessionTimelineEvent>(
    `/api/field-sessions/${fieldSessionId}/timeline-events`,
    { body: JSON.stringify(payload), method: "POST" },
  );
}

export async function listTimelineEvents(
  fieldSessionId: string,
  params?: TimelineEventListParams,
): Promise<SessionTimelineEvent[]> {
  const sp = new URLSearchParams();
  if (params?.event_type) sp.set("event_type", params.event_type);
  if (params?.source) sp.set("source", params.source);
  if (params?.recording_session_id) sp.set("recording_session_id", params.recording_session_id);
  if (params?.capture_take_id) sp.set("capture_take_id", params.capture_take_id);
  if (params?.from_ms !== undefined) sp.set("from_ms", String(params.from_ms));
  if (params?.to_ms !== undefined) sp.set("to_ms", String(params.to_ms));
  const q = sp.toString();
  return requestJson<SessionTimelineEvent[]>(
    `/api/field-sessions/${fieldSessionId}/timeline-events${q ? `?${q}` : ""}`,
  );
}

export async function updateTimelineEvent(
  eventId: string,
  payload: TimelineEventUpdate,
): Promise<SessionTimelineEvent> {
  return requestJson<SessionTimelineEvent>(`/api/timeline-events/${eventId}`, {
    body: JSON.stringify(payload),
    method: "PATCH",
  });
}

export async function deleteTimelineEvent(eventId: string): Promise<void> {
  await requestVoid(`/api/timeline-events/${eventId}`, { method: "DELETE" });
}

// ── CaptureTake & Coding Actions API ──

export async function getCaptureTake(takeId: string): Promise<CaptureTakeSummary> {
  return requestJson<CaptureTakeSummary>(`/api/capture-takes/${takeId}`);
}

export async function getLiveCodingState(takeId: string): Promise<LiveCodingState> {
  return requestJson<LiveCodingState>(`/api/capture-takes/${takeId}/live-state`);
}

export async function executeCodingAction(
  takeId: string,
  request: CodingActionRequest,
): Promise<CodingActionResponse> {
  return requestJson<CodingActionResponse>(`/api/capture-takes/${takeId}/coding-actions`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listSegments(
  takeId: string,
  segmentType?: string,
): Promise<CaptureSegmentSummary[]> {
  const sp = new URLSearchParams();
  if (segmentType) sp.set("segment_type", segmentType);
  const q = sp.toString();
  return requestJson<CaptureSegmentSummary[]>(`/api/capture-takes/${takeId}/segments${q ? `?${q}` : ""}`);
}

// ── Segment Editing API ──

export async function patchSegment(
  segmentId: string,
  patch: Record<string, unknown>,
): Promise<CaptureSegmentSummary> {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(patch)) {
    if (v !== undefined && v !== null) sp.set(k, String(v));
  }
  return requestJson<CaptureSegmentSummary>(`/api/capture-segments/${segmentId}?${sp.toString()}`, {
    method: "PATCH",
  });
}

export async function resetSegmentBoundary(segmentId: string): Promise<CaptureSegmentSummary> {
  return requestJson<CaptureSegmentSummary>(`/api/capture-segments/${segmentId}/reset-boundary-correction`, {
    method: "POST",
  });
}

export async function splitSegment(segmentId: string, splitMs: number): Promise<{ segments: CaptureSegmentSummary[] }> {
  return requestJson<{ segments: CaptureSegmentSummary[] }>(`/api/capture-segments/${segmentId}/split?split_ms=${splitMs}`, {
    method: "POST",
  });
}

export async function mergeSegments(segmentIds: [string, string]): Promise<CaptureSegmentSummary> {
  return requestJson<CaptureSegmentSummary>(`/api/capture-segments/merge`, {
    method: "POST",
    body: JSON.stringify(segmentIds),
  });
}

export async function archiveSegment(segmentId: string): Promise<CaptureSegmentSummary> {
  return requestJson<CaptureSegmentSummary>(`/api/capture-segments/${segmentId}/archive`, {
    method: "POST",
  });
}

export async function restoreSegment(segmentId: string): Promise<CaptureSegmentSummary> {
  return requestJson<CaptureSegmentSummary>(`/api/capture-segments/${segmentId}/restore`, {
    method: "POST",
  });
}

export async function deleteSegment(segmentId: string): Promise<void> {
  await requestVoid(`/api/capture-segments/${segmentId}`, { method: "DELETE" });
}

// ── AnalysisBatch API ──

export async function createAnalysisBatch(
  takeId: string,
  segmentIds: string[],
  analysisProfile?: string,
): Promise<AnalysisBatchCreateResponse> {
  return requestJson<AnalysisBatchCreateResponse>(`/api/capture-takes/${takeId}/analysis-batches`, {
    method: "POST",
    body: JSON.stringify({
      segment_ids: segmentIds,
      analysis_profile: analysisProfile ?? "match_default",
    }),
  });
}

export async function getAnalysisBatch(takeId: string, batchId: string): Promise<AnalysisBatchDetail> {
  return requestJson<AnalysisBatchDetail>(`/api/capture-takes/${takeId}/analysis-batches/${batchId}`);
}

export { demoAnalysisReport };
