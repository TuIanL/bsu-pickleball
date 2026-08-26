import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Camera, Layers } from "lucide-react";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { resolveAnalysisFlowOrigin, resolveLibraryRefFromAnalysisJob, taskContextForJob, taskListPathForJob, withTaskListContext } from "../app/navigationContext";
import type { AnalysisJobSummary } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { DiagnosticNoticeCard } from "../components/DiagnosticNoticeCard";
import { JobStageStepper } from "../components/platform/JobStageStepper";
import { StatusState } from "../components/StatusState";
import { supportedReportTypes } from "../app/router";
import { reportActions } from "../data/demoData";
import { getAnalysisJob, getAnalysisResult, rememberAnalysisJob, cancelAnalysisJob } from "../services/analysisClient";
import { errorToNotice, isCancelableAnalysisJob, cameraAngleLabel, formatDateTime, formatDurationMs, analysisStatusMeta, analysisModeLabel } from "../utils/analysisHelpers";
import { resolveLibraryItemByRef, type LibraryItemViewModel } from "../services/libraryAdapter";
import { computeLibraryViewCapabilities, type LibraryView } from "../components/library/viewCapabilities";
import { libraryAnalysisPathFor } from "../services/libraryAnalysisRouting";
import { isPipelineResult } from "../services/pipelineReportAdapter";
import { getReportCapability, type ReportCapability } from "../services/reportCapability";
import type { AnalysisPipelineResult } from "../types/report";

const VIEW_LABELS: Record<string, string> = { cam_1: "A 机位", cam_2: "B 机位" };

const TERMINAL_STATUSES = ["completed", "failed", "canceled", "interrupted"] as const;

export function AnalysisJobPage({ jobId, onNavigate }: { jobId: string; onNavigate: NavigateFn }) {
  const [job, setJob] = useState<AnalysisJobSummary | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<DiagnosticNotice | null>(null);
  const [cancelNotice, setCancelNotice] = useState<DiagnosticNotice | null>(null);
  const [isCanceling, setIsCanceling] = useState(false);
  // library origin 完成/失败/取消时，定向解析素材以门控结果 CTA（轻量，不拉重产物）
  const [libraryItem, setLibraryItem] = useState<LibraryItemViewModel | null>(null);
  const [reportManifest, setReportManifest] = useState<{
    jobId?: string;
    state: "idle" | "loading" | "loaded" | "error";
    result: AnalysisPipelineResult | null;
  }>({ state: "idle", result: null });

  const isMultiview = job?.analysisKind === "multiview";
  const isTerminal = Boolean(job && TERMINAL_STATUSES.includes(job.status as (typeof TERMINAL_STATUSES)[number]));

  const returnParam = new URLSearchParams(window.location.search).get("return");
  const taskContext = taskContextForJob(job);
  const origin = resolveAnalysisFlowOrigin(returnParam, taskContext);
  const libraryOrigin = origin.kind === "library" ? origin : null;
  const isLibraryOrigin = libraryOrigin !== null;
  const captureOrigin = origin.kind === "capture" ? origin : null;
  const isCaptureOrigin = captureOrigin !== null;

  const backPath: NavigatePath =
    (libraryOrigin ?? captureOrigin)?.returnPath as NavigatePath ?? taskListPathForJob(job);
  const backLabel = isLibraryOrigin ? "返回比赛详情" : isCaptureOrigin ? "返回现场采集" : "返回任务管理";

  // task-console origin 才为结果 URL 追加任务上下文参数
  const contextualPath = (path: string) =>
    origin.kind === "task-console" ? withTaskListContext(path, taskContext) : (path as NavigatePath);

  const libraryResultPath = (view: LibraryView): string | null =>
    libraryOrigin ? `/library/${libraryOrigin.itemKind}/${encodeURIComponent(libraryOrigin.sourceId)}?view=${view}&analysisJob=${encodeURIComponent(jobId)}` : null;

  // capture origin 完成后的结果定位：job → Library ref；无法归属降级 legacy 工程结果
  const captureResultPath = useMemo(() => {
    if (!captureOrigin || !job) return null;
    const ref = resolveLibraryRefFromAnalysisJob(job);
    return ref ? `/library/${ref.kind}/${encodeURIComponent(ref.sourceId)}?view=analysis&analysisJob=${encodeURIComponent(job.id)}` : null;
  }, [captureOrigin, job]);

  // library origin terminal：定向解析素材，门控「查看球路/报告/技术详情」与「再次分析」
  useEffect(() => {
    if (!libraryOrigin || !job || !isTerminal) {
      return;
    }
    let alive = true;
    resolveLibraryItemByRef({ kind: libraryOrigin.itemKind, sourceId: libraryOrigin.sourceId })
      .then((item) => {
        if (alive) setLibraryItem(item);
      })
      .catch(() => {
        if (alive) setLibraryItem(null);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.status, libraryOrigin?.returnPath]);

  const terminalLibraryItem = libraryOrigin && job && isTerminal ? libraryItem : null;
  const completedJobId = job?.status === "completed" ? job.id : undefined;
  useEffect(() => {
    if (!completedJobId) return;
    let alive = true;
    getAnalysisResult(completedJobId)
      .then((raw) => {
        if (alive) setReportManifest({ jobId: completedJobId, state: "loaded", result: isPipelineResult(raw) ? raw : null });
      })
      .catch(() => {
        if (alive) setReportManifest({ jobId: completedJobId, state: "error", result: null });
      });
    return () => {
      alive = false;
    };
  }, [completedJobId]);

  const reportManifestState = reportManifest.jobId === completedJobId ? reportManifest.state : completedJobId ? "loading" : "idle";
  const reportCapability = useMemo<ReportCapability>(
    () => getReportCapability({ job, manifest: reportManifest.result, manifestState: reportManifestState }),
    [job, reportManifest.result, reportManifestState],
  );
  const caps = useMemo(
    () => (terminalLibraryItem ? computeLibraryViewCapabilities(terminalLibraryItem, {
      job: job ?? undefined,
      manifest: reportManifest.result,
      manifestState: reportManifestState,
    }) : null),
    [terminalLibraryItem, job, reportManifest.result, reportManifestState],
  );

  // library origin 完成 CTA：轻量 capability 门控，不加载重产物；未就绪时至少给出主 CTA
  const libraryResultCtas = useMemo(() => {
    if (!libraryOrigin) return [];
    const base = `/library/${libraryOrigin.itemKind}/${encodeURIComponent(libraryOrigin.sourceId)}`;
    const candidates: { view: "analysis" | "trajectory" | "report" | "technical"; label: string; primary?: boolean; path: string; disabled?: boolean; reason?: string }[] = [
      { view: "analysis", label: "查看分析结果", primary: true, path: `${base}?view=analysis&analysisJob=${encodeURIComponent(jobId)}` },
      { view: "trajectory", label: "查看球路", path: `${base}?view=trajectory&analysisJob=${encodeURIComponent(jobId)}` },
      { view: "report", label: "查看报告", path: `${base}?view=report&analysisJob=${encodeURIComponent(jobId)}` },
      { view: "technical", label: "技术详情", path: `${base}?view=technical&analysisJob=${encodeURIComponent(jobId)}` },
    ];
    if (!terminalLibraryItem || !caps) return candidates.filter((c) => c.primary);
    return candidates
      .filter((c) => c.primary || c.view === "report" || caps[c.view] === "available")
      .map((c) => c.view === "report" && reportCapability.state !== "available"
        ? { ...c, disabled: true, reason: reportCapability.reason }
        : c);
  }, [libraryOrigin, terminalLibraryItem, caps, jobId, reportCapability]);

  const reanalyzePath = useMemo(
    () => (libraryOrigin && terminalLibraryItem ? libraryAnalysisPathFor(terminalLibraryItem) : null),
    [libraryOrigin, terminalLibraryItem],
  );

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    let isLoading = false;

    const scheduleLoad = (delay: number) => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      timer = window.setTimeout(() => {
        timer = undefined;
        void loadJob();
      }, delay);
    };

    const loadJob = async () => {
      if (!alive || isLoading) {
        return;
      }
      isLoading = true;
      try {
        const nextJob = await getAnalysisJob(jobId);
        if (!alive) {
          return;
        }

        setLoadError(null);
        setJob(nextJob);
        rememberAnalysisJob(nextJob);

        if (nextJob && ["uploaded", "queued", "processing"].includes(nextJob.status)) {
          scheduleLoad(1600);
        }
      } catch (error) {
        if (!alive) {
          return;
        }
        // 熄屏/网络短断不代表任务失败。保留最近一次的任务快照，并持续重试；
        // 唤醒时的 focus / visibilitychange 会触发一次立即对账。
        setLoadError(errorToNotice("任务状态暂时不可用", "正在等待后端恢复连接，任务不会因此被取消。", error));
        scheduleLoad(3000);
      } finally {
        isLoading = false;
      }
    };

    const reloadOnResume = () => {
      if (!alive || document.hidden) {
        return;
      }
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      void loadJob();
    };
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        reloadOnResume();
      }
    };

    void loadJob();
    window.addEventListener("focus", reloadOnResume);
    window.addEventListener("online", reloadOnResume);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      alive = false;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      window.removeEventListener("focus", reloadOnResume);
      window.removeEventListener("online", reloadOnResume);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [jobId]);

  if (job === undefined) {
    return <StatusState title="正在读取分析任务" body="正在连接后端或本地 mock 任务记录。" onNavigate={onNavigate} backPath={backPath} />;
  }

  if (loadError && job === null) {
    return <StatusState title={loadError.title} body={loadError.body} notice={loadError} onNavigate={onNavigate} backPath={backPath} />;
  }

  if (!job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，可能是本地记录已清空。`} onNavigate={onNavigate} backPath={backPath} />;
  }

  const statusCopy = {
    uploaded: "视频已接收",
    queued: "排队中",
    processing: "分析中",
    failed: "分析失败",
    completed: "分析完成",
    canceled: "任务已取消",
    interrupted: "任务失联",
  } satisfies Record<AnalysisJobSummary["status"], string>;

  const isCompleted = job.status === "completed";
  const isFailed = job.status === "failed";
  const isCanceled = job.status === "canceled";
  const isInterrupted = job.status === "interrupted";
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
  const visibleViewRuns = job.viewRuns && Object.keys(job.viewRuns).length > 0 ? job.viewRuns : null;

  return (
    <PageFrame>
      <section className="sport-card overflow-hidden">
        <div className="p-6 lg:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
              onClick={() => onNavigate(backPath)}
              type="button"
            >
              <ArrowLeft size={16} aria-hidden="true" />
              {backLabel}
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
            {libraryItem?.displayTitle ?? job.metadata.matchTitle} · {job.metadata.fileName} · {job.metadata.venue} · 任务 ID：{job.id}
          </p>

          {loadError && !isTerminal ? (
            <div className="mt-4">
              <DiagnosticNoticeCard notice={loadError} tone="info" />
            </div>
          ) : null}

          {isTerminal ? (
            <TerminalSummary
              isCompleted={isCompleted}
              isFailed={isFailed}
              isCanceled={isCanceled}
              isInterrupted={isInterrupted}
              job={job}
              completedStageCount={completedStageCount}
              totalDurationMs={totalDurationMs}
              currentStage={currentStage}
              onNavigate={onNavigate}
              contextualPath={contextualPath}
              backPath={backPath}
              backLabel={backLabel}
              isLibraryOrigin={isLibraryOrigin}
              libraryResultCtas={libraryResultCtas}
              reportCapability={reportCapability}
              reanalyzePath={reanalyzePath}
              captureResultPath={captureResultPath}
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

              {isMultiview && visibleViewRuns ? (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {Object.entries(visibleViewRuns).map(([view, run]) => (
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
            <button
              className="green-button shrink-0 px-4 py-2.5"
              onClick={() => {
                const target = isLibraryOrigin && libraryResultPath("technical")
                  ? libraryResultPath("technical")
                  : contextualPath(`/analysis/${job.id}/multiview`);
                onNavigate(target as NavigatePath, isLibraryOrigin ? { replace: true } : undefined);
              }}
              type="button"
            >
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
        {isInterrupted ? (
          <div className="mt-4">
            <DiagnosticNoticeCard
              notice={{
                title: "任务失联",
                body: job.publicErrorMessage ?? "Worker 在规定时间内没有心跳，已保留最后进度；可以重新分析。",
                detailItems: [
                  ["最后阶段", currentStage?.label ?? job.stage],
                  ["最后心跳", job.workerHeartbeatAt ? formatDateTime(job.workerHeartbeatAt) : undefined],
                  ["失联时间", job.interruptedAt ? formatDateTime(job.interruptedAt) : undefined],
                  ["中断原因", job.interruptionCode],
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
  isInterrupted,
  job,
  completedStageCount,
  totalDurationMs,
  currentStage,
  onNavigate,
  contextualPath,
  backPath,
  backLabel,
  isLibraryOrigin,
  libraryResultCtas,
  reportCapability,
  reanalyzePath,
  captureResultPath,
}: {
  isCompleted: boolean;
  isFailed: boolean;
  isCanceled: boolean;
  isInterrupted: boolean;
  job: AnalysisJobSummary;
  completedStageCount: number;
  totalDurationMs: number;
  currentStage: { label: string; detail?: string } | undefined;
  onNavigate: NavigateFn;
  contextualPath: (path: string) => NavigatePath;
  backPath: NavigatePath;
  backLabel: string;
  isLibraryOrigin: boolean;
  libraryResultCtas: { label: string; primary?: boolean; path: string; disabled?: boolean; reason?: string }[];
  reportCapability: ReportCapability;
  reanalyzePath: NavigatePath | null;
  captureResultPath: string | null;
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
            <p className="mt-1 text-sm leading-6 text-slate-600">
              {reportCapability.state === "available"
                ? "报告已生成，可以查看视频分析或指标详情。"
                : `任务完成，但暂无有效报告数据：${reportCapability.reason}`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {isLibraryOrigin ? (
              <>
                {libraryResultCtas.map((cta) => (
                  <button
                    className={cta.primary ? "green-button px-4 py-2.5" : "quiet-button px-4 py-2.5"}
                    disabled={cta.disabled}
                    key={cta.label}
                    onClick={() => onNavigate(cta.path as NavigatePath, { replace: true })}
                    title={cta.reason}
                    type="button"
                  >
                    {cta.label}
                    {cta.primary ? <ArrowRight size={16} aria-hidden="true" /> : null}
                  </button>
                ))}
              </>
            ) : (
              <>
                <button
                  className="green-button px-4 py-2.5"
                  onClick={() => onNavigate((captureResultPath ?? contextualPath(`/analysis/${job.id}/vision`)) as NavigatePath)}
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
                    disabled={!isCompleted || reportCapability.state !== "available"}
                    key={action.type}
                    onClick={() => onNavigate(contextualPath(`/analysis/${job.id}/reports/${action.type}`))}
                    title={reportCapability.state === "available" ? undefined : reportCapability.reason}
                    type="button"
                  >
                    {action.title}
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      ) : isInterrupted ? (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-bold text-[#A45A00]">任务失联 · 已保留最后进度</p>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              {job.publicErrorMessage ?? "Worker 在规定时间内没有心跳，可以重新分析。"}
              {job.workerHeartbeatAt ? ` 最后心跳：${formatDateTime(job.workerHeartbeatAt)}。` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="green-button px-4 py-2.5" onClick={() => onNavigate(reanalyzePath ?? contextualPath("/analysis/new"))} type="button">
              重新分析
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(backPath)} type="button">
              {backLabel}
            </button>
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
            {isLibraryOrigin ? (
              <>
                <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(backPath)} type="button">
                  {backLabel}
                </button>
                {reanalyzePath ? (
                  <button className="green-button px-4 py-2.5" onClick={() => onNavigate(reanalyzePath)} type="button">
                    再次分析
                    <ArrowRight size={16} aria-hidden="true" />
                  </button>
                ) : null}
              </>
            ) : (
              <>
                <button className="green-button px-4 py-2.5" onClick={() => onNavigate(contextualPath("/analysis/new"))} type="button">
                  {isCanceled ? "新建分析" : "重新上传"}
                </button>
                <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(backPath)} type="button">
                  {backLabel}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
