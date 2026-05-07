import { demoAnalysisReport } from "../data/demoData";
import type {
  AnalysisJobSummary,
  AnalysisReport,
  AnalysisStage,
  AnalysisStageId,
  AnalysisUploadMetadata,
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
  "frame-sampling": "抽帧采样",
  detection: "目标检测",
  pose: "人体姿态",
  tracking: "轨迹跟踪",
  "court-calibration": "场地标定",
  "event-analysis": "事件分析",
  report: "报告生成",
};

const orderedStages: AnalysisStageId[] = [
  "upload",
  "queue",
  "frame-sampling",
  "detection",
  "pose",
  "tracking",
  "court-calibration",
  "event-analysis",
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
      label: stageLabels[stage],
      status,
      detail: getStageDetail(stage),
    };
  });
}

function getStageDetail(stage: AnalysisStageId) {
  const details: Record<AnalysisStageId, string> = {
    upload: "保存视频和基础比赛信息",
    queue: "等待视觉分析任务执行",
    "frame-sampling": "按时间轴抽取关键帧",
    detection: "预留 YOLO11 检测球员、球、球拍和场地元素",
    pose: "预留 RTMPose26 识别人体关键点",
    tracking: "关联球员、球和击球轨迹",
    "court-calibration": "映射画面坐标到匹克球场",
    "event-analysis": "识别击球、落点、回合和风险模式",
    report: "生成报告 JSON 并交给前端展示",
  };

  return details[stage];
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

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
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

export async function createAnalysisJob(metadata: AnalysisUploadMetadata): Promise<AnalysisJobSummary> {
  try {
    return await requestJson<AnalysisJobSummary>("/api/analysis/jobs", {
      body: JSON.stringify({ metadata }),
      method: "POST",
    });
  } catch {
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

export { demoAnalysisReport };
