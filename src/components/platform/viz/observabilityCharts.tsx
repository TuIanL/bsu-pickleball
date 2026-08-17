import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import type { FusionObservabilityData, ObservabilityAvailability, RecoveryFunnel, RefinementObservabilityData, SyncObservabilityData } from "../../../types/multiviewObservability";
import { EChart, VIZ_PALETTE } from "./EChart";

const STAGE_LABELS = ["期望区域", "门内候选", "有检测框", "有位置", "球场投影", "正式观测", "全局关联", "绑定可见性", "连续漏检"] as const;

const COUNT_COLORS = [VIZ_PALETTE.green, VIZ_PALETTE.blue, VIZ_PALETTE.teal, VIZ_PALETTE.amber, VIZ_PALETTE.gray, "#7F77DD"];

/** 在图表可用时渲染，否则显示占位说明（避免空坐标系）。 */
function ChartOrPlaceholder({ available, reason, children }: { available: boolean; reason?: string; children: React.ReactNode }) {
  if (!available) {
    return <p className="rounded-2xl border border-dashed border-[#DDE9D6] bg-[#F7FBF5] p-4 text-sm leading-6 text-slate-600">{reason ?? "该分域暂无可用数据。"}</p>;
  }
  return <>{children}</>;
}

/** 同步权威：两视角时长对比柱 + 每视角 authority 文本（参考机位高亮）。 */
export function SyncAuthorityChart({ data, availability }: { data: SyncObservabilityData; availability: ObservabilityAvailability }) {
  const authority = data.per_view_authority ?? {};
  const provenance = data.timing_provenance as Record<string, { duration_seconds?: number; frame_count?: number; fps?: number }> | null | undefined;
  const views = Object.keys(authority).length > 0 ? Object.keys(authority) : provenance ? Object.keys(provenance) : [];
  const referenceView = data.reference_view;

  const option = useMemo<EChartsCoreOption | null>(() => {
    if (!provenance) return null;
    const rows = views.map((view) => {
      const meta = provenance[view] ?? {};
      return {
        view,
        duration: meta.duration_seconds ?? (meta.frame_count != null && meta.fps ? meta.frame_count / meta.fps : null),
        frameCount: meta.frame_count ?? null,
        fps: meta.fps ?? null,
      };
    });
    if (rows.every((row) => row.duration == null)) return null;
    return {
      grid: { left: 40, right: 16, top: 24, bottom: 32 },
      tooltip: {
        trigger: "axis",
        formatter: (params: Array<{ name: string; value: number; dataIndex: number }>) => {
          const row = rows[params[0]?.dataIndex ?? 0];
          if (!row) return "";
          return `${row.view}<br/>时长 ${row.duration?.toFixed(1) ?? "-"} s${row.frameCount != null ? ` · ${row.frameCount} 帧` : ""}${row.fps != null ? ` · ${row.fps} fps` : ""}<br/>authority: ${authority[row.view] ?? "-"}`;
        },
      },
      xAxis: { type: "category", data: rows.map((row) => row.view), axisLabel: { color: "#64748B", fontWeight: "bold" } },
      yAxis: { type: "value", name: "时长 (s)", nameTextStyle: { color: "#94A3B8" }, axisLabel: { color: "#64748B" }, splitLine: { lineStyle: { color: "#E7EFE2" } } },
      series: [
        {
          type: "bar",
          data: rows.map((row) => ({
            value: row.duration,
            itemStyle: { color: row.view === referenceView ? VIZ_PALETTE.green : "#B4B2A9", borderRadius: [6, 6, 0, 0] },
          })),
          barMaxWidth: 72,
          label: { show: true, position: "top", color: "#14241B", fontWeight: "bold", formatter: (p: { value: number }) => `${p.value?.toFixed(1)}s` },
        },
      ],
    };
  }, [authority, provenance, referenceView, views]);

  return (
    <ChartOrPlaceholder available={availability === "available" || availability === "partial"} reason="缺少时序证据，无法绘制视角对比图。">
      <div className="grid gap-2 sm:grid-cols-2">
        {views.map((view) => (
          <div className="flex items-center justify-between rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm" key={view}>
            <span className="text-slate-500">{view} authority</span>
            <strong className="text-[#14241B]">{authority[view] ?? "-"}</strong>
          </div>
        ))}
        {views.length === 0 ? <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm text-slate-500">无每视角权威数据</div> : null}
      </div>
      {option ? <div className="mt-3"><EChart ariaLabel="双视角时长对比柱状图" height={200} option={option} testId="sync-authority-chart" /></div> : null}
      {data.sync_quality ? <p className="mt-2 text-xs text-slate-500">同步质量：{data.sync_quality} · 参考机位：{referenceView ?? "-"}</p> : null}
    </ChartOrPlaceholder>
  );
}

/** 融合质量：有效比例环形图 + 状态计数堆叠条。 */
export function FusionQualityChart({ data, availability }: { data: FusionObservabilityData; availability: ObservabilityAvailability }) {
  const ratio = data.effective_multiview_ratio;
  const counts = data.status_counts ?? {};
  const countEntries = Object.entries(counts);

  const ratioOption = useMemo<EChartsCoreOption | null>(() => {
    if (ratio == null) return null;
    const pct = Math.round(ratio * 100);
    return {
      tooltip: { trigger: "item", formatter: (p: { name: string; value: number; percent: number }) => `${p.name}: ${p.value}%` },
      series: [
        {
          type: "pie",
          radius: ["62%", "82%"],
          center: ["50%", "52%"],
          avoidLabelOverlap: true,
          label: { show: true, position: "center", formatter: `${pct}%`, fontSize: 22, fontWeight: 700, color: VIZ_PALETTE.text },
          labelLine: { show: false },
          emphasis: { scale: false },
          data: [
            { name: "有效多视角", value: pct, itemStyle: { color: VIZ_PALETTE.green } },
            { name: "其余样本", value: 100 - pct, itemStyle: { color: "#E7EFE2" } },
          ],
        },
      ],
    };
  }, [ratio]);

  const countsOption = useMemo<EChartsCoreOption | null>(() => {
    if (countEntries.length === 0) return null;
    return {
      grid: { left: 40, right: 16, top: 20, bottom: 8 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (params: Array<{ seriesName: string; value: number }>) => params.map((p) => `${p.seriesName}: ${p.value}`).join("<br/>") },
      xAxis: { type: "value", axisLabel: { color: "#94A3B8" }, splitLine: { lineStyle: { color: "#E7EFE2" } } },
      yAxis: { type: "category", data: ["样本"], axisLabel: { show: false } },
      series: countEntries.map(([name, value], index) => ({
        name,
        type: "bar",
        stack: "total",
        barWidth: 18,
        data: [value],
        itemStyle: { color: COUNT_COLORS[index % COUNT_COLORS.length], borderRadius: index === countEntries.length - 1 ? [0, 6, 6, 0] : 0 },
      })),
    };
  }, [countEntries]);

  return (
    <ChartOrPlaceholder available={availability === "available" || availability === "partial"} reason="缺少融合统计，无法绘制质量图。">
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm"><span className="text-slate-500">有效多视角比例</span><strong className="mt-1 block text-[#14241B]">{ratio == null ? "-" : `${Math.round(ratio * 100)}%`}</strong></div>
        <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm"><span className="text-slate-500">指标可用样本</span><strong className="mt-1 block text-[#14241B]">{data.metric_eligible_count ?? "-"}</strong></div>
        <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm"><span className="text-slate-500">总样本</span><strong className="mt-1 block text-[#14241B]">{data.sample_count ?? "-"}</strong></div>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {ratioOption ? <EChart ariaLabel="有效多视角比例环形图" height={190} option={ratioOption} testId="fusion-ratio-chart" /> : null}
        {countsOption ? <EChart ariaLabel="融合状态分布堆叠条" height={190} option={countsOption} testId="fusion-counts-chart" /> : null}
      </div>
    </ChartOrPlaceholder>
  );
}

const FUNNEL_ORDER: Array<[keyof RecoveryFunnel, string]> = [
  ["recovery_opportunity_count", "恢复机会"],
  ["guidance_generated_count", "生成引导"],
  ["guided_recovery_success_count", "引导成功"],
  ["base_recovered_count", "基础自恢复"],
  ["guided_candidate_count", "候选"],
  ["guided_expected_global_preserved_count", "全局保持"],
];

/** 跨视角恢复：六段漏斗图（宽=计数/机会）+ 关键计数。 */
export function RecoveryFunnelChart({ funnel, availability, opportunityOverride }: { funnel: RecoveryFunnel | null | undefined; availability: ObservabilityAvailability; opportunityOverride?: number }) {
  const entries = useMemo(() => {
    if (!funnel) return [];
    const opportunity = opportunityOverride ?? Number(funnel.recovery_opportunity_count ?? 0);
    return FUNNEL_ORDER.map(([key, label], index) => {
      const value = Number(funnel[key] ?? 0);
      const prev = index === 0 ? opportunity : Number(funnel[FUNNEL_ORDER[index - 1][0]] ?? 0);
      return { key, label, value, conversion: prev > 0 ? value / prev : null };
    });
  }, [funnel, opportunityOverride]);

  const option = useMemo<EChartsCoreOption | null>(() => {
    if (entries.length === 0) return null;
    return {
      tooltip: {
        trigger: "item",
        formatter: (p: { data: { name: string; value: number; conversion: number | null } }) => {
          const conversion = p.data.conversion == null ? "" : ` · 转化率 ${Math.round(p.data.conversion * 100)}%`;
          return `${p.data.name}: ${p.data.value}${conversion}`;
        },
      },
      series: [
        {
          type: "funnel",
          left: "8%",
          top: 16,
          bottom: 8,
          width: "78%",
          minSize: "18%",
          sort: "none",
          gap: 4,
          label: { show: true, position: "inside", color: "#FFFFFF", fontWeight: 700, formatter: (p: { name: string; value: number }) => `${p.name} ${p.value}` },
          labelLine: { show: false },
          itemStyle: { borderColor: "#FFFFFF", borderWidth: 1 },
          emphasis: { label: { fontSize: 13 } },
          data: entries.map((entry, index) => ({
            name: entry.label,
            value: entry.value,
            conversion: entry.conversion,
            itemStyle: { color: index === entries.length - 1 ? VIZ_PALETTE.teal : index < 2 ? "#D3D1C7" : VIZ_PALETTE.green },
          })),
        },
      ],
    };
  }, [entries]);

  return (
    <ChartOrPlaceholder available={availability === "available" || availability === "partial"} reason="缺少恢复漏斗统计。">
      <div className="grid gap-2 sm:grid-cols-3">
        {[["恢复机会", entries[0]?.value ?? funnel?.recovery_opportunity_count ?? "-"], ["引导成功", funnel?.guided_recovery_success_count ?? "-"], ["基础自恢复", funnel?.base_recovered_count ?? "-"], ["全局保持", funnel?.guided_expected_global_preserved_count ?? "-"]].map(([label, value]) => (
          <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm" key={String(label)}><span className="text-slate-500">{label}</span><strong className="mt-1 block text-[#14241B]">{String(value)}</strong></div>
        ))}
      </div>
      {option ? <div className="mt-3"><EChart ariaLabel="跨视角恢复漏斗图" height={240} option={option} testId="recovery-funnel-chart" /></div> : null}
    </ChartOrPlaceholder>
  );
}

const EXECUTION_LABELS: Record<string, string> = {
  completed: "精修已完成",
  failed_fallback: "精修执行异常，已回退 F0",
  skipped_no_windows: "未执行（无可用窗口）",
  rejected_by_safety_gate: "精修完成，安全门拒绝发布",
};

const PUBLICATION_LABELS: Record<string, string> = {
  passed: "安全门通过，发布 F1",
  rejected_by_safety_gate: "发布被安全门拒绝",
  failed_fallback: "未发布（执行异常）",
  skipped_no_windows: "未发布（无可用窗口）",
};

/** 精修安全门：门控流程步骤条（当前状态高亮）。 */
export function RefinementGateChart({ data, availability }: { data: RefinementObservabilityData; availability: ObservabilityAvailability }) {
  const finalSource = data.final_source;
  const publishedF1 = finalSource === "refined_f1";
  const steps = [
    { label: "F0 首轮结果", state: "done" as const },
    { label: "精修执行", state: data.execution_status === "completed" || data.execution_status === "rejected_by_safety_gate" ? ("done" as const) : ("current" as const) },
    { label: "安全门", state: data.publication_decision === "rejected_by_safety_gate" ? ("failed" as const) : data.publication_decision === "passed" ? ("done" as const) : ("pending" as const) },
    { label: publishedF1 ? "发布 F1" : "保留 F0", state: publishedF1 ? ("done" as const) : ("current" as const) },
  ];
  const stepTone = { done: VIZ_PALETTE.green, current: VIZ_PALETTE.blue, failed: VIZ_PALETTE.red, pending: "#B4B2A9" };

  return (
    <ChartOrPlaceholder available={availability === "available" || availability === "partial"} reason="缺少精修门控事实。">
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm"><span className="text-slate-500">精修执行</span><strong className="mt-1 block text-[#14241B]">{EXECUTION_LABELS[String(data.execution_status ?? "")] ?? data.execution_status ?? "-"}</strong></div>
        <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm"><span className="text-slate-500">发布决策</span><strong className="mt-1 block text-[#14241B]">{PUBLICATION_LABELS[String(data.publication_decision ?? "")] ?? data.publication_decision ?? "-"}</strong></div>
      </div>
      <div className="mt-4 flex items-center gap-1" data-testid="refinement-gate-steps">
        {steps.map((step, index) => (
          <div className="flex min-w-0 flex-1 items-center gap-1" key={step.label}>
            <div className="flex min-w-0 flex-col items-center gap-1">
              <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: stepTone[step.state] }} aria-hidden="true" />
              <span className="truncate text-xs font-bold text-slate-600">{step.label}</span>
            </div>
            {index < steps.length - 1 ? <div className="mx-1 mb-4 h-0.5 flex-1" style={{ backgroundColor: steps[index + 1].state === "pending" ? "#E7EFE2" : VIZ_PALETTE.green }} aria-hidden="true" /> : null}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs font-semibold text-[#14241B]">最终产品来源：<strong>{publishedF1 ? "F1" : data.final_source === "first_pass_f0" ? "F0" : String(data.final_source ?? "-")}</strong></p>
      {data.safety_gate?.reason ? <p className="mt-2 rounded-xl border border-[#F6D79A] bg-[#FFF9ED] px-3 py-2 text-sm leading-6 text-[#8B5A17]">安全门说明：{data.safety_gate.reason}</p> : null}
    </ChartOrPlaceholder>
  );
}

export { STAGE_LABELS };
