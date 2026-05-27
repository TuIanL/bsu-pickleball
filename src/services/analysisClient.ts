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
  CalibrationPoint,
  ManualCalibrationResponse,
  PoseOverlayArtifact,
  ServeEventsArtifact,
  TrackingOverlayArtifact,
  VideoUploadResponse,
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

export { demoAnalysisReport };
