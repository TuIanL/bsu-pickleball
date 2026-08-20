import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleHelp, Gauge, MinusCircle, Target, Video } from "lucide-react";
import type { NavigateFn } from "../../app/navigationTypes";
import type {
  DimensionStatus,
  FindingAssessment,
  ReportPerformanceInsights,
} from "../../types/report";
import { withTaskListContext } from "../../app/navigationContext";
import type { AnalysisJobSummary } from "../../types/report";
import { taskContextForJob } from "../../app/navigationContext";

const dimensionStatusLabel: Record<DimensionStatus, string> = {
  strength: "优势",
  stable: "稳定",
  needs_improvement: "待改进",
  insufficient_evidence: "数据有限",
  not_applicable: "不适用",
  unsupported: "暂不评价",
};

const dimensionStatusClass: Record<DimensionStatus, string> = {
  strength: "border-[#22C55E]/40 bg-[#22C55E]/10 text-[#15803D]",
  stable: "border-[#22C55E]/30 bg-white text-slate-700",
  needs_improvement: "border-[#FF9500]/40 bg-[#FF9500]/10 text-[#B45309]",
  insufficient_evidence: "border-slate-200 bg-slate-50 text-slate-500",
  not_applicable: "border-slate-200 bg-slate-50 text-slate-400",
  unsupported: "border-slate-200 bg-slate-50 text-slate-400",
};

const assessmentLabel: Record<FindingAssessment, string> = {
  strength: "优势",
  stable: "稳定",
  needs_improvement: "待改进",
  insufficient_evidence: "数据有限",
};

const assessmentClass: Record<FindingAssessment, string> = {
  strength: "bg-[#22C55E]/15 text-[#15803D]",
  stable: "bg-[#22C55E]/10 text-[#166534]",
  needs_improvement: "bg-[#FF9500]/15 text-[#B45309]",
  insufficient_evidence: "bg-slate-100 text-slate-500",
};

const priorityLabel: Record<number, string> = { 1: "优先级 1", 2: "优先级 2", 3: "优先级 3" };

const confidenceLabel: Record<string, string> = { high: "高置信", medium: "中置信", low: "低置信" };

function formatMs(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Performance Insights 面板（报告 performance 类型主体）。
 *
 * 只做展示投影：维度状态直接取 DimensionAssessment（Rule Engine 权威输出），
 * 本组件不推导任何维度结论；数值技能分 / 历史趋势不渲染（schema 亦不携带）。
 */
export function PerformanceInsightsPanel({
  insights,
  jobId,
  job,
  onNavigate,
}: {
  insights: ReportPerformanceInsights;
  jobId?: string;
  job?: AnalysisJobSummary | null;
  onNavigate: NavigateFn;
}) {
  const playerSubjects = insights.subjects.filter((subject) => subject.kind === "player");
  const [selectedSubject, setSelectedSubject] = useState<string>(playerSubjects[0]?.id ?? "match");

  const subjectDimensions = useMemo(
    () => insights.dimensions.filter((dimension) => dimension.subject_id === selectedSubject),
    [insights.dimensions, selectedSubject]
  );
  const subjectFindings = useMemo(
    () =>
      insights.findings
        .filter((finding) => finding.subject_id === selectedSubject)
        .sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id)),
    [insights.findings, selectedSubject]
  );
  const subjectRecommendations = useMemo(
    () => insights.recommendations.filter((recommendation) => recommendation.subject_id === selectedSubject),
    [insights.recommendations, selectedSubject]
  );

  if (insights.status === "unavailable") {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
        <div className="flex items-center gap-3">
          <CircleHelp className="text-slate-400" size={22} aria-hidden="true" />
          <h3 className="text-base font-bold text-slate-700">洞察暂不可用</h3>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          {insights.unavailable_reason ?? "本次任务未能生成表现洞察。"}
          报告仍展示真实的移动数据；洞察生成恢复后不会影响已产出的移动指标。
        </p>
      </div>
    );
  }

  // 首屏总结 = 全场视角（primary focus 是全场首要问题）；维度/findings/建议按所选视角过滤。
  const primaryFocus = insights.findings.find((finding) => finding.id === insights.primary_focus_finding_id)
    ?? insights.findings.find((finding) => finding.assessment === "needs_improvement");
  const strengthFinding = insights.findings.find(
    (finding) => finding.assessment === "strength" || finding.assessment === "stable",
  );
  const nextTraining = subjectRecommendations[0];

  return (
    <div className="flex flex-col gap-6">
      {/* ── 首屏总结 ── */}
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          icon={<Gauge size={18} aria-hidden="true" />}
          label="本场表现"
          value={subjectDimensions.some((dimension) => dimension.status === "needs_improvement") ? "有待改进" : "整体稳定"}
          detail={insights.data_quality_summary ?? undefined}
        />
        <SummaryCard
          icon={<CheckCircle2 size={18} aria-hidden="true" />}
          label="最明显优势"
          value={strengthFinding ? strengthFinding.title : "见维度状态"}
          detail={strengthFinding?.dimension_label}
        />
        <SummaryCard
          icon={<AlertTriangle size={18} aria-hidden="true" />}
          label="首要问题"
          value={primaryFocus ? primaryFocus.title : "暂无高优先级问题"}
          detail={primaryFocus ? priorityLabel[primaryFocus.priority] : undefined}
        />
        <SummaryCard
          icon={<Target size={18} aria-hidden="true" />}
          label="下一次最值得练"
          value={nextTraining ? nextTraining.title : "暂无具体建议"}
          detail={nextTraining?.next_target}
        />
      </section>

      {/* ── 球员切换 ── */}
      {insights.subjects.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">切换视角</span>
          {insights.subjects.map((subject) => (
            <button
              className={`rounded-full border px-3.5 py-1.5 text-xs font-bold transition ${
                selectedSubject === subject.id
                  ? "border-[#168A34] bg-[#22C55E]/15 text-[#15803D]"
                  : "border-slate-200 bg-white text-slate-600 hover:border-[#22C55E]/50"
              }`}
              key={subject.id}
              onClick={() => setSelectedSubject(subject.id)}
              type="button"
            >
              {subject.label}
            </button>
          ))}
        </div>
      ) : null}

      {/* ── 六维状态卡（无数值分）── */}
      <section>
        <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.16em] text-slate-400">六维表现</h3>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {subjectDimensions.map((dimension) => (
            <div
              className={`rounded-2xl border p-4 ${dimensionStatusClass[dimension.status]}`}
              key={`${dimension.subject_id}-${dimension.dimension}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-bold">{dimension.label}</span>
                <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-black">
                  {dimensionStatusLabel[dimension.status]}
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-600">{dimension.summary}</p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-slate-400">
          维度只输出状态与证据充分度，不提供未经校准的数值评分。
        </p>
      </section>

      {/* ── 关键 Findings ── */}
      <section>
        <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.16em] text-slate-400">关键发现</h3>
        <div className="flex flex-col gap-3">
          {subjectFindings.length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
              当前视角暂无具体发现。
            </p>
          ) : (
            subjectFindings.map((finding) => (
              <article className="rounded-2xl border border-slate-200 bg-white p-5" key={finding.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-black ${assessmentClass[finding.assessment]}`}>
                    {assessmentLabel[finding.assessment]}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-bold text-slate-500">
                    {finding.dimension_label}
                  </span>
                  <span className="text-[11px] font-semibold text-slate-400">
                    {priorityLabel[finding.priority]} · {confidenceLabel[finding.confidence]}
                  </span>
                </div>
                <h4 className="mt-2.5 text-base font-bold text-[#14241B]">{finding.title}</h4>
                <p className="mt-1.5 text-sm leading-6 text-slate-600">{finding.diagnosis}</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">{finding.impact}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold text-slate-400">
                    证据 {finding.evidence_ids.length} 条
                  </span>
                  {finding.evidence_windows.length > 0 && jobId ? (
                    finding.evidence_windows.slice(0, 3).map((window, index) => (
                      <button
                        className="inline-flex items-center gap-1.5 rounded-full border border-[#2F80ED]/40 bg-[#2F80ED]/10 px-3 py-1 text-[11px] font-bold text-[#1D4ED8] transition hover:bg-[#2F80ED]/20"
                        key={`${finding.id}-window-${index}`}
                        onClick={() =>
                          onNavigate(
                            withTaskListContext(
                              `/analysis/${jobId}/vision?t=${window.start_ms}`,
                              taskContextForJob(job ?? null),
                            ),
                          )
                        }
                        type="button"
                      >
                        <Video size={12} aria-hidden="true" />
                        查看视频证据 {formatMs(window.start_ms)} - {formatMs(window.end_ms)}
                      </button>
                    ))
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold text-slate-400">
                      <MinusCircle size={12} aria-hidden="true" />
                      无时间窗证据
                    </span>
                  )}
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      {/* ── 算法候选事实（独立区，不进入 findings）── */}
      {insights.candidate_facts.length > 0 ? (
        <section className="rounded-2xl border border-dashed border-[#2F80ED]/40 bg-[#2F80ED]/5 p-5">
          <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-[#1D4ED8]">算法候选事实</h3>
          <ul className="mt-3 flex flex-col gap-1.5">
            {insights.candidate_facts.map((fact) => (
              <li className="text-sm leading-6 text-slate-600" key={fact.kind}>
                · {fact.detail}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-slate-400">
            候选事实仅描述检测覆盖，不构成落点统计或战术结论，也不参与表现发现。
          </p>
        </section>
      ) : null}

      {/* ── 训练建议与下次训练目标 ── */}
      <section>
        <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.16em] text-slate-400">训练建议与下次目标</h3>
        <div className="grid gap-3 lg:grid-cols-2">
          {subjectRecommendations.length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
              当前视角暂无待改进项，保持现有训练节奏即可。
            </p>
          ) : (
            subjectRecommendations.map((recommendation) => (
              <article className="rounded-2xl border border-[#22C55E]/30 bg-[#22C55E]/5 p-5" key={recommendation.id}>
                <h4 className="text-base font-bold text-[#14241B]">{recommendation.title}</h4>
                <p className="mt-1.5 text-sm leading-6 text-slate-600">{recommendation.detail}</p>
                <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl bg-white/80 p-3">
                    <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">本次 baseline</dt>
                    <dd className="mt-1 font-semibold text-slate-700">{recommendation.baseline}</dd>
                  </div>
                  <div className="rounded-xl bg-white/80 p-3">
                    <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">下一次目标</dt>
                    <dd className="mt-1 font-semibold text-[#15803D]">{recommendation.next_target}</dd>
                  </div>
                </dl>
              </article>
            ))
          )}
        </div>
        <p className="mt-2 text-[11px] text-slate-400">
          训练目标只包含本次 baseline 与下一次可度量目标；跨场次历史对比需建立稳定球员档案后提供。
        </p>
      </section>
    </div>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-2 text-[#168A34]">
        {icon}
        <span className="text-[11px] font-bold uppercase tracking-[0.16em]">{label}</span>
      </div>
      <p className="mt-2.5 line-clamp-2 text-lg font-black text-[#14241B]">{value}</p>
      {detail ? <p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p> : null}
    </div>
  );
}
