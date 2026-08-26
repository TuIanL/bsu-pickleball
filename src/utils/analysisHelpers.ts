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

/** 终端失败/取消任务：可作为「一键清除」的目标 */
export function isTerminalAnalysisJob(job: AnalysisJobSummary) {
  return job.status === "failed" || job.status === "canceled" || job.status === "interrupted";
}

/** 任务排序键：创建时间 / 更新时间 */
export type AnalysisSortKey = "createdAt" | "updatedAt";
/** 任务排序方向：新→旧 / 旧→新 */
export type AnalysisSortDir = "asc" | "desc";

function jobTimeValue(job: AnalysisJobSummary, key: AnalysisSortKey): number {
  const raw = key === "updatedAt" ? (job.updatedAt || job.createdAt) : job.createdAt;
  const ms = raw ? new Date(raw).getTime() : 0;
  return Number.isFinite(ms) ? ms : 0;
}

/** 按创建/更新时间对任务列表排序（不修改原数组）。updatedAt 缺失时回退 createdAt。 */
export function sortAnalysisJobs(
  jobs: AnalysisJobSummary[],
  key: AnalysisSortKey,
  dir: AnalysisSortDir,
): AnalysisJobSummary[] {
  const factor = dir === "asc" ? 1 : -1;
  return [...jobs].sort((a, b) => (jobTimeValue(a, key) - jobTimeValue(b, key)) * factor);
}

export function analysisStatusMeta(status: AnalysisJobSummary["status"]) {
  const styles = {
    uploaded: { label: "视频已接收", className: "bg-[#2F80ED]/12 text-[#1E63B6]" },
    queued: { label: "排队中", className: "bg-[#2F80ED]/12 text-[#1E63B6]" },
    processing: { label: "正在分析", className: "bg-[#FF9500]/14 text-[#A45A00]" },
    completed: { label: "分析完成", className: "bg-[#22C55E]/14 text-[#168A34]" },
    failed: { label: "分析失败", className: "bg-[#FF4D4F]/12 text-[#C92A2A]" },
    canceled: { label: "已取消", className: "bg-slate-200 text-slate-700" },
    interrupted: { label: "任务失联", className: "bg-[#FF9500]/14 text-[#A45A00]" },
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

/** 解析后端 canonical player id（Player_1..Player_4）为数字 1..4；非 canonical 返回 null。 */
export function canonicalPlayerNumber(value?: string | null): number | null {
  if (!value) return null;
  const match = /^Player_([1-4])$/.exec(value.trim());
  return match ? Number(match[1]) : null;
}

/** 把 canonical player id 映射为对外展示标签（P1..P4）。非 canonical 返回空串，绝不显示原始 track_id。 */
export function formatPlayerId(value?: string | null): string {
  const number = canonicalPlayerNumber(value);
  return number === null ? "" : `P${number}`;
}

/** 前端 canonical 球员颜色映射（镜像后端 PLAYER_HEX_COLORS，保持现有调色板不变）。 */
export const PLAYER_ID_TO_COLOR: Record<string, string> = {
  Player_1: "#22C55E",
  Player_2: "#F97316",
  Player_3: "#A855F7",
  Player_4: "#3B82F6",
};

/** 非 canonical 球员标识的兜底颜色（中性灰）。 */
export const UNKNOWN_PLAYER_COLOR = "#94A3B8";

/** 返回 canonical 球员 id 的展示颜色；非 canonical 回退兜底色。 */
export function playerColor(playerId?: string | null): string {
  return playerId ? (PLAYER_ID_TO_COLOR[playerId] ?? UNKNOWN_PLAYER_COLOR) : UNKNOWN_PLAYER_COLOR;
}

/**
 * 从分析结果轨迹提取去重后的 canonical 球员列表（按数字自然序）。
 * 只保留 canonical `Player_1`..`Player_4`；无有效轨迹时按预期球员数兜底（默认 4，单打 2）。
 */
export function buildPlayerRoster(
  tracks: ReadonlyArray<{ track_id?: string }> | null | undefined,
  expectedPlayerCount?: number,
): string[] {
  const ids = new Set<string>();
  for (const track of tracks ?? []) {
    const id = track.track_id;
    if (id && canonicalPlayerNumber(id) !== null) {
      ids.add(id);
    }
  }
  const sorted = [...ids].sort((a, b) => (canonicalPlayerNumber(a) ?? 0) - (canonicalPlayerNumber(b) ?? 0));
  if (sorted.length > 0) {
    return sorted;
  }
  const count = expectedPlayerCount === 2 ? 2 : 4;
  return Array.from({ length: count }, (_, i) => `Player_${i + 1}`);
}

/** 分析模式值：样例任务 / 有限真实分析 / 真实视频分析 */
export type AnalysisModeValue = NonNullable<AnalysisJobSummary["analysisMode"]>;

/** 三种分析模式的有序列表，用于「按类型选择」选项卡（demo 为样例，limited 为有限真实，real 为真实视频） */
export const ANALYSIS_MODES: readonly AnalysisModeValue[] = ["demo", "limited", "real"];

/** 返回指定分析模式下可删除（非活跃）的任务，用于按模式批量选择 */
export function eligibleJobsByMode(jobs: AnalysisJobSummary[], mode: AnalysisModeValue): AnalysisJobSummary[] {
  return jobs.filter((job) => job.analysisMode === mode && !isActiveAnalysisJob(job));
}

/**
 * 模式勾选三态：全部选中 checked / 部分选中 indeterminate / 未选中 unchecked。
 * 无可删任务（空集合）视为 unchecked，保证空态不可勾选。
 */
export function modeSelectionState(
  eligibleModeJobIds: string[],
  selectedJobIds: string[],
): "checked" | "indeterminate" | "unchecked" {
  if (eligibleModeJobIds.length === 0) {
    return "unchecked";
  }
  const selectedSet = new Set(selectedJobIds);
  const selectedCount = eligibleModeJobIds.reduce(
    (count, jobId) => count + (selectedSet.has(jobId) ? 1 : 0),
    0,
  );
  if (selectedCount === 0) {
    return "unchecked";
  }
  if (selectedCount === eligibleModeJobIds.length) {
    return "checked";
  }
  return "indeterminate";
}

/**
 * 按模式批量增删选择集：check=true 把该模式全部可删任务加入选择集，
 * check=false 全部移除。不修改入参，返回新数组，保持 set 语义（去重、保留既有选择）。
 */
export function applyModeSelection(
  selectedJobIds: string[],
  eligibleModeJobIds: string[],
  check: boolean,
): string[] {
  const next = new Set(selectedJobIds);
  for (const jobId of eligibleModeJobIds) {
    if (check) {
      next.add(jobId);
    } else {
      next.delete(jobId);
    }
  }
  return [...next];
}
