import type { AnalysisJobSummary, AnalysisPipelineResult } from "../types/report";

export type ReportCapabilityState = "available" | "unavailable" | "loading";

export interface ReportCapability {
  state: ReportCapabilityState;
  reason: string;
  evidence: {
    canonicalTracks: boolean;
    movementMetrics: boolean;
    structuredVisualization: boolean;
  };
}

export interface ReportCapabilityInput {
  job?: Pick<AnalysisJobSummary, "status"> | null;
  manifest?: AnalysisPipelineResult | null;
  manifestState?: "idle" | "loading" | "loaded" | "error";
}

const EMPTY_EVIDENCE: ReportCapability["evidence"] = {
  canonicalTracks: false,
  movementMetrics: false,
  structuredVisualization: false,
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isCanonicalPlayerId(value: unknown): value is string {
  return typeof value === "string" && /^Player_\d+$/i.test(value.trim());
}

function hasValidCanonicalTracks(result: AnalysisPipelineResult): boolean {
  return Array.isArray(result.tracks) && result.tracks.some((track) => (
    isCanonicalPlayerId(track.track_id)
    && isFiniteNumber(track.court_point?.x)
    && isFiniteNumber(track.court_point?.y)
  ));
}

function hasValidMovementMetrics(result: AnalysisPipelineResult): boolean {
  const metrics = result.metrics;
  return (
    Array.isArray(metrics?.distances)
      && metrics.distances.some((item) => isCanonicalPlayerId(item.track_id) && isFiniteNumber(item.distance_ft))
  ) || (
    Array.isArray(metrics?.speeds)
      && metrics.speeds.some((item) => (
        isCanonicalPlayerId(item.track_id)
        && (isFiniteNumber(item.average_speed_ft_per_s) || isFiniteNumber(item.max_speed_ft_per_s))
      ))
  ) || (
    Array.isArray(metrics?.kitchen_dwell)
      && metrics.kitchen_dwell.some((item) => (
        isCanonicalPlayerId(item.track_id)
        && (isFiniteNumber(item.kitchen_frames) || isFiniteNumber(item.kitchen_seconds))
      ))
  );
}

function hasAvailableStructuredVisualization(result: AnalysisPipelineResult): boolean {
  const artifacts = result.artifacts;
  if (!artifacts?.structured_visualization_data_path) return false;
  return !["failed", "skipped", "unavailable", "no_data"].includes(
    artifacts.position_visualizations_status ?? "available",
  );
}

/**
 * 报告入口的单一门控：完成任务 + 可读取 result manifest + 至少一类真实运动证据。
 * 单个模块（例如 zone_stats）缺失不关闭整份报告；完全没有有效证据才禁用。
 */
export function getReportCapability(input: ReportCapabilityInput): ReportCapability {
  const job = input.job;
  if (!job) {
    return { state: "unavailable", reason: "该素材尚无可用的分析结果", evidence: EMPTY_EVIDENCE };
  }
  if (job.status !== "completed") {
    return { state: "unavailable", reason: "分析任务尚未完成，报告不可用", evidence: EMPTY_EVIDENCE };
  }
  if (input.manifestState === "idle" || input.manifestState === "loading") {
    return { state: "loading", reason: "正在核对报告所需的真实分析数据", evidence: EMPTY_EVIDENCE };
  }
  if (input.manifestState === "error" || !input.manifest) {
    return { state: "unavailable", reason: "该历史任务没有可读取的分析产物", evidence: EMPTY_EVIDENCE };
  }
  if (input.manifest.status !== "completed") {
    return { state: "unavailable", reason: "分析结果未成功完成，无法生成有效报告", evidence: EMPTY_EVIDENCE };
  }

  const evidence = {
    canonicalTracks: hasValidCanonicalTracks(input.manifest),
    movementMetrics: hasValidMovementMetrics(input.manifest),
    structuredVisualization: hasAvailableStructuredVisualization(input.manifest),
  };
  if (evidence.canonicalTracks || evidence.movementMetrics || evidence.structuredVisualization) {
    return { state: "available", reason: "", evidence };
  }
  return {
    state: "unavailable",
    reason: "本次分析没有有效球员轨迹、运动指标或区域可视化数据",
    evidence,
  };
}
