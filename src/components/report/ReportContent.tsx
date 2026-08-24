// =============================================================
// ReportContent - 报告「数据与业务状态」层
// -------------------------------------------------------------
// 四层职责中的第 1 层：负责 useJobReport 驱动的
//   loading / failed / canceled / not-found / no-report 等数据状态。
// 拿到 report data 后委托 PbReportContent 渲染 PB 视觉内容。
// 可被 Workspace 报告 view 与独立报告路由共同复用。
// =============================================================
import { useEffect, useState } from "react";
import type { AnalysisReport, AnalysisJobSummary, NavigateFn, ReconstructedBallTrajectoryArtifact } from "../../types/report";
import type { NavigatePath } from "../../app/navigationTypes";
import type { DiagnosticNotice } from "../../services/analysisDiagnostics";
import { StatusState } from "../StatusState";
import { demoAnalysisReport as demoReport, getAnalysisJob, getAnalysisReport, getAnalysisResult, getReconstructedBallTrajectory } from "../../services/analysisClient";
import { isPipelineResult } from "../../services/pipelineReportAdapter";
import { formatDateTime, errorToNotice } from "../../utils/analysisHelpers";
import PbReportContent from "../pb-vizion/PbReportContent";

function useJobReport(jobId?: string) {
  const [loadedReport, setLoadedReport] = useState<{
    error: DiagnosticNotice | null;
    job: AnalysisJobSummary | null;
    jobId: string;
    report: AnalysisReport | null;
    trajectoryArtifact: ReconstructedBallTrajectoryArtifact | null;
  } | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    const load = async () => {
      try {
        const [nextJob, nextReport, rawResult] = await Promise.all([
          getAnalysisJob(jobId),
          getAnalysisReport(jobId),
          getAnalysisResult(jobId),
        ]);
        const pipelineResult = isPipelineResult(rawResult) ? rawResult : null;
        const trajectoryArtifact = pipelineResult
          ? await getReconstructedBallTrajectory(pipelineResult).catch(() => null)
          : null;
        if (alive) {
          setLoadedReport({ error: null, job: nextJob, jobId, report: nextReport, trajectoryArtifact });
        }
      } catch (error) {
        if (alive) {
          setLoadedReport({
            error: errorToNotice("读取分析报告失败", "无法读取该任务生成的报告数据，请检查后端服务和任务产物。", error),
            job: null,
            jobId,
            report: null,
            trajectoryArtifact: null,
          });
        }
      }
    };
    load();
    return () => {
      alive = false;
    };
  }, [jobId]);

  if (!jobId) return { error: null, job: null, report: demoReport, trajectoryArtifact: null };
  if (loadedReport?.jobId !== jobId) return { error: null, job: undefined, report: undefined, trajectoryArtifact: undefined };
  return { error: loadedReport.error, job: loadedReport.job, report: loadedReport.report, trajectoryArtifact: loadedReport.trajectoryArtifact };
}

export function ReportContent({
  jobId,
  onNavigate,
  backPath,
}: {
  jobId?: string;
  onNavigate: NavigateFn;
  backPath?: NavigatePath;
}) {
  const { error, job, report, trajectoryArtifact } = useJobReport(jobId);

  if (jobId && (job === undefined || report === undefined)) {
    return <StatusState title="正在加载分析报告" body="正在读取该任务生成的轻量报告数据。" onNavigate={onNavigate} backPath={backPath} />;
  }

  if (jobId && error) {
    return <StatusState title={error.title} body={error.body} notice={error} onNavigate={onNavigate} backPath={backPath} />;
  }

  if (jobId && !job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，无法打开报告。`} onNavigate={onNavigate} backPath={backPath} />;
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
        backPath={backPath}
      />
    );
  }

  if (jobId && !report) {
    return (
      <StatusState
        title="报告尚未生成"
        body="该任务记录已读取，但还没有可用的轻量报告数据。请返回并稍后重试。"
        onNavigate={onNavigate}
        backPath={backPath}
      />
    );
  }

  const analysis = (report ?? demoReport) as AnalysisReport;
  return <PbReportContent report={analysis} trajectoryArtifact={trajectoryArtifact ?? null} />;
}
