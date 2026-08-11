import { useState, useEffect } from "react";
import { ArrowRight, Dumbbell } from "lucide-react";
import type { NavigateFn, AppPath } from "../app/navigationTypes";
import type { AnalysisReport, ReportType, AnalysisJobSummary } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { taskContextForJob, taskListPathForJob, withTaskListContext } from "../app/navigationContext";
import { PageFrame } from "../components/PageFrame";
import { StatusState } from "../components/StatusState";
import { MetricCard } from "../components/platform/MetricCard";
import { ReportVisualization } from "../components/platform/ReportVisualization";
import { supportedReportTypes } from "../app/router";
import { demoAnalysisReport as demoReport, getAnalysisJob, getAnalysisReport } from "../services/analysisClient";
import { formatDateTime, toneStyles, errorToNotice } from "../utils/analysisHelpers";

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
  const taskReturnPath = taskListPathForJob(job);

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

  const analysis = report ?? demoReport;
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
