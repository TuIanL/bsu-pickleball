import type { AnalysisJobSummary, AnalysisUploadMetadata } from "../../types/report";
import type { PreparedModuleSources } from "../../types/analysisModules";
import { capabilityNames, moduleDraftReturn, type AnalysisCreationMode } from "../../services/analysisModeConfig";
import { useModularAnalysisCreation } from "../../hooks/useModularAnalysisCreation";
import { AnalysisPlanPreview } from "./AnalysisPlanPreview";

export function ModularAnalysisCreator(props: {
  mode: AnalysisCreationMode; sourceKey: string; prepare: () => Promise<PreparedModuleSources>;
  metadata: AnalysisUploadMetadata; onCreated: (job: AnalysisJobSummary, sources: PreparedModuleSources) => void;
  onOpenSync?: (returnPath: string) => void; sourceReady?: boolean;
}) {
  const flow = useModularAnalysisCreation(props);
  const { draft, updateDraft, prepared, busy } = flow;
  const duration = prepared?.sources.find((s) => s.view_id === prepared.reference_view_id)?.duration_ms;
  const phaseLabels: Record<string, string> = { preparing: "正在准备视频时间信息和模型环境…", previewing: "正在预览执行计划…", submitting: "正在创建分析任务…", history: "正在核对任务历史…" };
  return <section className="sport-card p-5" aria-label="专项分析配置">
    <h2 className="text-xl font-bold">专项分析配置</h2>
    <p className="mt-2 text-sm leading-6 text-slate-500">无需场地标定或球员名册。先准备视频与模型，再预览这次实际执行的步骤。</p>
    {!flow.catalog && !flow.catalogError ? <p role="status">正在读取可用能力…</p> : null}
    {flow.catalogError ? <div role="alert"><p>{flow.catalogError}</p><button className="quiet-button" onClick={flow.reloadCatalog} type="button">重试读取能力</button></div> : null}
    {flow.catalog && !flow.catalog.enabled ? <p role="alert">当前服务已关闭专项分析创建，可切回完整比赛分析。</p> : null}
    <fieldset disabled={busy || flow.uncertain} className="mt-4 space-y-4">
      {props.mode === "custom" ? <div className="flex flex-wrap gap-4" role="group" aria-label="选择专项能力">{Object.entries(capabilityNames).map(([id, name]) => {
        const available = flow.catalog?.capabilities.some((c) => c.capability_id === id && c.status === "implemented");
        return <label key={id} className="text-sm"><input type="checkbox" checked={draft.targets.includes(id)} disabled={!available} onChange={(event) => updateDraft({ targets: event.target.checked ? [...draft.targets, id] : draft.targets.filter((target) => target !== id) })} /> {name}{!available ? "（当前不可用）" : ""}</label>;
      })}</div> : null}
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm">开始时间（秒）<input className="field-input mt-1" type="number" min="0" step="0.001" value={Number.isFinite(draft.start) ? draft.start : ""} onChange={(e) => updateDraft({ start: e.target.value === "" ? NaN : Number(e.target.value) })} /></label>
        <label className="text-sm">结束时间（秒）<input className="field-input mt-1" type="number" min="0" step="0.001" value={draft.end === null ? (duration ? Math.min(30, duration / 1000) : "") : Number.isFinite(draft.end) ? draft.end : ""} placeholder="默认前 30 秒" onChange={(e) => updateDraft({ end: e.target.value === "" ? NaN : Number(e.target.value) })} /></label>
        <label className="text-sm">每几帧采样一次<input className="field-input mt-1" type="number" min="1" step="1" value={draft.stride} onChange={(e) => updateDraft({ stride: Number(e.target.value) })} /></label>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm"><button className="quiet-button" type="button" disabled={!duration} onClick={() => updateDraft({ start: 0, end: duration! / 1000 })}>整个视频</button>{duration ? <span>参考视频时长 {(duration / 1000).toFixed(3)} 秒</span> : null}</div>
      <details><summary className="text-sm font-semibold">高级设置</summary><div className="mt-3 space-y-3 text-sm">
        <label className="block">完成条件<select className="field-input mt-1" value={draft.failurePolicy} onChange={(e) => updateDraft({ failurePolicy: e.target.value as typeof draft.failurePolicy })}><option value="all_targets">所有目标完成</option><option value="best_effort">尽可能保留成功目标（可能只有部分结果）</option></select></label>
        <label className="block"><input type="checkbox" checked={draft.newVersion} onChange={(e) => updateDraft({ newVersion: e.target.checked })} /> 创建新分析版本（仍可能复用有效计算结果）</label>
      </div></details>
    </fieldset>
    {flow.validation ? <p role="alert" className="mt-3 text-sm text-red-700">{flow.validation}</p> : null}
    {flow.error ? <p role="alert" className="mt-3 text-sm text-red-700">{flow.error}</p> : null}
    {prepared && !flow.targetsAvailable && !flow.validation ? <p role="alert" className="mt-3 text-sm">所选目标当前不可用，请检查能力目录或切换模式。</p> : null}
    {busy ? <p role="status" className="mt-3 text-sm">{phaseLabels[flow.phase]}</p> : null}
    <div className="mt-4 flex flex-wrap gap-3">
      <button type="button" className="quiet-button" disabled={busy || flow.uncertain || !flow.catalog?.enabled || props.sourceReady === false} onClick={() => void flow.prepareInputs()}>{prepared ? "重新准备视频与模型" : "准备视频与模型"}</button>
      <button type="button" className="quiet-button" disabled={busy || flow.uncertain || !flow.targetsAvailable || Boolean(flow.validation)} onClick={() => void flow.previewPlan()}>预览执行计划</button>
      <button type="button" className="green-button" disabled={busy || flow.uncertain || !flow.plan || !flow.catalog?.enabled} onClick={() => void flow.submit()}>创建专项分析</button>
    </div>
    {props.sourceReady === false ? <p className="mt-2 text-sm">请先选择可用视频。</p> : null}
    {props.onOpenSync ? <button className="quiet-button mt-3" type="button" disabled={busy} onClick={() => props.onOpenSync!(moduleDraftReturn(props.mode, draft))}>打开同步工作台</button> : null}
    {flow.plan ? <AnalysisPlanPreview plan={flow.plan} /> : null}
    {flow.uncertain ? <div className="mt-4"><button className="quiet-button" type="button" disabled={busy} onClick={() => void flow.checkHistory()}>核对任务历史</button><p className="mt-2 text-sm">核对同一计划的任务时间，确认已创建任务后可直接打开。</p>{flow.history.map((job) => <button className="quiet-button mt-2 block" type="button" key={job.id} onClick={() => flow.openHistoryJob(job)}>{job.id} · {job.createdAt} · 打开任务</button>)}</div> : null}
  </section>;
}
