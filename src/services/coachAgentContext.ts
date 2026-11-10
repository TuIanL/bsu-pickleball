// =============================================================
// 教学助教 Agent —— 上下文构建
// -------------------------------------------------------------
// 只把「可核对的东西」交给 Agent：
//   有效指标 + 单位 + 范围 + 质量状态 + 证据编号 + 已有发现。
// 明确不喂：skillRatings（轨迹完整度映射分）、progressPoints（MVP 映射值）等
// 会被误读成真实技术水平或长期趋势的字段。
// =============================================================
import { demoEvidence } from "../data/coachAgentDemo";
import type { PlayerReportEvidence } from "../evidence/evidenceTypes";
import type { EvidenceValue } from "../evidence/evidenceTypes";
import type { AnalysisReport } from "../types/report";

/** PbReportContext 里的球员主体（已归一化为 name 形态） */
export interface CoachSubject {
  id: string;
  name: string;
  role?: string;
}
import type { CoachContext, CoachEvidenceItem, CoachEvidenceQuality } from "../types/coachAgent";

function qualityFromConfidence(confidence?: number): CoachEvidenceQuality {
  if (typeof confidence !== "number") return "medium";
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

function formatEvidenceValue(value: unknown, unit: string): string {
  if (typeof value === "number") {
    const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
    return `${rounded}${unit}`;
  }
  return String(value);
}

/** 从证据层抽取可引用条目（只取 status === "available" 的） */
export function collectEvidenceItems(evidence: PlayerReportEvidence | null | undefined): CoachEvidenceItem[] {
  if (!evidence) return [];
  const items: CoachEvidenceItem[] = [];

  const push = (
    metric: string,
    value: EvidenceValue<number> | undefined,
    unit: string,
    detail: string
  ) => {
    if (!value || value.status !== "available") return;
    items.push({
      id: `E${items.length + 1}`,
      metric,
      value: formatEvidenceValue(value.value, unit),
      detail,
      quality: qualityFromConfidence(value.confidence),
    });
  };

  push("累计移动距离", evidence.courtCoverage?.distanceFt, " ft", "单场累计 · 轨迹投影");
  push("总击球数", evidence.summary?.totalShots, " 拍", "本场可归属到该球员的击球");
  push("进区率", evidence.summary?.inRatePct, "%", "落在有效区域的击球占比");
  push("发球数", evidence.serveReturn?.serveCount, " 次", "发球事件归属该球员");
  push("发球进区率", evidence.serveReturn?.serveInRatePct, "%", "发球落点在有效区域的比例");

  return items;
}

/** 从表现洞察里取「已有发现」作为证据补充（真实报告才存在） */
export function collectFindingEvidence(report: AnalysisReport): CoachEvidenceItem[] {
  const insights = report.performanceInsights;
  if (!insights || insights.status !== "available") return [];
  return insights.findings.slice(0, 3).map((finding, index) => ({
    id: `F${index + 1}`,
    metric: finding.dimension_label || finding.title,
    value: finding.title,
    detail: finding.diagnosis || finding.impact || "来自本次表现洞察",
    quality: finding.confidence,
    findingId: finding.id,
    windowLabel: finding.evidence_windows?.[0]
      ? `${formatMs(finding.evidence_windows[0].start_ms)}–${formatMs(finding.evidence_windows[0].end_ms)}`
      : undefined,
  }));
}

function formatMs(ms?: number | null): string {
  if (typeof ms !== "number" || !Number.isFinite(ms)) return "--:--";
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * 组装面板上下文。
 * demo 报告没有表现洞察，因此证据回落到演示样例，并由 source 标记提示界面不做真实结论声明。
 */
export function buildCoachContext(
  report: AnalysisReport,
  subject: CoachSubject | undefined,
  evidence: PlayerReportEvidence | null | undefined
): CoachContext {
  const isJob = report.source === "job";
  const realEvidence = [...collectEvidenceItems(evidence), ...collectFindingEvidence(report)];
  const hasInsights = !!report.performanceInsights && report.performanceInsights.status === "available";

  const playerLabel = subject?.name?.trim() || report.metadata?.athleteLabel?.trim() || "该球员";
  const taskLabel = isJob
    ? report.metadata?.matchTitle?.trim() || `任务 ${report.jobId ?? ""}`.trim()
    : "样例报告（脱敏演示数据）";

  const dataQuality = hasInsights
    ? report.performanceInsights?.data_quality_summary ?? "本次任务已生成可核对指标"
    : isJob
      ? "本次任务未生成表现洞察，仅提供原始可读指标"
      : "演示样例：指标为脱敏示例值，接真实任务后替换";

  return {
    taskLabel,
    playerLabel,
    source: isJob ? "job" : "demo",
    dataQuality,
    evidence: isJob ? realEvidence : realEvidence.length ? realEvidence : demoEvidence,
    hasInsights,
  };
}
