import type { ModulePlan } from "../../types/analysisModules";
import { capabilityName } from "../../services/analysisModeConfig";

export function AnalysisPlanPreview({ plan }: { plan: ModulePlan }) {
  return <section className="mt-4 rounded-2xl border border-[var(--ui-border)] p-4" aria-label="执行计划预览">
    <h3 className="font-bold">本次执行计划</h3>
    <p className="mt-2 text-sm">片段 {plan.requested_window.start_ms / 1000}–{plan.requested_window.end_ms / 1000} 秒 · 每 {plan.sampling.stride} 帧采样 · {plan.failure_policy === "all_targets" ? "全部目标完成" : "允许部分目标完成"}</p>
    <ul className="my-3 space-y-2">{plan.nodes.map((node) => <li key={node.node_key} className="rounded-lg bg-[var(--ui-surface-soft)] p-3 text-sm">
      <strong>{capabilityName(node.capability_id)}</strong> · {plan.targets.includes(node.capability_id) ? "所选目标" : "自动加入的依赖"}
      <p className="mt-1 text-xs text-slate-500">有效片段 {node.effective_window.start_ms / 1000}–{node.effective_window.end_ms / 1000} 秒{node.truncated ? " · 边界已截断" : ""}</p>
    </li>)}</ul>
    <p className="text-xs text-slate-500">缓存提示为预估，实际复用情况将在执行后显示。</p>
    <details className="mt-3 text-xs"><summary>计划技术详情与缓存提示</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify({ nodes: plan.nodes, cache: plan.cache_hints, plan_hash: plan.plan_hash }, null, 2)}</pre></details>
  </section>;
}
