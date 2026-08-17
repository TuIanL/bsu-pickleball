/**
 * 联合运行状态页面的可视化辅助（纯函数，无 DOM 依赖，便于单元测试）。
 *
 * 健康度评分与一句话结论均只消费后端已发布事实（availability、
 * effective_multiview_ratio、恢复漏斗计数），是"展示汇总"，不重算任何算法结论。
 */

export type VizAvailability = "available" | "partial" | "unavailable" | "not_applicable";

export interface HealthScoreInput {
  /** 四大分域可用性（key 为 sync/fusion/recovery/refinement）。 */
  availability: Record<string, VizAvailability>;
  /** 有效多视角比例（0-1，缺失为 null）。 */
  effectiveMultiviewRatio?: number | null;
  /** 恢复成功率（0-1，缺失为 null）。 */
  recoverySuccessRate?: number | null;
}

export interface HealthScoreResult {
  /** 0-100 整数评分。 */
  score: number;
  /** 一句话结论（面向非专业用户）。 */
  conclusion: string;
  /** 参与的可用分域数（排除 not_applicable）。 */
  applicableCount: number;
}

/** availability → 权重（not_applicable 返回 null，表示不计入）。 */
export function availabilityWeight(availability: VizAvailability): number | null {
  switch (availability) {
    case "available":
      return 1;
    case "partial":
      return 0.6;
    case "unavailable":
      return 0;
    case "not_applicable":
      return null;
  }
}

/** 缺失维度时的中性分数（not_applicable 满分不拖累、available 半程、partial 低程、unavailable 零分）。 */
function neutralScore(availability: VizAvailability | undefined): number {
  switch (availability) {
    case "not_applicable":
      return 1;
    case "available":
      return 0.5;
    case "partial":
      return 0.3;
    default:
      return 0;
  }
}

/**
 * 推导健康度评分（0-100）。
 * 权重：分域健康 50% + 融合比例 25% + 恢复成功率 25%。
 * 缺失维度：有效多视角比例缺失时按融合分域可用性给中性值；
 * 恢复成功率缺失时按恢复分域可用性给中性值；对应分域不适用时该维度视为满分不拖累。
 */
export function deriveHealthScore(input: HealthScoreInput): HealthScoreResult {
  const weights = Object.values(input.availability)
    .map(availabilityWeight)
    .filter((weight): weight is number => weight !== null);
  const applicableCount = weights.length;
  const base = applicableCount === 0 ? 0 : weights.reduce((sum, weight) => sum + weight, 0) / applicableCount;

  const fusionAvailability = input.availability.fusion ?? "unavailable";
  const ratio = input.effectiveMultiviewRatio;
  const ratioScore = ratio != null ? Math.max(0, Math.min(1, ratio)) : neutralScore(fusionAvailability);

  const recoveryAvailability = input.availability.recovery ?? "unavailable";
  const recoveryRate = input.recoverySuccessRate;
  const recoveryScore = recoveryRate != null ? Math.max(0, Math.min(1, recoveryRate)) : neutralScore(recoveryAvailability);

  const score = Math.round(100 * (0.5 * base + 0.25 * ratioScore + 0.25 * recoveryScore));
  return { score, conclusion: deriveConclusion({ ...input, _base: base, _ratioScore: ratioScore, _recoveryScore: recoveryScore }), applicableCount };
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** 一句话结论（内部评分规则与 deriveHealthScore 保持一致）。 */
function deriveConclusion(input: HealthScoreInput & { _base: number; _ratioScore: number; _recoveryScore: number }): string {
  const unavailable = Object.entries(input.availability).filter(([, availability]) => availability === "unavailable");
  const degraded = Object.entries(input.availability).filter(([, availability]) => availability === "partial");
  const hasRatio = input.effectiveMultiviewRatio != null;
  const hasRecovery = input.recoverySuccessRate != null;

  if (input.availability.recovery === "not_applicable") {
    return `双摄协同分析完成（融合模式），${hasRatio ? `有效多视角比例 ${percent(input.effectiveMultiviewRatio as number)}` : "恢复机制不适用"}`;
  }
  if (unavailable.length > 0) {
    return `部分诊断证据缺失（${unavailable.map(([name]) => name).join("、")}），已按可用事实汇总，建议展开明细排查`;
  }
  if (input._base >= 0.9) {
    return `双摄协同分析运行良好${hasRecovery ? `，恢复成功率 ${percent(input.recoverySuccessRate as number)}` : ""}${hasRatio ? `，融合有效比例 ${percent(input.effectiveMultiviewRatio as number)}` : ""}`;
  }
  if (input._base >= 0.7) {
    return `双摄协同分析完成，存在部分降级（${degraded.map(([name]) => name).join("、")}），整体结论可信`;
  }
  return "双摄协同分析存在较多异常，建议逐项展开各分域明细核验";
}
