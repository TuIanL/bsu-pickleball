import { demoAnalysisReport } from "../data/demoData";
import type {
  AnalysisJobSummary,
  AnalysisPipelineResult,
  AnalysisReport,
  AnalysisStage,
  AnalysisStageId,
  AnalysisUploadMetadata,
  CalibrationPoint,
  ManualCalibrationResponse,
  PoseOverlayArtifact,
  TrackingOverlayArtifact,
  VideoUploadResponse,
} from "../types/report";

const API_BASE_URL = import.meta.env.VITE_ANALYSIS_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "pre-pickleball-analysis-jobs";

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
    detection: "预留 YOLO11 检测球员、球、球拍和场地元素",
    pose: "预留 RTMPose26 识别人体关键点",
    tracking: "关联球员、球和击球轨迹",
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

function saveStoredJob(job: StoredJob) {
  const jobs = getStoredJobs();
  jobs[job.summary.id] = job;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
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

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(toApiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    throw new Error(`Analysis API returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function requestForm<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(toApiUrl(path), {
    body,
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Analysis API returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

interface AnalysisJobRequest {
  calibrationId?: string;
  frameStride?: number;
  metadata: AnalysisUploadMetadata;
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

export async function createAnalysisJob(request: AnalysisJobRequest): Promise<AnalysisJobSummary> {
  try {
    return await requestJson<AnalysisJobSummary>("/api/analysis/jobs", {
      body: JSON.stringify({
        metadata: request.metadata,
        videoId: request.videoId,
        calibrationId: request.calibrationId,
        frameStride: request.frameStride ?? 30,
      }),
      method: "POST",
    });
  } catch (error) {
    if (request.videoId || request.useDemoFallback === false) {
      throw error;
    }

    const metadata = request.metadata;
    const job = buildMockJob(metadata);
    saveStoredJob(job);
    return job.summary;
  }
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJobSummary | null> {
  try {
    return await requestJson<AnalysisJobSummary>(`/api/analysis/jobs/${jobId}`);
  } catch {
    const stored = getStoredJobs()[jobId];
    return stored?.summary ?? null;
  }
}

export async function getAnalysisReport(jobId: string): Promise<AnalysisReport | null> {
  try {
    return await requestJson<AnalysisReport>(`/api/analysis/jobs/${jobId}/report`);
  } catch {
    const stored = getStoredJobs()[jobId];
    return stored?.report ?? null;
  }
}

export async function getAnalysisResult(jobId: string): Promise<AnalysisPipelineResult | AnalysisJobSummary | null> {
  try {
    return await requestJson<AnalysisPipelineResult | AnalysisJobSummary>(`/api/analysis/jobs/${jobId}/result`);
  } catch {
    const stored = getStoredJobs()[jobId];
    return stored?.summary ?? null;
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

export { demoAnalysisReport };
