import { useState, useEffect, useMemo } from "react";
import { ArrowRight, Dumbbell } from "lucide-react";
import type {
  AnalysisReport,
  NavigateFn,
  AppPath,
  ReportType,
  AnalysisJobSummary,
} from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { taskContextForJob, taskListPathForJob, withTaskListContext } from "../app/navigationContext";
import { PageFrame } from "../components/PageFrame";
import { StatusState } from "../components/StatusState";
import { MetricCard } from "../components/platform/MetricCard";
import { ReportVisualization } from "../components/platform/ReportVisualization";
import { supportedReportTypes } from "../app/router";
import { demoAnalysisReport as demoReport, getAnalysisJob, getAnalysisReport } from "../services/analysisClient";
import { PerformanceInsightsPanel } from "../components/platform/PerformanceInsightsPanel";
import { formatDateTime, toneStyles, errorToNotice } from "../utils/analysisHelpers";
import PbVisionReportLayout from "../components/pb-vizion/PbVisionReportLayout";

function useJobReport(jobId?: string) {
  const [loadedReport, setLoadedReport] = useState<{
    error: DiagnosticNotice | null;
    job: AnalysisJobSummary | null;
    jobId: string;
    report: AnalysisReport | null;
  } | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let alive = true;

    const load = async () => {
      try {
        const [nextJob, nextReport] = await Promise.all([getAnalysisJob(jobId), getAnalysisReport(jobId)]);

        if (alive) {
          setLoadedReport({
            error: null,
            job: nextJob,
            jobId,
            report: nextReport,
          });
        }
      } catch (error) {
        if (alive) {
          setLoadedReport({
            error: errorToNotice("读取分析报告失败", "无法读取该任务生成的报告数据，请检查后端服务和任务产物。", error),
            job: null,
            jobId,
            report: null,
          });
        }
      }
    };

    load();

    return () => {
      alive = false;
    };
  }, [jobId]);

  if (!jobId) {
    return { error: null, job: null, report: demoReport };
  }

  if (loadedReport?.jobId !== jobId) {
    return {
      error: null,
      job: undefined,
      report: undefined,
    };
  }

  return {
    error: loadedReport.error,
    job: loadedReport.job,
    report: loadedReport.report,
  };
}

/** 基于原生 URLSearchParams 读取当前 query，无需 react-router-dom。 */
function useCurrentSearchParams(): URLSearchParams {
  const [params, setParams] = useState<URLSearchParams>(() => {
    if (typeof window === "undefined") return new URLSearchParams();
    return new URLSearchParams(window.location.search);
  });
  useEffect(() => {
    const onChange = () => setParams(new URLSearchParams(window.location.search));
    window.addEventListener("popstate", onChange);
    window.addEventListener("searchparams:change", onChange);
    return () => {
      window.removeEventListener("popstate", onChange);
      window.removeEventListener("searchparams:change", onChange);
    };
  }, []);
  return params;
}

export function ReportPage({
  jobId,
  onNavigate,
  reportType,
}: {
  jobId?: string;
  onNavigate: NavigateFn;
  reportType: ReportType;
}) {
  const { error, job, report } = useJobReport(jobId);
  const searchParams = useCurrentSearchParams();
  const taskReturnPath = taskListPathForJob(job);

  // 2.4 读取 legacy 标记：
  //   - query: ?legacy=1 优先
  //   - 否则 fallback localStorage.reportLegacy==='1'
  const useLegacyLayout = useMemo(() => {
    if (typeof window === "undefined") return false;
    const fromQuery = searchParams.get("legacy");
    if (fromQuery !== null) {
      return fromQuery === "1" || fromQuery === "true";
    }
    return window.localStorage.getItem("reportLegacy") === "1";
  }, [searchParams]);

  if (jobId && (job === undefined || report === undefined)) {
    return <StatusState title="正在加载分析报告" body="正在读取该任务生成的轻量报告数据。" onNavigate={onNavigate} backPath={taskReturnPath} />;
  }

  if (jobId && error) {
    return <StatusState title={error.title} body={error.body} notice={error} onNavigate={onNavigate} backPath={taskReturnPath} />;
  }

  if (jobId && !job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，无法打开报告。`} onNavigate={onNavigate} backPath={taskReturnPath} />;
  }

  if (job && job.status !== "completed") {
    const canceled = job.status === "canceled";
    return (
      <StatusState
        title={job.status === "failed" ? "分析任务失败" : canceled ? "分析任务已取消" : "报告尚未生成"}
        body={
          job.status === "failed"
            ? job.publicErrorMessage ?? job.errorMessage ?? "请重新上传或检查后端日志。"
            : canceled
              ? "任务在完成前被取消，因此不会生成报告页面。"
              : "任务还在排队或处理中，完成后会开放报告页面。"
        }
        notice={
          job.status === "failed"
            ? {
                title: "失败位置",
                body: job.publicErrorMessage ?? job.errorMessage ?? "请重新上传或检查后端日志。",
                detailItems: [
                  ["错误码", job.errorCode],
                  ["失败阶段", job.stages.find((stage) => stage.status === "failed")?.label ?? job.stage],
                  ["阶段详情", job.stages.find((stage) => stage.status === "failed")?.detail],
                ],
              }
            : canceled
              ? {
                  title: "取消记录",
                  body: "任务取消后保留执行记录，但不会生成报告。",
                  detailItems: [["取消时间", job.canceledAt ? formatDateTime(job.canceledAt) : undefined]],
                }
              : null
        }
        onNavigate={onNavigate}
        backPath={taskReturnPath}
      />
    );
  }

  if (jobId && !report) {
    return (
      <StatusState
        title="报告尚未生成"
        body="该任务记录已读取，但还没有可用的轻量报告数据。请返回任务管理查看任务状态或稍后重试。"
        onNavigate={onNavigate}
        backPath={taskReturnPath}
      />
    );
  }

  const analysis = (report ?? demoReport) as AnalysisReport;

  // —— 默认：渲染 PB Vision 风格（新布局）
  if (!useLegacyLayout) {
    return <PbVisionReportLayout report={analysis} />;
  }

  // —— legacy=true：渲染旧布局（深绿风格）
  const supportedDefinitions = analysis.reportDefinitions.filter((item) => supportedReportTypes.includes(item.type));
  const definition =
    supportedDefinitions.find((item) => item.type === reportType) ??
    supportedDefinitions[0] ??
    analysis.reportDefinitions[0];
  const backPath = analysis.jobId
    ? withTaskListContext(`/analysis/${analysis.jobId}/vision`, taskContextForJob(job))
    : "/vision" as AppPath;

  return (
    <PageFrame>
      {/* 任务 7.6：在旧版页面顶部也放一个切回新版的按钮，避免用户卡死在 legacy 版本 */}
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-lg border border-[#22C55E]/40 bg-white px-3 py-1.5 text-xs font-semibold text-[#168A34] hover:bg-[#22C55E]/10 transition"
          onClick={() => {
            if (typeof window !== "undefined") {
              window.localStorage.removeItem("reportLegacy");
              // 同时清掉 URL 上的 legacy query，保证之后都走默认新布局
              const next = new URL(window.location.href);
              next.searchParams.delete("legacy");
              window.location.href = next.toString();
            }
          }}
        >
          <span>✨</span>
          <span>切换到新版</span>
        </button>
      </div>

      <section className="sport-card overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.45fr] lg:p-8">
          <div>
            <button
              className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
              onClick={() => onNavigate(backPath)}
              type="button"
            >
              <ArrowRight className="rotate-180" size={16} aria-hidden="true" />
              返回视频分析
            </button>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-[#168A34]">{definition.eyebrow}</p>
            <h1 className="mt-3 max-w-4xl text-4xl font-black text-[#14241B] sm:text-5xl">{definition.title}</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">{definition.summary}</p>
            <p className="mt-3 text-sm font-semibold text-slate-500">
              {analysis.source === "demo"
                ? "样例报告"
                : `${job?.analysisMode === "limited" ? "有限真实分析" : "真实上传视频"} · ${analysis.metadata.matchTitle} · ${analysis.metadata.fileName} · ${analysis.reportId}`}
            </p>
          </div>
          <div className="rounded-3xl border border-[#22C55E]/25 bg-[#22C55E]/10 p-6">
            <span className="text-sm font-bold text-[#168A34]">{definition.heroMetricLabel}</span>
            <strong className="mt-4 block text-5xl font-black text-[#13A12C]">{definition.heroMetric}</strong>
            <button className="mt-6 green-button w-full" onClick={() => onNavigate("/training")} type="button">
              查看相关训练
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {definition.metrics.map((metric) => (
          <MetricCard key={`${definition.type}-${metric.id}`} metric={metric} />
        ))}
      </section>

      {reportType === "performance" ? (
        <section className="mt-6">
          {analysis.performanceInsights ? (
            <PerformanceInsightsPanel
              insights={analysis.performanceInsights}
              jobId={analysis.jobId ?? jobId}
              job={job}
              onNavigate={onNavigate}
            />
          ) : (
            /* demo 任务 / v1 旧报告访问 performance 路由：显示样例说明，不用 demo 数据冒充真实洞察。 */
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6">
              <p className="text-sm font-bold text-slate-600">该报告不含表现洞察数据</p>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {analysis.source === "demo"
                  ? "当前为样例报告：表现洞察只对真实分析任务生成，样例数据不会冒充洞察结论。"
                  : "该任务的报告版本较早（v1），未包含表现洞察字段。重新运行分析即可生成。"}
              </p>
            </div>
          )}
        </section>
      ) : null}

      <div className="mt-6">
        <ReportVisualization
          definition={definition}
          diagnoses={analysis.diagnoses}
          movementPath={analysis.session.movementPath}
        />
      </div>

      <section className="mt-6 grid gap-4 lg:grid-cols-[0.78fr_1.22fr]">
        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">训练承接</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">{definition.trainingLink}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            这份报告的价值不止在解释数据，还要把弱项直接转成下一次训练任务。
          </p>
          <button className="mt-5 green-button" onClick={() => onNavigate("/training")} type="button">
            打开训练计划
            <Dumbbell size={17} aria-hidden="true" />
          </button>
        </article>
        <div className="grid gap-4 md:grid-cols-2">
          {definition.insights.map((insight) => {
            const style = toneStyles[insight.tone];

            return (
              <article className={`rounded-2xl border p-5 ${style.border} ${style.bg}`} key={insight.id}>
                <strong className={`text-base ${style.text}`}>{insight.title}</strong>
                <p className="mt-3 text-sm leading-6 text-slate-600">{insight.body}</p>
              </article>
            );
          })}
        </div>
      </section>
    </PageFrame>
  );
}
