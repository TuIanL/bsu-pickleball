import { useState, useEffect } from "react";
import { ArrowRight } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import type { AnalysisJobSummary } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { DiagnosticNoticeCard } from "../components/DiagnosticNoticeCard";
import { StatusState } from "../components/StatusState";
import { supportedReportTypes } from "../app/router";
import { reportActions } from "../data/demoData";
import { getAnalysisJob, rememberAnalysisJob, cancelAnalysisJob } from "../services/analysisClient";
import { errorToNotice, isCancelableAnalysisJob, cameraAngleLabel, formatDateTime, formatDurationMs } from "../utils/analysisHelpers";

export function AnalysisJobPage({ jobId, onNavigate }: { jobId: string; onNavigate: NavigateFn }) {
  const [job, setJob] = useState<AnalysisJobSummary | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<DiagnosticNotice | null>(null);
  const [cancelNotice, setCancelNotice] = useState<DiagnosticNotice | null>(null);
  const [isCanceling, setIsCanceling] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;

    const loadJob = async () => {
      try {
        const nextJob = await getAnalysisJob(jobId);
        if (!alive) {
          return;
        }

        setLoadError(null);
        setJob(nextJob);
        rememberAnalysisJob(nextJob);

        if (nextJob && ["uploaded", "queued", "processing"].includes(nextJob.status)) {
          timer = window.setTimeout(loadJob, 1600);
        }
      } catch (error) {
        if (!alive) {
          return;
        }
        setJob(null);
        setLoadError(errorToNotice("读取分析任务失败", "无法读取该任务的最新状态，请检查后端服务和任务 ID。", error));
      }
    };

    loadJob();

    return () => {
      alive = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [jobId]);

  if (job === undefined) {
    return <StatusState title="正在读取分析任务" body="正在连接后端或本地 mock 任务记录。" onNavigate={onNavigate} />;
  }

  if (loadError) {
    return <StatusState title={loadError.title} body={loadError.body} notice={loadError} onNavigate={onNavigate} />;
  }

  if (!job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，可能是本地记录已清空。`} onNavigate={onNavigate} />;
  }

  const statusCopy = {
    uploaded: "视频已接收",
    queued: "排队中",
    processing: "分析中",
    failed: "分析失败",
    completed: "分析完成",
    canceled: "任务已取消",
  } satisfies Record<AnalysisJobSummary["status"], string>;

  const isCompleted = job.status === "completed";
  const isFailed = job.status === "failed";
  const isCanceled = job.status === "canceled";
  const canCancel = isCancelableAnalysisJob(job);
  const activeStage = job.stages.find((stage) => stage.status === "active") ?? job.stages.find((stage) => stage.id === job.stage);
  const failedStage = job.stages.find((stage) => stage.status === "failed");
  const currentStage = failedStage ?? activeStage ?? [...job.stages].reverse().find((stage) => stage.status === "done" || stage.status === "skipped");

  const handleCancel = async () => {
    if (!canCancel || isCanceling) {
      return;
    }
    const confirmed = window.confirm(`确定取消「${job.metadata.matchTitle}」吗？运行中的任务会在安全检查点停止。`);
    if (!confirmed) {
      return;
    }
    setIsCanceling(true);
    setCancelNotice(null);
    try {
      const nextJob = await cancelAnalysisJob(job.id);
      setJob(nextJob);
      rememberAnalysisJob(nextJob);
      setCancelNotice({
        title: nextJob.status === "canceled" ? "任务已取消" : "已请求取消任务",
        body:
          nextJob.status === "canceled"
            ? "任务已停止，后续可以删除该历史任务或重新上传。"
            : "运行中的分析会在下一处安全检查点停止，本页会继续刷新状态。",
      });
    } catch (error) {
      setCancelNotice(errorToNotice("取消任务失败", "无法取消该分析任务，请刷新后重试。", error));
    } finally {
      setIsCanceling(false);
    }
  };

  return (
    <PageFrame>
      <section className="sport-card overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.42fr] lg:p-8">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-[#168A34]">分析任务</p>
            <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">{statusCopy[job.status]}</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
              {job.metadata.matchTitle} · {job.metadata.fileName} · {job.metadata.venue}
            </p>
            <p className="mt-2 text-sm font-semibold text-slate-500">任务 ID：{job.id}</p>
            {currentStage ? (
              <p className="mt-3 inline-flex rounded-full border border-[#DDE9D6] bg-white/80 px-3 py-1 text-sm font-bold text-[#14241B]">
                当前阶段：{currentStage.label} · {currentStage.status === "failed" ? "失败" : currentStage.status === "active" ? "处理中" : currentStage.status === "skipped" ? "已跳过" : "已完成"}
              </p>
            ) : null}
          </div>
          <div className="rounded-3xl border border-[#22C55E]/25 bg-[#22C55E]/10 p-6">
            <span className="text-sm font-bold text-[#168A34]">当前进度</span>
            <strong className="mt-4 block text-5xl font-black text-[#13A12C]">{job.progress}%</strong>
            <div className="mt-5 h-2 rounded-full bg-[#DFEADA]">
              <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${job.progress}%` }} />
            </div>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">任务信息</p>
          <div className="mt-5 grid gap-3 text-sm">
            {[
              ["比赛形式", job.metadata.matchFormat === "doubles" ? "双打" : "单打"],
              ["拍摄角度", cameraAngleLabel(job.metadata.cameraAngle)],
              ["球员/队伍", job.metadata.athleteLabel],
              ["水平", job.metadata.level],
              ["分析模式", job.analysisMode === "real" ? "真实视频分析" : job.analysisMode === "limited" ? "有限分析" : "样例任务"],
              [
                "人体检测 (YOLO)",
                job.enableModelInference === undefined
                  ? "沿用全局"
                  : job.enableModelInference
                    ? "开启"
                    : "关闭",
              ],
              [
                "姿态识别 (RTMPose)",
                job.enablePoseInference === undefined
                  ? "沿用全局"
                  : job.enablePoseInference
                    ? "开启"
                    : "关闭",
              ],
              ["视频 ID", job.videoId ?? "无"],
              ["标定 ID", job.calibrationId ?? "无"],
              ["创建时间", new Date(job.createdAt).toLocaleString()],
            ].map(([label, value]) => (
              <div className="flex justify-between gap-4 rounded-2xl bg-[#F5FAF1] p-3" key={label}>
                <span className="text-slate-500">{label}</span>
                <strong className="text-right text-[#14241B]">{value}</strong>
              </div>
            ))}
          </div>
          {isFailed ? (
            <div className="mt-4">
              <DiagnosticNoticeCard
                notice={{
                  title: "分析任务失败",
                  body: job.publicErrorMessage ?? job.errorMessage ?? "请重新上传或检查后端日志。",
                  detailItems: [
                    ["错误码", job.errorCode],
                    ["失败阶段", failedStage?.label ?? job.stage],
                    ["阶段详情", failedStage?.detail],
                    ["任务 ID", job.id],
                  ],
                }}
              />
            </div>
          ) : null}
          {isCanceled ? (
            <div className="mt-4">
              <DiagnosticNoticeCard
                notice={{
                  title: "任务已取消",
                  body: "该分析任务已停止，保留任务记录供追踪和复盘。",
                  detailItems: [
                    ["取消时间", job.canceledAt ? formatDateTime(job.canceledAt) : undefined],
                    ["任务 ID", job.id],
                  ],
                }}
                tone="info"
              />
            </div>
          ) : null}
          {cancelNotice ? (
            <div className="mt-4">
              <DiagnosticNoticeCard notice={cancelNotice} tone={cancelNotice.title.includes("失败") ? "error" : "info"} />
            </div>
          ) : null}
        </article>

        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">分析阶段</p>
          <div className="mt-5 grid gap-3">
            {job.stages.map((stage) => (
              <div className="flex gap-3 rounded-2xl border border-[#DDE9D6] bg-white/70 p-4" key={stage.id}>
                <span className={`mt-1 size-3 shrink-0 rounded-full ${stage.status === "done" ? "bg-[#22C55E]" : stage.status === "failed" ? "bg-[#FF4D4F]" : stage.status === "active" ? "bg-[#FF9500]" : stage.status === "canceled" ? "bg-slate-500" : stage.status === "skipped" ? "bg-slate-400" : "bg-slate-300"}`} />
                <div>
                  <strong className="text-[#14241B]">{stage.label}</strong>
                  <p className="mt-1 text-sm leading-6 text-slate-600">
                    {stage.status === "skipped" ? "已跳过 · " : null}
                    {stage.status === "canceled" ? "已取消 · " : null}
                    {stage.publicMessage ?? stage.detail}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs font-bold text-slate-500">
                    {stage.durationMs != null ? <span>耗时 {formatDurationMs(stage.durationMs)}</span> : null}
                    {stage.errorCode ? <span>错误码 {stage.errorCode}</span> : null}
                    {stage.retryCount ? <span>重试 {stage.retryCount} 次</span> : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="mt-6 sport-card p-5 sm:p-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">结果入口</p>
            <h2 className="mt-2 text-2xl font-black text-[#14241B]">
              {isCompleted ? "报告已经生成" : "等待分析完成后生成报告"}
            </h2>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              className="green-button px-4 py-2.5"
              disabled={!isCompleted}
              onClick={() => onNavigate(`/analysis/${job.id}/vision`)}
              type="button"
            >
              打开视频分析
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            <button
              className="quiet-button px-4 py-2.5"
              disabled={!isCompleted}
              onClick={() => onNavigate(`/analysis/${job.id}/details`)}
              type="button"
            >
              分析详情
            </button>
            {reportActions.filter((action) => supportedReportTypes.includes(action.type)).map((action) => (
              <button
                className="quiet-button px-4 py-2.5"
                disabled={!isCompleted}
                key={action.type}
                onClick={() => onNavigate(`/analysis/${job.id}/reports/${action.type}`)}
                type="button"
              >
                {action.title}
              </button>
            ))}
            {canCancel ? (
              <button className="quiet-button px-4 py-2.5 text-[#A45A00]" disabled={isCanceling} onClick={handleCancel} type="button">
                {isCanceling ? "取消中" : "取消任务"}
              </button>
            ) : null}
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
              {isCanceled ? "新建分析" : "重新上传"}
            </button>
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/analysis/tasks")} type="button">
              返回任务管理
            </button>
          </div>
        </div>
      </section>
    </PageFrame>
  );
}
