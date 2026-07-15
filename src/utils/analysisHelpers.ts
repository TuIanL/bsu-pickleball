import type { AnalysisJobSummary, AnalysisUploadMetadata, InsightTone } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { isAnalysisApiError } from "../services/analysisClient";
import { errorToNotice as buildErrorNotice } from "../services/analysisDiagnostics";

export const toneStyles: Record<InsightTone, { dot: string; text: string; border: string; bg: string }> = {
  advantage: {
    dot: "bg-[#22C55E]",
    text: "text-[#168A34]",
    border: "border-[#22C55E]/25",
    bg: "bg-[#22C55E]/12",
  },
  risk: {
    dot: "bg-[#FF9500]",
    text: "text-[#A45A00]",
    border: "border-[#FF9500]/25",
    bg: "bg-[#FF9500]/12",
  },
  error: {
    dot: "bg-[#FF4D4F]",
    text: "text-[#C92A2A]",
    border: "border-[#FF4D4F]/25",
    bg: "bg-[#FF4D4F]/12",
  },
  training: {
    dot: "bg-[#2F80ED]",
    text: "text-[#1E63B6]",
    border: "border-[#2F80ED]/25",
    bg: "bg-[#2F80ED]/12",
  },
};

export function errorToNotice(title: string, fallbackBody: string, error: unknown): DiagnosticNotice {
  return buildErrorNotice(title, fallbackBody, error, isAnalysisApiError);
}

export function isActiveAnalysisJob(job: AnalysisJobSummary) {
  return ["uploaded", "queued", "processing"].includes(job.status);
}

export function isCancelableAnalysisJob(job: AnalysisJobSummary) {
  return ["uploaded", "queued", "processing"].includes(job.status);
}

export function analysisStatusMeta(status: AnalysisJobSummary["status"]) {
  const styles = {
    uploaded: { label: "视频已接收", className: "bg-[#2F80ED]/12 text-[#1E63B6]" },
    queued: { label: "排队中", className: "bg-[#2F80ED]/12 text-[#1E63B6]" },
    processing: { label: "正在分析", className: "bg-[#FF9500]/14 text-[#A45A00]" },
    completed: { label: "分析完成", className: "bg-[#22C55E]/14 text-[#168A34]" },
    failed: { label: "分析失败", className: "bg-[#FF4D4F]/12 text-[#C92A2A]" },
    canceled: { label: "已取消", className: "bg-slate-200 text-slate-700" },
  } satisfies Record<AnalysisJobSummary["status"], { label: string; className: string }>;

  return styles[status];
}

export function analysisModeLabel(mode?: AnalysisJobSummary["analysisMode"]) {
  if (mode === "real") {
    return "真实视频分析";
  }
  if (mode === "limited") {
    return "有限分析";
  }
  return "样例任务";
}

export function formatDateTime(value: string) {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return value;
  }
  return new Date(timestamp).toLocaleString();
}

export function formatDurationMs(value: number) {
  if (value < 1000) {
    return `${value}ms`;
  }
  if (value < 60_000) {
    return `${(value / 1000).toFixed(1)}s`;
  }
  return `${Math.floor(value / 60_000)}m ${Math.round((value % 60_000) / 1000)}s`;
}

export function cameraAngleLabel(angle: AnalysisUploadMetadata["cameraAngle"]) {
  const labels: Record<AnalysisUploadMetadata["cameraAngle"], string> = {
    baseline: "底线视角",
    sideline: "边线视角",
    elevated: "高位俯拍",
    unknown: "未知",
  };

  return labels[angle];
}
