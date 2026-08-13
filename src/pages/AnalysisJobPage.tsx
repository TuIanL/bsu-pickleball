import { useState, useEffect } from "react";
import { ArrowLeft, ArrowRight, Camera, Layers } from "lucide-react";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { taskContextForJob, taskListPathForJob, withTaskListContext } from "../app/navigationContext";
import type { AnalysisJobSummary } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { DiagnosticNoticeCard } from "../components/DiagnosticNoticeCard";
import { JobStageStepper } from "../components/platform/JobStageStepper";
import { StatusState } from "../components/StatusState";
import { supportedReportTypes } from "../app/router";
import { reportActions } from "../data/demoData";
import { getAnalysisJob, rememberAnalysisJob, cancelAnalysisJob } from "../services/analysisClient";
import { errorToNotice, isCancelableAnalysisJob, cameraAngleLabel, formatDateTime, formatDurationMs, analysisStatusMeta, analysisModeLabel } from "../utils/analysisHelpers";

const VIEW_LABELS: Record<string, string> = { cam_1: "A 机位", cam_2: "B 机位" };

const TERMINAL_STATUSES = ["completed", "failed", "canceled"] as const;

export function AnalysisJobPage({ jobId, onNavigate }: { jobId: string; onNavigate: NavigateFn }) {
  const [job, setJob] = useState<AnalysisJobSummary | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<DiagnosticNotice | null>(null);
  const [cancelNotice, setCancelNotice] = useState<DiagnosticNotice | null>(null);
  const [isCanceling, setIsCanceling] = useState(false);

  const isMultiview = job?.analysisKind === "multiview";
  const returnPath = taskListPathForJob(job);
  const contextualPath = (path: string) => withTaskListContext(path, taskContextForJob(job));

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
    return <StatusState title="正在读取分析任务" body="正在连接后端或本地 mock 任务记录。" onNavigate={onNavigate} backPath={returnPath} />;
  }

  if (loadError) {
    return <StatusState title={loadError.title} body={loadError.body} notice={loadError} onNavigate={onNavigate} backPath={returnPath} />;
  }

  if (!job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，可能是本地记录已清空。`} onNavigate={onNavigate} backPath={returnPath} />;
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
  const isTerminal = TERMINAL_STATUSES.includes(job.status as (typeof TERMINAL_STATUSES)[number]);
  const canCancel = isCancelableAnalysisJob(job);
  const activeStage = job.stages.find((stage) => stage.status === "active");
  const failedStage = job.stages.find((stage) => stage.status === "failed");
  const currentStage = failedStage ?? activeStage;
  const statusMeta = analysisStatusMeta(job.status);

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

  const completedStageCount = job.stages.filter((stage) => stage.status === "done" || stage.status === "skipped").length;
  const totalDurationMs = job.stages.reduce((sum, stage) => sum + (stage.durationMs ?? 0), 0);

  return (
    <PageFrame>
      <section className="sport-card overflow-hidden">
        <div className="p-6 lg:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
              onClick={() => onNavigate(returnPath)}
              type="button"
            >
              <ArrowLeft size={16} aria-hidden="true" />
              返回任务管理
            </button>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-black ${statusMeta.className}`}>{statusMeta.label}</span>
              <span className="rounded-full border border-[#DDE9D6] bg-white/80 px-3 py-1 text-xs font-bold text-slate-500">
                {analysisModeLabel(job.analysisMode)}
              </span>
              {isMultiview ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-[#168A34]/25 bg-[#EAF7EE] px-3 py-1 text-xs font-black text-[#168A34]">
                  <Layers size={12} aria-hidden="true" />
                  双摄协同
                </span>
              ) : null}
            </div>
          </div>

          <h1 className="mt-5 text-4xl font-black text-[#14241B] sm:text-5xl">{statusCopy[job.status]}</h1>
          <p className="mt-3 max-w-3xl text-base leading-7 text-slate-600">
            {job.metadata.matchTitle} · {job.metadata.fileName} · {job.metadata.venue} · 任务 ID：{job.id}
          </p>

          {isTerminal ? (
            <TerminalSummary
              isCompleted={isCompleted}
              isFailed={isFailed}
              isCanceled={isCanceled}
              job={job}
              completedStageCount={completedStageCount}
              totalDurationMs={totalDurationMs}
              currentStage={currentStage}
              onNavigate={onNavigate}
              contextualPath={contextualPath}
              returnPath={returnPath}
            />
          ) : (
            <div className="mt-6 rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4 sm:p-5">
              <JobStageStepper stages={job.stages} ariaLabel="分析阶段进度" />

              <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                <p className="min-w-0 flex-1 text-sm font-semibold leading-6 text-[#14241B]">
                  {currentStage ? (
                    <>
                      <span className={`mr-1.5 inline-block size-2 rounded-full align-middle ${currentStage.status === "failed" ? "bg-[#FF4D4F]" : "bg-[#FF9500]"}`} />
                      {currentStage.label}
                      {currentStage.detail ? <span className="text-slate-600"> · {currentStage.detail}</span> : null}
                    </>
                  ) : (
                    <span className="text-slate-500">{statusCopy[job.status]}，等待视觉分析任务执行…</span>
                  )}
                </p>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">整体进度</span>
                  <strong className="text-xl font-black text-[#168A34]">{job.progress}%</strong>
                </div>
              </div>
              <div className="mt-2 h-1.5 rounded-full bg-[#DFEADA]">
                <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${job.progress}%` }} />
              </div>

              {isMultiview && job.viewRuns ? (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {Object.entries(job.viewRuns).map(([view, run]) => (
                    <div className="rounded-xl border border-[#DDE9D6] bg-white/80 p-2.5" key={view}>
                      <div className="flex items-center justify-between text-xs font-bold">
                        <span className="inline-flex items-center gap-1.5 text-[#14241B]">
                          <Camera size={12} aria-hidden="true" />
                          {VIEW_LABELS[view] ?? view}
                        </span>
                        <span className="text-slate-500">{run.progress}%</span>
                      </div>
                      <div className="mt-1.5 h-1 rounded-full bg-[#DFEADA]">
                        <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${run.progress}%` }} />
                      </div>
                      <p className="mt-1 truncate text-[0.68rem] font-semibold text-slate-500">{run.stage}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              {canCancel ? (
                <div className="mt-4 flex justify-end">
                  <button className="quiet-button px-3 py-2 text-sm text-[#A45A00]" disabled={isCanceling} onClick={handleCancel} type="button">
                    {isCanceling ? "取消中…" : "取消任务"}
                  </button>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </section>

      {isMultiview && isCompleted ? (
        <section className="mt-6 sport-card border-l-4 border-l-[#168A34] p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex min-w-0 items-start gap-3">
              <Layers size={20} className="mt-0.5 shrink-0 text-[#168A34]" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">双摄协同分析</p>
                <h2 className="mt-1 text-lg font-black text-[#14241B]">同步、融合、恢复与精修已集中到协同详情页</h2>
                <p className="mt-1 text-sm leading-6 text-slate-600">任务页保留轻量摘要；完整状态由后端 observability summary 统一投影。</p>
              </div>
            </div>
            <button className="green-button shrink-0 px-4 py-2.5" onClick={() => onNavigate(contextualPath(`/analysis/${job.id}/multiview`))} type="button">
              查看双摄协同详情
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </section>
      ) : null}

      <section className="mt-6 sport-card p-5 sm:p-6">
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">任务信息</p>
            <span className="text-xs font-bold text-slate-400 transition group-open:rotate-180">▾</span>
          </summary>
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
        </details>
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
      </section>
    </PageFrame>
  );
}

function TerminalSummary({
  isCompleted,
  isFailed,
  isCanceled,
  job,
  completedStageCount,
  totalDurationMs,
  currentStage,
  onNavigate,
  contextualPath,
  returnPath,
}: {
  isCompleted: boolean;
  isFailed: boolean;
  isCanceled: boolean;
  job: AnalysisJobSummary;
  completedStageCount: number;
  totalDurationMs: number;
  currentStage: { label: string; detail?: string } | undefined;
  onNavigate: NavigateFn;
  contextualPath: (path: string) => NavigatePath;
  returnPath: NavigatePath;
}) {
  return (
    <div className="mt-6 rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4 sm:p-5">
      {isCompleted ? (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-bold text-[#168A34]">
              {`${completedStageCount}/${job.stages.length || 1} 阶段完成`}
              {totalDurationMs > 0 ? <span className="font-semibold text-slate-500"> · 总耗时 {formatDurationMs(totalDurationMs)}</span> : null}
            </p>
            <p className="mt-1 text-sm leading-6 text-slate-600">报告已生成，可以查看视频分析或指标详情。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="green-button px-4 py-2.5"
              onClick={() => onNavigate(contextualPath(`/analysis/${job.id}/vision`))}
              type="button"
            >
              打开视频分析
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            <button
              className="quiet-button px-4 py-2.5"
              onClick={() => onNavigate(contextualPath(`/analysis/${job.id}/details`))}
              type="button"
            >
              分析详情
            </button>
            {reportActions.filter((action) => supportedReportTypes.includes(action.type)).map((action) => (
              <button
                className="quiet-button px-4 py-2.5"
                disabled={!isCompleted}
                key={action.type}
                onClick={() => onNavigate(contextualPath(`/analysis/${job.id}/reports/${action.type}`))}
                type="button"
              >
                {action.title}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className={`text-sm font-bold ${isFailed ? "text-[#C92A2A]" : "text-slate-600"}`}>
              {isFailed
                ? `失败阶段：${currentStage?.label ?? job.stage}`
                : `任务已取消${job.canceledAt ? ` · ${formatDateTime(job.canceledAt)}` : ""}`}
            </p>
            {isFailed ? (
              <p className="mt-1 text-sm leading-6 text-slate-600">
                {job.publicErrorMessage ?? job.errorMessage ?? currentStage?.detail ?? "请重新上传或检查后端日志。"}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="green-button px-4 py-2.5" onClick={() => onNavigate(contextualPath("/analysis/new"))} type="button">
              {isCanceled ? "新建分析" : "重新上传"}
            </button>
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(returnPath)} type="button">
              返回任务管理
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
