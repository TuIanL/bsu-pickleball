import { useMemo } from "react";
import type { FusionObservabilityData, MultiviewObservabilitySummary, ObservabilityAvailability, RecoveryObservabilityData, RefinementObservabilityData, SyncObservabilityData } from "../../../types/multiviewObservability";
import { deriveHealthScore } from "../../../lib/observabilityViz";
import { VIZ_PALETTE } from "./EChart";

export type PipelineStageId = "sync" | "fusion" | "recovery" | "refinement";

const STAGE_META: Array<{ id: PipelineStageId; label: string; title: string }> = [
  { id: "sync", label: "SYNC", title: "同步" },
  { id: "fusion", label: "FUSION", title: "融合" },
  { id: "recovery", label: "RECOVERY", title: "恢复" },
  { id: "refinement", label: "REFINEMENT", title: "精修" },
];

function tone(availability: ObservabilityAvailability) {
  switch (availability) {
    case "available":
      return { dot: VIZ_PALETTE.green, text: "#16733A", ring: "#B7E7C2", bg: "#F1FBF3" };
    case "partial":
      return { dot: VIZ_PALETTE.amber, text: "#A45A00", ring: "#F6D79A", bg: "#FFF9ED" };
    case "unavailable":
      return { dot: VIZ_PALETTE.red, text: "#A32D2D", ring: "#F2C2C2", bg: "#FFF5F5" };
    case "not_applicable":
      return { dot: VIZ_PALETTE.gray, text: "#64748B", ring: "#DDE9D6", bg: "#F5FAF1" };
  }
}

function stageKeyNumber(stageId: PipelineStageId, summary: MultiviewObservabilitySummary): string {
  const section = summary.sections[stageId];
  if (section.availability === "not_applicable") return "不适用";
  const data = section.data as (SyncObservabilityData & FusionObservabilityData & RecoveryObservabilityData & RefinementObservabilityData) | undefined;
  switch (stageId) {
    case "sync":
      return data?.reference_view ? `参考 ${data.reference_view}` : data?.sync_quality ?? section.status;
    case "fusion": {
      const ratio = data?.effective_multiview_ratio;
      return ratio == null ? "—" : `有效 ${Math.round(ratio * 100)}%`;
    }
    case "recovery": {
      const funnel = data?.funnel;
      const opportunities = Number(funnel?.recovery_opportunity_count ?? 0);
      if (!opportunities) return "无恢复机会";
      const recovered = Number(funnel?.guided_recovery_success_count ?? 0) + Number(funnel?.base_recovered_count ?? 0);
      return `${opportunities} 次 · ${Math.round((recovered / opportunities) * 100)}%`;
    }
    case "refinement":
      return data?.final_source === "refined_f1" ? "发布 F1" : data?.final_source === "first_pass_f0" ? "保留 F0" : section.status;
  }
}

/**
 * L1 概览条：一句话结论 + 健康度评分（标注"前端汇总"）+ 四阶段流水线状态灯。
 * 仅消费后端已发布事实，不重算算法结论。
 */
export function L1OverviewBar({ summary, onStageClick }: { summary: MultiviewObservabilitySummary; onStageClick?: (stage: PipelineStageId) => void }) {
  const health = useMemo(() => {
    const sections = summary.sections;
    const fusionData = sections.fusion.data as FusionObservabilityData | undefined;
    const recoveryData = sections.recovery.data as RecoveryObservabilityData | undefined;
    const funnel = recoveryData?.funnel;
    const opportunities = Number(funnel?.recovery_opportunity_count ?? 0);
    const recovered = Number(funnel?.guided_recovery_success_count ?? 0) + Number(funnel?.base_recovered_count ?? 0);
    return deriveHealthScore({
      availability: {
        sync: sections.sync.availability,
        fusion: sections.fusion.availability,
        recovery: sections.recovery.availability,
        refinement: sections.refinement.availability,
      },
      effectiveMultiviewRatio: fusionData?.effective_multiview_ratio ?? null,
      recoverySuccessRate: opportunities > 0 ? recovered / opportunities : null,
    });
  }, [summary]);

  const scoreTone = health.score >= 85 ? VIZ_PALETTE.green : health.score >= 60 ? VIZ_PALETTE.amber : VIZ_PALETTE.red;

  return (
    <section className="sport-card p-5 sm:p-6" data-testid="l1-overview-bar">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-[0.68rem] font-black uppercase tracking-[0.16em] text-[#168A34]">OVERVIEW</p>
          <h2 className="mt-1 text-lg font-black text-[#14241B]">运行概览</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600" data-testid="overview-conclusion">{health.conclusion}</p>
          <p className="mt-1 text-xs text-slate-400">健康度由前端基于后端已发布事实汇总，不重新计算算法结论。</p>
        </div>
        <div className="flex shrink-0 flex-col items-center rounded-2xl border border-[#DDE9D6] bg-[#F7FBF5] px-5 py-3" data-testid="health-score">
          <span className="text-4xl font-black leading-none" style={{ color: scoreTone }}>{health.score}</span>
          <span className="mt-1 text-xs font-bold text-slate-500">健康度 / 100</span>
        </div>
      </div>

      <div className="mt-5 grid gap-px overflow-hidden rounded-2xl border border-[#DDE9D6] bg-[#DDE9D6] sm:grid-cols-4">
        {STAGE_META.map((stage) => {
          const section = summary.sections[stage.id];
          const t = tone(section.availability);
          return (
            <button
              className="bg-white p-4 text-left transition-colors hover:bg-[#F7FBF5]"
              data-testid={`pipeline-stage-${stage.id}`}
              key={stage.id}
              onClick={() => onStageClick?.(stage.id)}
              type="button"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-black tracking-[0.14em] text-slate-500">{stage.label}</span>
                <span className="inline-flex h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: t.dot }} aria-hidden="true" />
              </div>
              <p className="mt-2 break-words text-sm font-bold text-[#14241B]">{stageKeyNumber(stage.id, summary)}</p>
              <p className="mt-1 truncate text-xs font-semibold" style={{ color: t.text }}>{section.status}</p>
            </button>
          );
        })}
      </div>
    </section>
  );
}
