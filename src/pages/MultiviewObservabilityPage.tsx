import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, Film, RefreshCw, SlidersHorizontal } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { taskContextForJob, taskListPathForJob, withTaskListContext } from "../app/navigationContext";
import { PageFrame } from "../components/PageFrame";
import { StatusState } from "../components/StatusState";
import { getAnalysisJob, getMultiviewDebugVideoUrl, getMultiviewObservability, getMultiviewRecoveryEpisodes } from "../services/analysisClient";
import { isAnalysisApiError } from "../services/analysisClient";
import type { AnalysisJobSummary } from "../types/report";
import type {
  DebugObservabilityData,
  FusionObservabilityData,
  MultiviewObservabilitySummary,
  ObservabilityAvailability,
  ObservabilitySection,
  RecoveryEpisode,
  RecoveryObservabilityData,
  RecoveryOutcome,
  RefinementObservabilityData,
  SyncObservabilityData,
} from "../types/multiviewObservability";

const outcomeLabels: Record<RecoveryOutcome, string> = {
  guided_recovery_success: "引导恢复成功",
  base_recovered: "基础观测自恢复",
  guidance_failed: "引导未成功",
  pre_gate_rejected: "前置门拒绝",
  lock_rejected: "锁定拒绝",
  global_mismatch: "全局身份不匹配",
};

const availabilityLabels: Record<ObservabilityAvailability, string> = {
  available: "可用",
  partial: "部分可用",
  unavailable: "不可用",
  not_applicable: "不适用",
};

function sectionTone(section: ObservabilitySection) {
  if (section.availability === "available") return "border-[#B7E7C2] bg-[#F1FBF3] text-[#16733A]";
  if (section.availability === "partial") return "border-[#F6D79A] bg-[#FFF9ED] text-[#A45A00]";
  if (section.availability === "not_applicable") return "border-[#DDE9D6] bg-[#F5FAF1] text-slate-500";
  return "border-[#F2C2C2] bg-[#FFF5F5] text-[#A32D2D]";
}

function formatMs(value?: number | null) {
  if (value == null) return "-";
  return `${Math.round(value)} ms`;
}

const refinementExecutionLabels: Record<string, string> = {
  completed: "精修已完成",
  failed_fallback: "精修执行异常，已回退 F0",
  skipped_no_windows: "未执行（无可用窗口）",
};

const refinementPublicationLabels: Record<string, string> = {
  passed: "安全门通过，发布 F1",
  rejected_by_safety_gate: "发布被安全门拒绝",
  failed_fallback: "未发布（执行异常）",
  skipped_no_windows: "未发布（无可用窗口）",
};

function SectionBadge({ section }: { section: ObservabilitySection }) {
  return <span className={`inline-flex shrink-0 rounded-full border px-2.5 py-1 text-xs font-bold ${sectionTone(section)}`}>{availabilityLabels[section.availability]}</span>;
}

function MetricRow({ label, value }: { label: string; value: unknown }) {
  const display = value == null || value === "" ? "-" : typeof value === "boolean" ? (value ? "是" : "否") : String(value);
  return <div className="flex min-w-0 items-start justify-between gap-4 rounded-xl bg-[#F7FBF5] px-3 py-2.5 text-sm"><span className="text-slate-500">{label}</span><strong className="max-w-[65%] break-words text-right text-[#14241B]">{display}</strong></div>;
}

function Panel({ title, eyebrow, section, children, testId }: { title: string; eyebrow: string; section: ObservabilitySection; children: ReactNode; testId?: string }) {
  return <section className="sport-card p-5 sm:p-6" data-testid={testId}>
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-[0.68rem] font-black uppercase tracking-[0.16em] text-[#168A34]">{eyebrow}</p><h2 className="mt-1 text-xl font-black text-[#14241B]">{title}</h2></div><SectionBadge section={section} /></div>
    <div className="mt-4">{children}</div>
    {section.reason_code ? <p className="mt-4 rounded-xl border border-[#F2E2BD] bg-[#FFF9ED] px-3 py-2 text-xs leading-5 text-[#8B5A17]">诊断说明：{section.reason_code}</p> : null}
  </section>;
}

function JointRunStatusHeader({ summary }: { summary: MultiviewObservabilitySummary }) {
  const sections = summary.sections;
  const rows = [["SYNC", sections.sync], ["FUSION", sections.fusion], ["RECOVERY", sections.recovery], ["REFINEMENT", sections.refinement]] as const;
  return <section className="sport-card overflow-hidden" data-testid="joint-run-status-header"><div className="border-b border-[#DDE9D6] bg-[#F5FAF1] p-6 sm:p-7"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-[0.18em] text-[#168A34]">双摄协同分析</p><h1 className="mt-2 text-3xl font-black text-[#14241B] sm:text-4xl">联合运行状态</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">后端已发布的同步、融合、恢复和精修事实分域展示。页面不重新计算算法结论。</p></div><div className="text-right text-xs font-semibold text-slate-500"><div>执行模式</div><strong className="mt-1 block text-sm text-[#14241B]">{summary.execution_mode ?? "-"}</strong></div></div></div><div className="grid gap-px bg-[#DDE9D6] sm:grid-cols-4">{rows.map(([label, section]) => <div className="bg-white p-4" key={label}><div className="flex items-center justify-between gap-2"><span className="text-xs font-black tracking-[0.14em] text-slate-500">{label}</span><SectionBadge section={section} /></div><p className="mt-3 break-words text-sm font-bold text-[#14241B]">{section.status}</p></div>)}</div></section>;
}

function SyncAuthorityPanel({ section }: { section: ObservabilitySection<SyncObservabilityData> }) {
  const data = section.data ?? {};
  const authority = data.per_view_authority as Record<string, string> | null | undefined;
  return <Panel title="同步权威" eyebrow="SYNC AUTHORITY" section={section} testId="sync-authority-panel"><div className="grid gap-2 sm:grid-cols-2"><MetricRow label="同步质量" value={data.sync_quality} /><MetricRow label="执行模式" value={data.execution_mode} /><MetricRow label="权威联合分析" value={data.authoritative_joint_eligible} /><MetricRow label="参考机位" value={data.reference_view} /></div>{authority ? <div className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(authority).map(([view, value]) => <MetricRow key={view} label={`${view} authority`} value={value} />)}</div> : null}{data.authority_reason ? <p className="mt-3 text-sm leading-6 text-slate-600">{data.authority_reason}</p> : null}</Panel>;
}

function FusionQualityPanel({ section }: { section: ObservabilitySection<FusionObservabilityData> }) {
  const data = section.data ?? {};
  const counts = data.status_counts as Record<string, number> | null | undefined;
  return <Panel title="融合质量" eyebrow="FUSION QUALITY" section={section} testId="fusion-quality-panel"><div className="grid gap-2 sm:grid-cols-2"><MetricRow label="指标可用样本" value={data.metric_eligible_count} /><MetricRow label="总样本" value={data.sample_count} /><MetricRow label="有效多视角比例" value={data.effective_multiview_ratio == null ? null : `${Math.round(data.effective_multiview_ratio * 100)}%`} /><MetricRow label="视角差异中位数" value={(data.view_disagreement as { median_distance_ft?: number | null } | null)?.median_distance_ft == null ? null : `${(data.view_disagreement as { median_distance_ft: number }).median_distance_ft.toFixed(2)} ft`} /></div>{counts ? <div className="mt-3 flex flex-wrap gap-2">{Object.entries(counts).map(([key, value]) => <span className="rounded-full border border-[#DDE9D6] bg-[#F5FAF1] px-3 py-1.5 text-xs font-bold text-slate-600" key={key}>{key}: {value}</span>)}</div> : null}<p className="mt-3 text-xs leading-5 text-slate-500">融合参与度与同步权威是两个独立事实域。</p></Panel>;
}

function RecoveryPanel({ jobId, section, canSeek, onSeek }: { jobId: string; section: ObservabilitySection<RecoveryObservabilityData>; canSeek: boolean; onSeek: (episode: RecoveryEpisode) => void }) {
  const data = section.data ?? {};
  const [outcome, setOutcome] = useState<RecoveryOutcome | "">("");
  const [targetView, setTargetView] = useState("");
  const [page, setPage] = useState<{ items: RecoveryEpisode[]; next_cursor?: string | null; total_estimate: number; availability?: ObservabilityAvailability; reason?: { code: string; message: string } } | null>(null);
  const [loading, setLoading] = useState(section.availability !== "not_applicable");
  const [expanded, setExpanded] = useState<string | null>(null);
  const fetchPage = useCallback(
    (cursor?: string | null) => getMultiviewRecoveryEpisodes(jobId, { cursor, limit: 8, outcome, target_view: targetView || undefined }),
    [jobId, outcome, targetView],
  );
  const load = useCallback((cursor?: string | null) => {
    setLoading(true);
    void fetchPage(cursor)
      .then(setPage)
      .catch(() => setPage({ items: [], total_estimate: 0, availability: "unavailable" }))
      .finally(() => setLoading(false));
  }, [fetchPage]);
  useEffect(() => {
    if (section.availability === "not_applicable") return;
    let alive = true;
    void fetchPage()
      .then((nextPage) => { if (alive) setPage(nextPage); })
      .catch(() => { if (alive) setPage({ items: [], total_estimate: 0, availability: "unavailable" }); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [fetchPage, section.availability]);
  const funnel = data.funnel;
  return <Panel title="跨视角恢复" eyebrow="RECOVERY" section={section} testId="recovery-panel"><div className="grid gap-2 sm:grid-cols-3">{[["机会", funnel?.recovery_opportunity_count], ["引导", funnel?.guidance_generated_count], ["引导成功", funnel?.guided_recovery_success_count], ["基础自恢复", funnel?.base_recovered_count], ["候选", funnel?.guided_candidate_count], ["全局保持", funnel?.guided_expected_global_preserved_count]].map(([label, value]) => <MetricRow key={String(label)} label={String(label)} value={value} />)}</div><div className="mt-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto]"><label className="text-xs font-bold text-slate-500">结果<select aria-label="恢复结果" className="field-input mt-1 py-2" value={outcome} onChange={(event) => setOutcome(event.target.value as RecoveryOutcome | "")}><option value="">全部</option>{Object.entries(outcomeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-xs font-bold text-slate-500">目标视角<select aria-label="目标视角" className="field-input mt-1 py-2" value={targetView} onChange={(event) => setTargetView(event.target.value)}><option value="">全部</option><option value="cam_1">cam_1</option><option value="cam_2">cam_2</option></select></label><button className="quiet-button self-end px-3 py-2" onClick={() => load()} type="button" title="刷新恢复 episodes"><RefreshCw size={15} aria-hidden="true" />刷新</button></div><div className="mt-4 overflow-hidden rounded-2xl border border-[#DDE9D6]"><div className="flex items-center justify-between bg-[#F5FAF1] px-3 py-2 text-xs font-bold text-slate-500"><span>{page?.total_estimate ?? 0} 个 episode</span><span>{loading ? "读取中…" : page?.availability === "partial" ? "证据部分可用" : ""}</span></div>{page?.items.length ? page.items.map((episode) => <div className="border-t border-[#DDE9D6] bg-white" key={episode.recovery_episode_id}><button className="flex w-full items-start gap-2 px-3 py-3 text-left" onClick={() => setExpanded(expanded === episode.recovery_episode_id ? null : episode.recovery_episode_id)} type="button"><span className="mt-0.5 text-[#168A34]">{expanded === episode.recovery_episode_id ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}</span><span className="min-w-0 flex-1"><strong className="block break-words text-sm text-[#14241B]">{outcomeLabels[episode.outcome] ?? episode.outcome}</strong><span className="mt-1 block text-xs text-slate-500">{episode.global_player_id ?? "-"} · {episode.donor_view ?? "-"} → {episode.target_view ?? "-"} · {formatMs(episode.start_ms)} - {formatMs(episode.end_ms)}</span></span><span className="shrink-0 text-xs font-bold text-slate-500">{episode.guidance_attempts} 次引导</span></button>{expanded === episode.recovery_episode_id ? <div className="grid gap-2 border-t border-[#EEF2EA] bg-[#FBFDF9] p-3 sm:grid-cols-2"><MetricRow label="前置门拒绝" value={episode.pre_gate_rejections} /><MetricRow label="锁定拒绝" value={episode.lock_rejections} /><MetricRow label="视频定位" value={formatMs(episode.debug_video_seek_ms)} /><button className="quiet-button px-3 py-2 text-xs sm:col-span-2" onClick={() => onSeek(episode)} type="button" disabled={!canSeek || episode.debug_video_seek_ms == null}>定位到 Debug Replay</button></div> : null}</div>) : <div className="p-5 text-sm leading-6 text-slate-500">{page?.reason?.message ?? (section.availability === "not_applicable" ? "当前执行模式不适用在线恢复。" : "当前没有可分页的 recovery episode 证据。")}</div>}</div>{page?.next_cursor ? <button className="quiet-button mt-3 px-3 py-2 text-xs" onClick={() => load(page.next_cursor)} type="button">加载下一页</button> : null}</Panel>;
}

function DebugReplayPanel({ jobId, section, selectedSeek }: { jobId: string; section: ObservabilitySection<DebugObservabilityData>; selectedSeek: number | null }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [enabled, setEnabled] = useState(false);
  useEffect(() => { if (enabled && selectedSeek != null && videoRef.current) { videoRef.current.currentTime = selectedSeek / 1000; videoRef.current.focus(); } }, [enabled, selectedSeek]);
  const data = section.data ?? {};
  const debugTraceDisabled = data.debug_trace_enabled === false || section.reason_code === "debug_trace_disabled";
  return <Panel title="Debug Replay" eyebrow="DEBUG REPLAY" section={section} testId="debug-replay-panel">{section.availability === "available" && data.video_available ? <><button className="green-button px-3 py-2" onClick={() => setEnabled(true)} type="button"><Film size={16} aria-hidden="true" />加载 canonical MP4</button>{enabled ? <video className="mt-4 aspect-video w-full rounded-2xl bg-[#101828]" controls preload="metadata" ref={videoRef} src={getMultiviewDebugVideoUrl(jobId)} /> : <p className="mt-3 text-sm text-slate-500">视频按需加载。选择 episode 后会使用后端提供的定位时间。</p>}</> : <div className="rounded-2xl border border-dashed border-[#DDE9D6] bg-[#F7FBF5] p-5 text-sm leading-6 text-slate-600">{debugTraceDisabled ? "本任务未开启详细诊断回放，正式诊断区域仍可正常使用。" : "canonical debug MP4 尚未生成。"}</div>}</Panel>;
}

function RefinementSafetyPanel({ section }: { section: ObservabilitySection<RefinementObservabilityData> }) {
  const data = section.data ?? {};
  const candidate = data.candidate_f1;
  return <Panel title="精修与安全门" eyebrow="REFINEMENT SAFETY" section={section} testId="refinement-safety-panel"><div className="grid gap-2 sm:grid-cols-2"><MetricRow label="精修执行" value={refinementExecutionLabels[String(data.execution_status)] ?? data.execution_status} /><MetricRow label="Candidate F1" value={candidate ? (candidate.available ? "已生成" : "未生成") : null} /><MetricRow label="发布决策" value={refinementPublicationLabels[String(data.publication_decision)] ?? data.publication_decision} /><MetricRow label="最终产品来源" value={data.final_source === "refined_f1" ? "F1" : data.final_source === "first_pass_f0" ? "F0" : data.final_source} /></div>{data.safety_gate?.reason ? <p className="mt-3 rounded-xl border border-[#F6D79A] bg-[#FFF9ED] px-3 py-2 text-sm leading-6 text-[#8B5A17]">安全门说明：{data.safety_gate.reason}</p> : null}</Panel>;
}

export function MultiviewObservabilityPage({ jobId, onNavigate }: { jobId: string; onNavigate: NavigateFn }) {
  const [job, setJob] = useState<AnalysisJobSummary | null | undefined>(undefined);
  const [summary, setSummary] = useState<MultiviewObservabilitySummary | null | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [selectedSeek, setSelectedSeek] = useState<number | null>(null);
  useEffect(() => { let alive = true; Promise.all([getAnalysisJob(jobId), getMultiviewObservability(jobId)]).then(([nextJob, nextSummary]) => { if (!alive) return; setJob(nextJob); setSummary(nextSummary); }).catch((reason) => { if (alive) setError(reason); }); return () => { alive = false; }; }, [jobId]);
  if (error) return <StatusState title="读取双摄协同详情失败" body={isAnalysisApiError(error) ? error.message : "无法读取后端 observability summary。"} onNavigate={onNavigate} backPath="/analysis/tasks" />;
  if (job === undefined || summary === undefined) return <StatusState title="正在读取双摄协同详情" body="正在加载后端发布的同步、融合、恢复与精修状态。" onNavigate={onNavigate} backPath="/analysis/tasks" />;
  const returnPath = taskListPathForJob(job);
  if (!job) return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在。`} onNavigate={onNavigate} backPath={returnPath} />;
  if (!summary) return <StatusState title="该任务不适用双摄协同详情" body="当前任务不是 multiview 分析，可返回任务页查看通用结果。" onNavigate={onNavigate} backPath={returnPath} />;
  const contextualPath = (path: string) => withTaskListContext(path, taskContextForJob(job));
  return <PageFrame><div className="mb-5 flex flex-wrap items-center justify-between gap-3"><button className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 hover:text-[#168A34]" onClick={() => onNavigate(returnPath)} type="button"><ArrowLeft size={16} aria-hidden="true" />返回任务管理</button><button className="quiet-button px-3 py-2 text-sm" onClick={() => onNavigate(contextualPath(`/analysis/${job.id}`))} type="button">返回任务详情</button></div><JointRunStatusHeader summary={summary} /><div className="mt-6 grid gap-6 xl:grid-cols-2"><SyncAuthorityPanel section={summary.sections.sync} /><FusionQualityPanel section={summary.sections.fusion} /><RecoveryPanel jobId={jobId} section={summary.sections.recovery} canSeek={summary.sections.debug.availability === "available" && Boolean(summary.sections.debug.data?.video_available)} onSeek={(episode) => setSelectedSeek(episode.debug_video_seek_ms ?? null)} /><DebugReplayPanel jobId={jobId} section={summary.sections.debug} selectedSeek={selectedSeek} /><RefinementSafetyPanel section={summary.sections.refinement} /><section className="sport-card p-5 sm:p-6"><details><summary className="flex cursor-pointer items-center gap-2 text-sm font-bold text-[#14241B]"><SlidersHorizontal size={16} aria-hidden="true" />技术运行详情</summary><div className="mt-4 grid gap-2 text-sm"><MetricRow label="任务 ID" value={summary.job_id} /><MetricRow label="run ID" value={summary.run_id} /><MetricRow label="请求模式" value={summary.requested_mode} /><MetricRow label="有效模式" value={summary.effective_mode} /><MetricRow label="DEBUG" value={summary.sections.debug.status} /></div></details></section></div></PageFrame>;
}
