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
  ReconstructedBallTrajectoryArtifact,
  ServeEventsArtifact,
  TrackingOverlayArtifact,
  FusedPlayerOverlayArtifact,
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
  FusedManifest,
  ShowcaseRuntimeStatus,
  PlayerDisplayDiagnosticsResponse,
} from "../types/report";
import type { CaptureTakeRuntimeStatus } from "../types/captureRuntimeStatus";
import type {
  MultiviewObservabilitySummary,
  RecoveryEpisodePage,
  RecoveryOutcome,
} from "../types/multiviewObservability";
import type {
  SyncAnchorConfirmResponse,
  SyncAnchorDraft,
  SyncAnchorDraftResponse,
  SyncAnchorStatus,
} from "../types/syncAnchors";

const API_BASE_URL = import.meta.env.VITE_ANALYSIS_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "pre-pickleball-analysis-jobs";
const RECENT_JOB_KEY = "pre-pickleball-recent-analysis-job";
export const RECENT_ANALYSIS_JOB_EVENT = "pre-pickleball-recent-analysis-job-change";

export interface VidatPackage {
  id: string;
  capture_take_id: string;
  version: number;
  package_dir: string;
  manifest: { video?: { file?: string; fps?: number; duration?: number }; [key: string]: unknown };
  imported_at: string | null;
}

export interface VidatImportPreview {
  preview_id: string;
  confirmation_token: string;
  expires_at: string;
  operations: unknown[];
  coding_actions: unknown[];
  changes: Array<{ kind: string; before?: unknown; after?: unknown }>;
  blocking_errors: string[];
  conflicts: string[];
  score_summary: { affected_scores: unknown[]; final: Record<string, unknown> };
}

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

interface DemoFallbackOptions {
  useDemoFallback?: boolean;
}

type LegacyAnalysisJobSummary = AnalysisJobSummary & {
  recording_session_id?: string;
  camera_slot?: "cam_1" | "cam_2";
  metadata: AnalysisUploadMetadata & {
    recordingSessionId?: string;
    cameraSlot?: "cam_1" | "cam_2";
  };
};

function normalizeAnalysisJobSummary(job: AnalysisJobSummary): AnalysisJobSummary {
  const raw = job as LegacyAnalysisJobSummary;
  const recordingSessionId = job.recordingSessionId
    ?? raw.recording_session_id
    ?? job.metadata.recording_session_id
    ?? raw.metadata.recordingSessionId;
  const cameraSlot = job.cameraSlot
    ?? raw.camera_slot
    ?? job.metadata.camera_slot
    ?? raw.metadata.cameraSlot;

  return {
    ...job,
    recordingSessionId,
    cameraSlot,
    metadata: {
      ...job.metadata,
      recording_session_id: job.metadata.recording_session_id ?? recordingSessionId,
      camera_slot: job.metadata.camera_slot ?? cameraSlot,
    },
  };
}

function isAnalysisJobSummary(value: AnalysisPipelineResult | AnalysisJobSummary): value is AnalysisJobSummary {
  return Boolean(
    value
    && typeof value === "object"
    && "id" in value
    && "metadata" in value
    && "stages" in value,
  );
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
    .map((job) => normalizeAnalysisJobSummary(job.summary))
    .filter((summary): summary is AnalysisJobSummary => Boolean(summary?.id && summary.analysisMode === "demo"))
    .sort((a, b) => Date.parse(b.updatedAt || b.createdAt) - Date.parse(a.updatedAt || a.createdAt));
}

function getStoredDemoJob(jobId: string): StoredJob | undefined {
  const stored = getStoredJobs()[jobId];
  return stored?.summary.analysisMode === "demo" ? stored : undefined;
}

function getStoredDemoJobs(): Record<string, StoredJob> {
  return Object.fromEntries(
    Object.entries(getStoredJobs()).filter(([, job]) => job.summary.analysisMode === "demo"),
  );
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
    return job?.id ? normalizeAnalysisJobSummary(job) : null;
  } catch {
    return null;
  }
}

export function rememberAnalysisJob(job?: AnalysisJobSummary | null) {
  if (!job) {
    return;
  }

  try {
    const normalizedJob = normalizeAnalysisJobSummary(job);
    window.localStorage.setItem(RECENT_JOB_KEY, JSON.stringify(normalizedJob));
    window.dispatchEvent(new CustomEvent(RECENT_ANALYSIS_JOB_EVENT, { detail: normalizedJob }));
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
    analysisMode: "demo",
    recordingSessionId: metadata.recording_session_id,
    cameraSlot: metadata.camera_slot,
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
      if (
        payload
        && typeof payload === "object"
        && "code" in payload
        && ("issues" in payload || "diagnostics" in payload || "current_revision" in payload)
      ) {
        return JSON.stringify(payload);
      }
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
  recordingSessionId?: string;
  cameraSlot?: "cam_1" | "cam_2";
  /** 任务级推理开关：YOLO 人体检测 / RTMPose 姿态识别（不传则后端沿用全局配置） */
  enableModelInference?: boolean;
  enablePoseInference?: boolean;
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

export async function requestAutomaticCalibration(
  videoId: string,
  options?: { timestampSeconds?: number; frameIndex?: number }
): Promise<AutomaticCalibrationResponse> {
  return requestJson<AutomaticCalibrationResponse>("/calibration/automatic", {
    body: JSON.stringify({
      video_id: videoId,
      timestamp_seconds: options?.timestampSeconds,
      frame_index: options?.frameIndex,
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
    const job = normalizeAnalysisJobSummary(await requestJson<AnalysisJobSummary>("/api/analysis/jobs", {
      body: JSON.stringify({
        metadata: request.metadata,
        videoId: request.videoId,
        calibrationId: request.calibrationId,
        frameStride: request.frameStride ?? 2,
        sourceFps: request.metadata.sourceFps,
        priority: request.priority ?? 0,
        requestNewVersion: request.requestNewVersion ?? false,
        recording_session_id: request.recordingSessionId,
        camera_slot: request.cameraSlot,
        enableModelInference: request.enableModelInference,
        enablePoseInference: request.enablePoseInference,
      }),
      method: "POST",
    }));
    rememberAnalysisJob(job);
    return job;
  } catch (error) {
    if (request.videoId || request.useDemoFallback !== true) {
      throw error;
    }

    const metadata = request.metadata;
    const job = buildMockJob(metadata);
    saveStoredJob(job);
    rememberAnalysisJob(job.summary);
    return job.summary;
  }
}

export async function listAnalysisJobs(options: DemoFallbackOptions = {}): Promise<AnalysisJobSummary[]> {
  try {
    const jobs = (await requestJson<AnalysisJobSummary[]>("/api/analysis/jobs")).map(normalizeAnalysisJobSummary);
    if (jobs.length) {
      rememberAnalysisJob(jobs[0]);
      return jobs;
    }
    const storedJobs = options.useDemoFallback ? getStoredJobSummaries() : [];
    if (storedJobs.length) {
      rememberAnalysisJob(storedJobs[0]);
    }
    return storedJobs;
  } catch (error) {
    const storedJobs = options.useDemoFallback ? getStoredJobSummaries() : [];
    if (storedJobs.length) {
      rememberAnalysisJob(storedJobs[0]);
      return storedJobs;
    }
    throw error;
  }
}

// ── 双摄（multiview）协同分析 ──

export interface MultiViewCreateViewPayload {
  viewId: string;
  cameraId?: string;
  videoId: string;
  calibrationId: string;
  courtOrientation: "identity" | "rotate_180" | "mirror_x" | "mirror_y" | null;
}

export interface MultiviewAnalysisJobRequest {
  metadata: AnalysisUploadMetadata;
  frameStride?: number;
  referenceViewId: string;
  views: MultiViewCreateViewPayload[];
  executionMode?: "late_fusion_v1" | "joint_tracking_v2";
  /** Opt-in canonical diagnostic replay; requires joint_tracking_v2. */
  debugTraceEnabled?: boolean;
  canonicalFrame?: { endA: string; endB: string };
  /** 分析窗口（take 公共时间轴 ms；缺省整场）。secondary 由后端经 sync 换算到自身时间轴。 */
  clipStartMs?: number;
  clipEndMs?: number;
}

/**
 * 创建双摄协同分析任务：后端创建 1 个 public Parent + 2 个 internal child。
 * 前端绝不 create 两个 job 再调 fusion（业务编排不泄漏到浏览器）。
 */
export async function createMultiviewAnalysisJob(request: MultiviewAnalysisJobRequest): Promise<AnalysisJobSummary> {
  const job = normalizeAnalysisJobSummary(await requestJson<AnalysisJobSummary>("/api/analysis/jobs", {
    body: JSON.stringify({
      metadata: request.metadata,
      frameStride: request.frameStride ?? 2,
      clipStartMs: request.clipStartMs,
      clipEndMs: request.clipEndMs,
      analysisKind: "multiview",
      multiview: {
        referenceViewId: request.referenceViewId,
        views: request.views,
        executionMode: request.executionMode ?? "late_fusion_v1",
        debugTraceEnabled: request.debugTraceEnabled ?? false,
        canonicalFrame: request.canonicalFrame,
      },
    }),
    method: "POST",
  }));
  rememberAnalysisJob(job);
  return job;
}

export async function getFusedManifest(jobId: string): Promise<FusedManifest | null> {
  try {
    return await requestJson<FusedManifest>(`/api/analysis/jobs/${jobId}/artifacts/fused-manifest`);
  } catch (error) {
    if (error && typeof error === "object" && "status" in error && (error as { status: number }).status === 404) {
      return null;
    }
    throw error;
  }
}

/** 融合质量诊断（fused_diagnostics）：双视角共同观测 / 单视角补偿 / 预测补点 / 视角位置差异等 */
export interface FusionDiagnostics {
  schema_version?: string;
  run_id?: string;
  fusion_status_counts?: Record<string, number>;
  sample_count?: number;
  metric_eligible_count?: number;
  view_disagreement?: { median_distance_ft?: number | null; mean_distance_ft?: number | null; dual_samples?: number };
  fallback?: boolean;
  reason?: string;
}

export async function getFusionDiagnostics(jobId: string): Promise<FusionDiagnostics | null> {
  try {
    return await requestJson<FusionDiagnostics>(`/api/analysis/jobs/${jobId}/artifacts/fusion-diagnostics`);
  } catch (error) {
    if (error && typeof error === "object" && "status" in error && (error as { status: number }).status === 404) {
      return null;
    }
    throw error;
  }
}

export async function getMultiviewObservability(jobId: string): Promise<MultiviewObservabilitySummary | null> {
  try {
    return await requestJson<MultiviewObservabilitySummary>(`/api/analysis/jobs/${jobId}/multiview/observability`);
  } catch (error) {
    if (isAnalysisApiError(error) && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export interface RecoveryEpisodeFilters {
  cursor?: string | null;
  limit?: number;
  outcome?: RecoveryOutcome | "";
  global_player_id?: string;
  donor_view?: string;
  target_view?: string;
  from_ms?: number;
  to_ms?: number;
}

export async function getMultiviewRecoveryEpisodes(jobId: string, filters: RecoveryEpisodeFilters = {}): Promise<RecoveryEpisodePage> {
  const params = new URLSearchParams();
  if (filters.cursor) params.set("cursor", filters.cursor);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.outcome) params.set("outcome", filters.outcome);
  if (filters.global_player_id) params.set("global_player_id", filters.global_player_id);
  if (filters.donor_view) params.set("donor_view", filters.donor_view);
  if (filters.target_view) params.set("target_view", filters.target_view);
  if (filters.from_ms != null) params.set("from_ms", String(filters.from_ms));
  if (filters.to_ms != null) params.set("to_ms", String(filters.to_ms));
  const query = params.toString();
  return requestJson<RecoveryEpisodePage>(`/api/analysis/jobs/${jobId}/multiview/recovery-events${query ? `?${query}` : ""}`);
}

export function getMultiviewDebugVideoUrl(jobId: string): string {
  return toApiUrl(`/api/analysis/jobs/${jobId}/multiview/debug-video`);
}

export async function deleteAnalysisJob(jobId: string, options: DemoFallbackOptions = {}): Promise<AnalysisDeleteResult> {
  try {
    const result = await requestJson<AnalysisDeleteResult>(`/api/analysis/jobs/${jobId}`, {
      method: "DELETE",
    });
    if (result.status === "deleted") {
      deleteStoredJobs([jobId]);
    }
    return result;
  } catch (error) {
    const stored = options.useDemoFallback ? getStoredDemoJob(jobId) : undefined;
    if (stored) {
      return deleteStoredJobs([jobId])[0];
    }
    throw error;
  }
}

export async function deleteAnalysisJobs(jobIds: string[], options: DemoFallbackOptions = {}): Promise<AnalysisDeleteResult[]> {
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
    const storedJobs = options.useDemoFallback ? getStoredDemoJobs() : {};
    const hasAnyStored = jobIds.some((jobId) => storedJobs[jobId]);
    if (hasAnyStored) {
      return deleteStoredJobs(jobIds);
    }
    throw error;
  }
}

export async function cancelAnalysisJob(jobId: string): Promise<AnalysisJobSummary> {
  const job = normalizeAnalysisJobSummary(await requestJson<AnalysisJobSummary>(`/api/analysis/jobs/${jobId}/cancel`, {
    method: "POST",
  }));
  rememberAnalysisJob(job);
  return job;
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJobSummary | null> {
  try {
    const job = normalizeAnalysisJobSummary(await requestJson<AnalysisJobSummary>(`/api/analysis/jobs/${jobId}`));
    rememberAnalysisJob(job);
    return job;
  } catch (error) {
    const stored = getStoredDemoJob(jobId);
    if (stored) {
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
    const stored = getStoredDemoJob(jobId);
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
    const result = await requestJson<AnalysisPipelineResult | AnalysisJobSummary>(`/api/analysis/jobs/${jobId}/result`);
    return isAnalysisJobSummary(result) ? normalizeAnalysisJobSummary(result) : result;
  } catch (error) {
    const stored = getStoredDemoJob(jobId);
    if (stored) {
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

export interface VideoTimingFrame {
  frame_index: number;
  pts_seconds: number;
  dts_seconds?: number | null;
  keyframe?: boolean;
}

export interface VideoTimingResponse {
  schema_version: string;
  authority: "source_pts" | "legacy_nominal_fps" | "missing";
  frame_count: number;
  fps?: number | null;
  first_pts_seconds?: number | null;
  last_pts_seconds?: number | null;
  frames: VideoTimingFrame[];
}

export async function getVideoTiming(videoId: string): Promise<VideoTimingResponse> {
  return requestJson<VideoTimingResponse>(`/api/videos/${videoId}/timing`);
}

export function resolveAnalysisAssetUrl(path?: string): string | undefined {
  return path ? toApiUrl(path) : undefined;
}

export async function getTrackingOverlay(result: AnalysisPipelineResult): Promise<TrackingOverlayArtifact | null> {
  const path = result.artifacts.tracking_overlay_url;
  return path ? requestJson<TrackingOverlayArtifact>(path) : null;
}

export async function getFusedPlayerOverlay(
  result: AnalysisPipelineResult,
): Promise<FusedPlayerOverlayArtifact | null> {
  const path = result.artifacts.fused_player_overlay_url;
  return path ? requestJson<FusedPlayerOverlayArtifact>(path) : null;
}

export async function getPlayerDisplayDiagnostics(
  jobId: string,
  playerId: string,
  timestampMs: number,
  windowMs = 500,
): Promise<PlayerDisplayDiagnosticsResponse> {
  const query = new URLSearchParams({
    timestamp_ms: String(timestampMs),
    window_ms: String(windowMs),
  });
  return requestJson<PlayerDisplayDiagnosticsResponse>(
    `/api/analysis/jobs/${jobId}/multiview/players/${playerId}/display-diagnostics?${query.toString()}`,
  );
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

export async function getReconstructedBallTrajectory(
  result: AnalysisPipelineResult,
): Promise<ReconstructedBallTrajectoryArtifact | null> {
  const path = result.artifacts.reconstructed_ball_trajectory_url;
  return path ? requestJson<ReconstructedBallTrajectoryArtifact>(path) : null;
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
  CameraUpdateRequest,
  CameraInfo,
  FieldSession,
  FieldSessionCreate,
  FieldSessionDeleteResult,
  ProbeResult,
  CaptureStopResult,
  RecordingSession,
  RecordingStartRequest,
  SessionTimelineEvent,
  SyncRecordingSession,
  SyncStartRequest,
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

export async function updateCamera(cameraId: string, request: CameraUpdateRequest): Promise<CameraInfo> {
  return requestJson<CameraInfo>(`/api/cameras/${encodeURIComponent(cameraId)}`, {
    body: JSON.stringify(request),
    method: "PATCH",
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

export type StorageLocation = {
  canceled: boolean;
  storage_root: string;
  captures_root?: string;
};

export async function getDefaultStorageLocation(): Promise<{ storage_root: string; source: "default" }> {
  return requestJson<{ storage_root: string; source: "default" }>("/api/storage/default");
}

export async function pickStorageLocation(): Promise<StorageLocation> {
  return requestJson<StorageLocation>("/api/storage/pick", { method: "POST" });
}

export async function validateStorageLocation(path: string): Promise<{ storage_root: string; captures_root: string }> {
  return requestJson<{ storage_root: string; captures_root: string }>("/api/storage/validate", {
    body: JSON.stringify({ path }),
    method: "POST",
  });
}

export async function startRecording(request: RecordingStartRequest): Promise<RecordingSession> {
  return requestJson<RecordingSession>("/api/recordings/start", {
    body: JSON.stringify(request),
    method: "POST",
  });
}

export async function stopRecording(sessionId: string): Promise<CaptureStopResult> {
  return requestJson<CaptureStopResult>(`/api/recordings/${sessionId}/stop`, {
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

export async function stopSyncRecording(sessionId: string): Promise<CaptureStopResult> {
  return requestJson<CaptureStopResult>(`/api/sync-recordings/${sessionId}/stop`, {
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

export async function deleteRecordingAnalysis(sessionId: string, options: DemoFallbackOptions = {}): Promise<AnalysisDeleteResult[]> {
  // 删除该双摄录制派生的所有分析任务及其本地产物；录制本身保留。
  try {
    const results = await requestJson<AnalysisDeleteResult[]>(`/api/sync-recordings/${sessionId}/analysis`, {
      method: "DELETE",
    });
    const deletedJobIds = results.filter((result) => result.status === "deleted").map((result) => result.job_id);
    if (deletedJobIds.length) {
      deleteStoredJobs(deletedJobIds);
    }
    return results;
  } catch (error) {
    if (options.useDemoFallback) {
      const storedJobs = getStoredDemoJobs();
      const recordingDerived = Object.values(storedJobs)
        .map((stored) => stored.summary)
        .filter(
          (job) => job.recordingSessionId === sessionId || job.metadata?.recording_session_id === sessionId,
        );
      if (recordingDerived.length) {
        return deleteStoredJobs(recordingDerived.map((job) => job.id));
      }
    }
    throw error;
  }
}

export async function mergeSyncRecording(sessionId: string): Promise<SyncRecordingSession> {
  return requestJson<SyncRecordingSession>(`/api/sync-recordings/${sessionId}/merge`, {
    method: "POST",
  });
}

export function getCameraPreviewUrl(cameraId?: string): string | undefined {
  return cameraId ? toApiUrl(`/api/cameras/${cameraId}/preview`) : undefined;
}

export function getShowcaseStreamUrl(runtimeId: string, slot: "cam_1" | "cam_2"): string {
  return toApiUrl(`/api/showcase-runtimes/${encodeURIComponent(runtimeId)}/streams/${slot}`);
}

export async function getShowcaseRuntimeStatus(runtimeId: string): Promise<ShowcaseRuntimeStatus> {
  return requestJson<ShowcaseRuntimeStatus>(`/api/showcase-runtimes/${encodeURIComponent(runtimeId)}`);
}

// Field Session API functions
export async function createFieldSession(request: FieldSessionCreate): Promise<FieldSession> {
  return normalizeFieldSession(await requestJson<FieldSession>("/api/field-sessions", {
    body: JSON.stringify(request),
    method: "POST",
  }));
}

function normalizeFieldSession(session: FieldSession): FieldSession {
  return { ...session, display_mode: session.display_mode === "showcase" ? "showcase" : "standard" };
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
  return (await requestJson<FieldSession[]>(`/api/field-sessions${q ? `?${q}` : ""}`)).map(normalizeFieldSession);
}

export async function getFieldSession(id: string): Promise<FieldSession> {
  return normalizeFieldSession(await requestJson<FieldSession>(`/api/field-sessions/${id}`));
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

export async function getSyncAnchorStatus(takeId: string, requireManual = false): Promise<SyncAnchorStatus> {
  const query = requireManual ? "?require_manual=true" : "";
  return requestJson<SyncAnchorStatus>(`/api/capture-takes/${takeId}/sync-anchors/status${query}`);
}

export async function getSyncAnchorDraft(takeId: string): Promise<SyncAnchorDraftResponse> {
  return requestJson<SyncAnchorDraftResponse>(`/api/capture-takes/${takeId}/sync-anchors/draft`);
}

export async function saveSyncAnchorDraft(takeId: string, draft: SyncAnchorDraft): Promise<SyncAnchorDraftResponse> {
  return requestJson<SyncAnchorDraftResponse>(`/api/capture-takes/${takeId}/sync-anchors/draft`, {
    method: "PUT",
    body: JSON.stringify(draft),
  });
}

export async function confirmSyncAnchors(
  takeId: string,
  request: Omit<SyncAnchorDraft, "expected_revision"> & { expected_revision: number },
): Promise<SyncAnchorConfirmResponse> {
  return requestJson<SyncAnchorConfirmResponse>(`/api/capture-takes/${takeId}/sync-anchors/confirm`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getSyncAnchorExportUrl(takeId: string): string {
  return toApiUrl(`/api/capture-takes/${takeId}/sync-anchors/export`);
}

export async function getMergeStatus(takeId: string): Promise<{ status: string; detail?: string }> {
  return requestJson(`/api/capture-takes/${takeId}/finalization-status`);
}

export async function getLiveCodingState(takeId: string): Promise<LiveCodingState> {
  return requestJson<LiveCodingState>(`/api/capture-takes/${takeId}/live-state`);
}

export async function getActiveCaptureTake(): Promise<{
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
} | null> {
  return requestJson(`/api/capture-takes/active`);
}

export async function forceFinalizeActiveCaptureTake(): Promise<{ ok: boolean; detail: string }> {
  return requestJson<{ ok: boolean; detail: string }>(`/api/capture-takes/active/force-finalize`, {
    method: "POST",
  });
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

export function listVidatPackages(captureTakeId: string): Promise<VidatPackage[]> {
  return requestJson(`/api/vidat/capture-takes/${captureTakeId}/packages`);
}

export function createVidatPackage(captureTakeId: string): Promise<VidatPackage> {
  return requestJson(`/api/vidat/capture-takes/${captureTakeId}/packages`, { method: "POST" });
}

export function openVidatPackage(packageId: string): Promise<{ url: string; package_id: string }> {
  return requestJson(`/api/vidat/packages/${packageId}/open`, { method: "POST" });
}

export function startVidatService(): Promise<{ url: string; started: boolean }> {
  return requestJson("/api/vidat/service/start", { method: "POST" });
}

export function previewVidatImport(packageId: string, annotation: unknown): Promise<VidatImportPreview> {
  return requestJson(`/api/vidat/packages/${packageId}/import-previews`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ annotation }),
  });
}

export function confirmVidatImport(packageId: string, confirmationToken: string, annotation: unknown): Promise<{ audit_id: string }> {
  return requestJson(`/api/vidat/packages/${packageId}/import-confirmations`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation_token: confirmationToken, annotation }),
  });
}

export async function getCaptureTakeRuntimeStatus(
  takeId: string,
): Promise<CaptureTakeRuntimeStatus> {
  const raw = await requestJson<{
    capture_take_id: string;
    capture_mode: "single" | "dual";
    storage: CaptureTakeRuntimeStatus["storage"] & {
      total_bytes?: number | null;
      used_bytes?: number | null;
      free_bytes?: number | null;
    };
    recording: {
      phase: string;
      started_at?: string | null;
      elapsed_ms?: number | null;
      duration_ms?: number | null;
      target_fps?: number | null;
      target_width?: number | null;
      target_height?: number | null;
      file_size_bytes?: CaptureTakeRuntimeStatus["recording"]["fileSizeBytes"];
      effective_fps?: CaptureTakeRuntimeStatus["recording"]["effectiveFps"];
      avg_bitrate_bps?: CaptureTakeRuntimeStatus["recording"]["avgBitrateBps"];
    };
    tracks: Array<{
      track_id: string;
      slot: "cam_1" | "cam_2";
      camera_id: string;
      phase: string;
      file_size_bytes: CaptureTakeRuntimeStatus["recording"]["fileSizeBytes"];
      effective_fps: CaptureTakeRuntimeStatus["recording"]["effectiveFps"];
      error?: string | null;
    }>;
    sync?: {
      dual_sync: CaptureTakeRuntimeStatus["sync"] extends infer S
        ? S extends { dualSync: infer D } ? D : never
        : never;
      dual_sync_quality?: "good" | "degraded" | "unknown" | null;
      event_sync: CaptureTakeRuntimeStatus["sync"] extends infer S
        ? S extends { eventSync: infer E } ? E : never
        : never;
      message?: string | null;
    } | null;
    updated_at: string;
  }>(
    `/api/capture-takes/${takeId}/runtime-status`,
  );
  return {
    captureTakeId: raw.capture_take_id,
    captureMode: raw.capture_mode,
    storage: {
      state: raw.storage.state,
      totalBytes: raw.storage.total_bytes,
      usedBytes: raw.storage.used_bytes,
      freeBytes: raw.storage.free_bytes,
      message: raw.storage.message,
    },
    recording: {
      phase: raw.recording.phase,
      startedAt: raw.recording.started_at,
      elapsedMs: raw.recording.elapsed_ms,
      durationMs: raw.recording.duration_ms,
      targetFps: raw.recording.target_fps,
      targetWidth: raw.recording.target_width,
      targetHeight: raw.recording.target_height,
      fileSizeBytes: raw.recording.file_size_bytes ?? { state: "collecting" },
      effectiveFps: raw.recording.effective_fps ?? { state: "collecting" },
      avgBitrateBps: raw.recording.avg_bitrate_bps ?? { state: "collecting" },
    },
    tracks: raw.tracks.map((track) => ({
      trackId: track.track_id,
      slot: track.slot,
      cameraId: track.camera_id,
      phase: track.phase,
      fileSizeBytes: track.file_size_bytes,
      effectiveFps: track.effective_fps,
      error: track.error,
    })),
    sync: raw.sync
      ? {
          dualSync: raw.sync.dual_sync,
          dualSyncQuality: raw.sync.dual_sync_quality,
          eventSync: raw.sync.event_sync,
          message: raw.sync.message,
        }
      : null,
    updatedAt: raw.updated_at,
  };
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
