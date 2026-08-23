import { useState, useEffect } from "react";
import { ArrowRight, BadgeCheck, Brain, Camera, ChevronRight, Layers, LineChart, Route, Timer } from "lucide-react";
import type { NavigateFn, AppPath, NavigatePath, ReportType } from "../app/navigationTypes";
import type { AnalysisJobSummary, AnalysisPipelineResult, AnalysisReport, VisualizationManifest, BallTrajectoryArtifact, BounceEventsArtifact, PoseOverlayArtifact, ServeEventsArtifact, TrackingOverlayArtifact, FusedPlayerOverlayArtifact, StructuredVisualizationData } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { RailMeta } from "../components/RailMeta";
import { StatusState } from "../components/StatusState";
import { VideoAnalysisCard } from "../components/platform/VideoAnalysisCard";
import { MetricCard } from "../components/platform/MetricCard";
import { SkillRatings } from "../components/platform/SkillRatings";
import { PlayerScoringPanel } from "../components/platform/PlayerScoringPanel";
import { RecommendedDrills } from "../components/RecommendedDrills";
import { ProgressChart } from "../components/platform/ProgressChart";
import StructuredHeatmap from "../components/platform/StructuredHeatmap";
import StructuredScatterPlot from "../components/platform/StructuredScatterPlot";
import StructuredZoneHeatmap from "../components/platform/StructuredZoneHeatmap";
import { supportedReportTypes } from "../app/router";
import { taskContextForJob, taskListPathForJob, withTaskListContext } from "../app/navigationContext";
import type { LibraryView } from "../components/library/viewCapabilities";
import { demoAnalysisReport as demoReport, getAnalysisJob, getAnalysisReport, getAnalysisResult, getVideoStreamUrl, getStructuredVizData, resolveAnalysisAssetUrl, getBallTrajectory, getBounceEvents, getPoseOverlay, getServeEvents, getTrackingOverlay, getFusedPlayerOverlay, getAnalysisOverlayVideoUrl, getPositionHeatmaps, getPositionScatterPlots } from "../services/analysisClient";
import { isPipelineResult } from "../services/pipelineReportAdapter";
import { errorToNotice, analysisStatusMeta, analysisModeLabel, formatDateTime, toneStyles, buildPlayerRoster } from "../utils/analysisHelpers";

type OverlayLoadState = "idle" | "loading" | "available" | "unavailable" | "failed";

function useVisualAnalysisReport(jobId?: string) {
  const [loadedResult, setLoadedResult] = useState<{
    error: DiagnosticNotice | null;
    ballTrajectory: BallTrajectoryArtifact | null;
    ballTrajectoryLoadState: OverlayLoadState;
    bounceEvents: BounceEventsArtifact | null;
    bounceEventsLoadState: OverlayLoadState;
    job: AnalysisJobSummary | null;
    jobId: string;
    heatmapsManifest: VisualizationManifest | null;
    heatmapsLoadState: OverlayLoadState;
    overlayVideoSrc?: string;
    poseOverlay: PoseOverlayArtifact | null;
    poseOverlayLoadState: OverlayLoadState;
    report: AnalysisReport | null;
    result: AnalysisPipelineResult | null;
    scatterManifest: VisualizationManifest | null;
    scatterLoadState: OverlayLoadState;
    serveEvents: ServeEventsArtifact | null;
    serveEventsLoadState: OverlayLoadState;
    trackingOverlay: TrackingOverlayArtifact | null;
    trackingOverlayLoadState: OverlayLoadState;
    fusedPlayerOverlay: FusedPlayerOverlayArtifact | null;
    fusedPlayerOverlayLoadState: OverlayLoadState;
    videoSrc?: string;
  } | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let alive = true;

    const setOverlayState = (
      updates: Partial<{
        poseOverlay: PoseOverlayArtifact | null;
        poseOverlayLoadState: OverlayLoadState;
        ballTrajectory: BallTrajectoryArtifact | null;
        ballTrajectoryLoadState: OverlayLoadState;
        bounceEvents: BounceEventsArtifact | null;
        bounceEventsLoadState: OverlayLoadState;
        serveEvents: ServeEventsArtifact | null;
        serveEventsLoadState: OverlayLoadState;
        trackingOverlay: TrackingOverlayArtifact | null;
        trackingOverlayLoadState: OverlayLoadState;
        fusedPlayerOverlay: FusedPlayerOverlayArtifact | null;
        fusedPlayerOverlayLoadState: OverlayLoadState;
        heatmapsManifest: VisualizationManifest | null;
        heatmapsLoadState: OverlayLoadState;
        scatterManifest: VisualizationManifest | null;
        scatterLoadState: OverlayLoadState;
      }>
    ) => {
      if (!alive) {
        return;
      }
      setLoadedResult((current) => (current?.jobId === jobId ? { ...current, ...updates } : current));
    };

    const load = async () => {
      try {
        const [nextJob, nextReport, nextResult] = await Promise.all([getAnalysisJob(jobId), getAnalysisReport(jobId), getAnalysisResult(jobId)]);
        const pipelineResult = isPipelineResult(nextResult) ? nextResult : null;
        // real-job 报告只消费权威 /report API；报告缺失时走显式"报告尚未生成"状态，
        // 不再前端拼装近似报告（pipelineReportAdapter 已 deprecated）。
        const adaptedReport = nextReport ?? null;
        const shouldLoadTracking = Boolean(pipelineResult?.artifacts.tracking_overlay_url);
        const shouldLoadFused = Boolean(pipelineResult?.artifacts.fused_player_overlay_url);
        const shouldLoadPose = Boolean(pipelineResult?.artifacts.pose_overlay_url);
        const shouldLoadServeEvents = Boolean(pipelineResult?.artifacts.serve_events_url);
        const shouldLoadBallTrajectory = Boolean(pipelineResult?.artifacts.cleaned_ball_trajectory_url ?? pipelineResult?.artifacts.ball_trajectory_url);
        const shouldLoadBounceEvents = Boolean(pipelineResult?.artifacts.bounce_events_url);
        const shouldLoadHeatmaps = Boolean(pipelineResult?.artifacts.heatmaps_url);
        const shouldLoadScatter = Boolean(pipelineResult?.artifacts.scatter_plots_url);

        if (!alive) {
          return;
        }

        setLoadedResult({
          error: null,
          ballTrajectory: null,
          ballTrajectoryLoadState: shouldLoadBallTrajectory ? "loading" : "unavailable",
          bounceEvents: null,
          bounceEventsLoadState: shouldLoadBounceEvents ? "loading" : "unavailable",
          heatmapsManifest: null,
          heatmapsLoadState: shouldLoadHeatmaps ? "loading" : "unavailable",
          job: nextJob,
          jobId,
          overlayVideoSrc: pipelineResult ? getAnalysisOverlayVideoUrl(pipelineResult) : undefined,
          poseOverlay: null,
          poseOverlayLoadState: shouldLoadPose ? "loading" : "unavailable",
          report: adaptedReport,
          result: pipelineResult,
          scatterManifest: null,
          scatterLoadState: shouldLoadScatter ? "loading" : "unavailable",
          serveEvents: null,
          serveEventsLoadState: shouldLoadServeEvents ? "loading" : "unavailable",
          trackingOverlay: null,
          trackingOverlayLoadState: shouldLoadTracking ? "loading" : "unavailable",
          fusedPlayerOverlay: null,
          fusedPlayerOverlayLoadState: shouldLoadFused ? "loading" : "unavailable",
          videoSrc: getVideoStreamUrl(pipelineResult?.video_id ?? nextJob?.videoId),
        });

        if (pipelineResult && shouldLoadTracking) {
          getTrackingOverlay(pipelineResult)
            .then((overlay) => {
              setOverlayState({
                trackingOverlay: overlay,
                trackingOverlayLoadState: overlay ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                trackingOverlay: null,
                trackingOverlayLoadState: "failed",
              });
            });
        }

        if (pipelineResult && shouldLoadFused) {
          getFusedPlayerOverlay(pipelineResult)
            .then((overlay) => {
              setOverlayState({
                fusedPlayerOverlay: overlay,
                fusedPlayerOverlayLoadState: overlay ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                fusedPlayerOverlay: null,
                fusedPlayerOverlayLoadState: "failed",
              });
            });
        }

        if (pipelineResult && shouldLoadBallTrajectory) {
          getBallTrajectory(pipelineResult)
            .then((artifact) => {
              setOverlayState({
                ballTrajectory: artifact,
                ballTrajectoryLoadState: artifact ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                ballTrajectory: null,
                ballTrajectoryLoadState: "failed",
              });
            });
        }

        if (pipelineResult && shouldLoadBounceEvents) {
          getBounceEvents(pipelineResult)
            .then((artifact) => {
              setOverlayState({
                bounceEvents: artifact,
                bounceEventsLoadState: artifact ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                bounceEvents: null,
                bounceEventsLoadState: "failed",
              });
            });
        }

        if (pipelineResult && shouldLoadPose) {
          getPoseOverlay(pipelineResult)
            .then((overlay) => {
              setOverlayState({
                poseOverlay: overlay,
                poseOverlayLoadState: overlay ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                poseOverlay: null,
                poseOverlayLoadState: "failed",
              });
            });
        }

        if (pipelineResult && shouldLoadServeEvents) {
          getServeEvents(pipelineResult)
            .then((artifact) => {
              setOverlayState({
                serveEvents: artifact,
                serveEventsLoadState: artifact ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                serveEvents: null,
                serveEventsLoadState: "failed",
              });
            });
        }

        if (pipelineResult && shouldLoadHeatmaps) {
          getPositionHeatmaps(pipelineResult)
            .then((manifest) => {
              setOverlayState({
                heatmapsManifest: manifest,
                heatmapsLoadState: manifest ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                heatmapsManifest: null,
                heatmapsLoadState: "failed",
              });
            });
        }

        if (pipelineResult && shouldLoadScatter) {
          getPositionScatterPlots(pipelineResult)
            .then((manifest) => {
              setOverlayState({
                scatterManifest: manifest,
                scatterLoadState: manifest ? "available" : "unavailable",
              });
            })
            .catch(() => {
              setOverlayState({
                scatterManifest: null,
                scatterLoadState: "failed",
              });
            });
        }
      } catch (error) {
        if (alive) {
          setLoadedResult({
            error: errorToNotice("读取分析结果失败", "无法读取该任务生成的报告或算法结果，请检查后端服务和任务产物。", error),
            ballTrajectory: null,
            ballTrajectoryLoadState: "unavailable",
            bounceEvents: null,
            bounceEventsLoadState: "unavailable",
            heatmapsManifest: null,
            heatmapsLoadState: "unavailable",
            job: null,
            jobId,
            overlayVideoSrc: undefined,
            poseOverlay: null,
            poseOverlayLoadState: "unavailable",
            report: null,
            result: null,
            scatterManifest: null,
            scatterLoadState: "unavailable",
            serveEvents: null,
            serveEventsLoadState: "unavailable",
            trackingOverlay: null,
            trackingOverlayLoadState: "unavailable",
            fusedPlayerOverlay: null,
            fusedPlayerOverlayLoadState: "unavailable",
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
    return {
      error: null,
      ballTrajectory: null,
      ballTrajectoryLoadState: "idle" as OverlayLoadState,
      bounceEvents: null,
      bounceEventsLoadState: "idle" as OverlayLoadState,
      heatmapsManifest: null,
      heatmapsLoadState: "idle" as OverlayLoadState,
      job: null,
      overlayVideoSrc: undefined,
      poseOverlay: null,
      poseOverlayLoadState: "idle" as OverlayLoadState,
      report: demoReport,
      result: null,
      scatterManifest: null,
      scatterLoadState: "idle" as OverlayLoadState,
      serveEvents: null,
      serveEventsLoadState: "idle" as OverlayLoadState,
      trackingOverlay: null,
      trackingOverlayLoadState: "idle" as OverlayLoadState,
      fusedPlayerOverlay: null,
      fusedPlayerOverlayLoadState: "idle" as OverlayLoadState,
      videoSrc: undefined,
    };
  }

  if (loadedResult?.jobId !== jobId) {
    return {
      error: null,
      ballTrajectory: undefined,
      ballTrajectoryLoadState: "idle" as OverlayLoadState,
      bounceEvents: undefined,
      bounceEventsLoadState: "idle" as OverlayLoadState,
      heatmapsManifest: undefined,
      heatmapsLoadState: "idle" as OverlayLoadState,
      job: undefined,
      overlayVideoSrc: undefined,
      poseOverlay: undefined,
      poseOverlayLoadState: "idle" as OverlayLoadState,
      report: undefined,
      result: undefined,
      scatterManifest: undefined,
      scatterLoadState: "idle" as OverlayLoadState,
      serveEvents: undefined,
      serveEventsLoadState: "idle" as OverlayLoadState,
      trackingOverlay: undefined,
      trackingOverlayLoadState: "idle" as OverlayLoadState,
      fusedPlayerOverlay: undefined,
      fusedPlayerOverlayLoadState: "idle" as OverlayLoadState,
      videoSrc: undefined,
    };
  }

  return {
    error: loadedResult.error,
    ballTrajectory: loadedResult.ballTrajectory,
    ballTrajectoryLoadState: loadedResult.ballTrajectoryLoadState,
    bounceEvents: loadedResult.bounceEvents,
    bounceEventsLoadState: loadedResult.bounceEventsLoadState,
    heatmapsManifest: loadedResult.heatmapsManifest,
    heatmapsLoadState: loadedResult.heatmapsLoadState,
    job: loadedResult.job,
    overlayVideoSrc: loadedResult.overlayVideoSrc,
    poseOverlay: loadedResult.poseOverlay,
    poseOverlayLoadState: loadedResult.poseOverlayLoadState,
    report: loadedResult.report,
    result: loadedResult.result,
    scatterManifest: loadedResult.scatterManifest,
    scatterLoadState: loadedResult.scatterLoadState,
    serveEvents: loadedResult.serveEvents,
    serveEventsLoadState: loadedResult.serveEventsLoadState,
    trackingOverlay: loadedResult.trackingOverlay,
    trackingOverlayLoadState: loadedResult.trackingOverlayLoadState,
    fusedPlayerOverlay: loadedResult.fusedPlayerOverlay,
    fusedPlayerOverlayLoadState: loadedResult.fusedPlayerOverlayLoadState,
    videoSrc: loadedResult.videoSrc,
  };
}

export function VisionPage({ jobId, onNavigate, recentJob, seekToMs, embedded, onSelectView }: { jobId?: string; onNavigate: NavigateFn; recentJob?: AnalysisJobSummary | null; seekToMs?: number; embedded?: boolean; onSelectView?: (view: LibraryView) => void }) {
  const {
    error,
    ballTrajectory,
    ballTrajectoryLoadState,
    bounceEvents,
    bounceEventsLoadState,
    heatmapsManifest,
    heatmapsLoadState,
    job,
    overlayVideoSrc,
    poseOverlay,
    poseOverlayLoadState,
    report,
    result,
    scatterManifest,
    scatterLoadState,
    serveEvents,
    serveEventsLoadState,
    trackingOverlay,
    trackingOverlayLoadState,
    fusedPlayerOverlay,
    fusedPlayerOverlayLoadState,
    videoSrc,
  } = useVisualAnalysisReport(jobId);
  const taskReturnPath = taskListPathForJob(job);

  if (jobId && (job === undefined || report === undefined)) {
    if (embedded) {
      return <div className="grid min-h-[50vh] place-items-center text-sm text-[var(--capture-text-muted,#8f9d96)]">正在加载视觉分析…</div>;
    }
    return <StatusState title="正在加载视觉分析" body="正在读取该任务生成的分析报告。" onNavigate={onNavigate} backPath={taskReturnPath} />;
  }

  if (jobId && error) {
    if (embedded) {
      return <div className="grid min-h-[50vh] place-items-center px-6 text-center text-sm text-[var(--capture-text-muted,#8f9d96)]">{error.body}</div>;
    }
    return <StatusState title={error.title} body={error.body} notice={error} onNavigate={onNavigate} backPath={taskReturnPath} />;
  }

  if (jobId && !job) {
    if (embedded) {
      return <div className="grid min-h-[50vh] place-items-center px-6 text-center text-sm text-[var(--capture-text-muted,#8f9d96)]">未找到该分析任务。</div>;
    }
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，无法打开视觉分析。`} onNavigate={onNavigate} backPath={taskReturnPath} />;
  }

  if (job && job.status !== "completed") {
    const canceled = job.status === "canceled";
    return (
      <StatusState
        title={job.status === "failed" ? "分析任务失败" : canceled ? "分析任务已取消" : "视觉分析尚未生成"}
        body={
          job.status === "failed"
            ? job.publicErrorMessage ?? job.errorMessage ?? "请重新上传或检查后端日志。"
            : canceled
              ? "任务在完成前被取消，因此不会开放视频分析工作台。"
              : "任务还在排队或处理中，完成后会开放视频分析工作台。"
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
                  body: "任务取消后保留执行记录，但不会生成可播放分析结果。",
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
  const sourceLabel =
    analysis.source === "demo"
      ? "样例数据"
      : job?.analysisMode === "limited"
        ? `有限真实分析 · 任务 ${analysis.jobId}`
        : `真实上传视频 · 任务 ${analysis.jobId}`;
  const reportPath = (type: ReportType) => analysis.jobId
    ? withTaskListContext(`/analysis/${analysis.jobId}/reports/${type}`, taskContextForJob(job))
    : `/reports/${type}` as AppPath;
  const contextualPath = (path: string) => withTaskListContext(path, taskContextForJob(job));
  const supportedActions = analysis.reportActions.filter((action) => supportedReportTypes.includes(action.type));

      if (jobId) {
    return (
      <PageFrame>
        {!embedded && (
          <section className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <button
                className="mb-5 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
                onClick={() => onNavigate(taskReturnPath)}
                type="button"
              >
                <ArrowRight className="rotate-180" size={16} aria-hidden="true" />
                返回任务管理
              </button>
              <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
                <Camera size={16} aria-hidden="true" />
                智能视频分析
              </p>
              <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">视频分析结果</h1>
              <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
                当前数据来源：{sourceLabel}。详细报告已收纳到右侧下级标签中，主画面只保留视频和状态。
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              {job?.analysisKind === "multiview" && job?.status === "completed" && (
                <button
                  className="green-button inline-flex min-h-11 items-center justify-center gap-2 px-4 py-2.5 lg:shrink-0"
                  onClick={() => (embedded && onSelectView ? onSelectView("technical") : onNavigate(contextualPath(`/analysis/${jobId}/multiview`)))}
                  type="button"
                >
                  <Layers size={17} aria-hidden="true" />
                  查看双摄协同详情
                </button>
              )}
              <button
                className="quiet-button inline-flex min-h-11 items-center justify-center gap-2 px-4 py-2.5 lg:shrink-0"
                onClick={() => (embedded && onSelectView ? onSelectView("trajectory") : onNavigate(contextualPath(`/analysis/${jobId}/trajectory`)))}
                type="button"
              >
                <Route size={17} aria-hidden="true" />
                查看球路
              </button>
            </div>
          </section>
        )}

        {job?.analysisKind === "multiview" && result && (
          <section className="mb-5 flex flex-col gap-3 rounded-xl border border-[#DDE5E0] bg-[#F8FAF9] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <Route className="mt-0.5 shrink-0 text-[#168A34]" size={18} aria-hidden="true" />
              <div>
                <h2 className="text-sm font-bold text-[#182230]">双摄球路分析</h2>
                <p className="mt-1 text-xs leading-5 text-[#667085]">
                  {result.artifacts.reconstructed_ball_trajectory_detail ?? "球路状态由 Parent 分析结果统一发布。"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-bold text-[#344054]">
                {result.artifacts.reconstructed_ball_trajectory_status ?? "unavailable"}
              </span>
              <button
                className="quiet-button inline-flex min-h-9 items-center gap-2 px-3 py-2 text-xs"
                onClick={() => (embedded && onSelectView ? onSelectView("trajectory") : onNavigate(contextualPath(`/analysis/${jobId}/trajectory`)))}
                type="button"
              >
                查看球路
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            </div>
          </section>
        )}

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_380px]">
          <div className="grid gap-5">
            <VideoAnalysisCard
              labels={analysis.videoOverlayLabels}
              ballTrajectory={ballTrajectory ?? null}
              ballTrajectoryDetail={result?.artifacts.cleaned_ball_trajectory_detail ?? result?.artifacts.ball_trajectory_detail}
              ballTrajectoryLoadState={ballTrajectoryLoadState}
              ballTrajectoryStatus={result?.artifacts.cleaned_ball_trajectory_status ?? result?.artifacts.ball_trajectory_status}
              bounceEvents={bounceEvents ?? null}
              bounceEventsDetail={result?.artifacts.bounce_events_detail}
              bounceEventsLoadState={bounceEventsLoadState}
              bounceEventsStatus={result?.artifacts.bounce_events_status}
              match={analysis.match}
              players={analysis.playerMarkers}
              poseOverlayDetail={result?.artifacts.pose_overlay_detail}
              poseOverlayLoadState={poseOverlayLoadState}
              poseOverlayStatus={result?.artifacts.pose_overlay_status}
              poseOverlay={poseOverlay ?? null}
              serveEvents={serveEvents ?? null}
              serveEventsDetail={result?.artifacts.serve_events_detail}
              serveEventsLoadState={serveEventsLoadState}
              serveEventsStatus={result?.artifacts.serve_events_status}
              timeline={analysis.timelineMarkers}
              trackingOverlayDetail={result?.artifacts.tracking_overlay_detail}
              trackingOverlayLoadState={trackingOverlayLoadState}
              trackingOverlayStatus={result?.artifacts.tracking_overlay_status}
              trackingOverlay={trackingOverlay ?? null}
              fusedPlayerOverlayDetail={result?.artifacts.fused_player_overlay_detail}
              fusedPlayerOverlayLoadState={fusedPlayerOverlayLoadState}
              fusedPlayerOverlayStatus={result?.artifacts.fused_player_overlay_status}
              fusedPlayerOverlay={fusedPlayerOverlay ?? null}
              // 优先使用 H.264 源视频（浏览器原生支持）；overlay 视频（mpeg4 编码）作为增强层
              videoSrc={videoSrc ?? undefined}
              fallbackVideoSrc={overlayVideoSrc ?? undefined}
              pipelineTracks={result?.tracks}
              seekToMs={seekToMs}
            />
            <VisualizationArtifactGallery
              heatmapsManifest={heatmapsManifest ?? null}
              heatmapsLoadState={heatmapsLoadState}
              heatmapsStatus={result?.artifacts.position_visualizations_status}
              heatmapsDetail={result?.artifacts.position_visualizations_detail}
              scatterManifest={scatterManifest ?? null}
              scatterLoadState={scatterLoadState}
              scatterStatus={result?.artifacts.position_visualizations_status}
              scatterDetail={result?.artifacts.position_visualizations_detail}
              jobId={jobId}
            />
          </div>
          <AnalysisStatusRail
            analysis={analysis}
            ballTrajectory={ballTrajectory ?? null}
            ballTrajectoryLoadState={ballTrajectoryLoadState}
            bounceEvents={bounceEvents ?? null}
            bounceEventsLoadState={bounceEventsLoadState}
            job={job}
            onNavigate={onNavigate}
            embedded={embedded}
            onSelectView={onSelectView}
            poseOverlay={poseOverlay ?? null}
            poseOverlayLoadState={poseOverlayLoadState}
            reportPath={reportPath}
            result={result}
            heatmapsManifest={heatmapsManifest ?? null}
            heatmapsLoadState={heatmapsLoadState}
            scatterManifest={scatterManifest ?? null}
            scatterLoadState={scatterLoadState}
            serveEvents={serveEvents ?? null}
            serveEventsLoadState={serveEventsLoadState}
            trackingOverlay={trackingOverlay ?? null}
            trackingOverlayLoadState={trackingOverlayLoadState}
          />
        </section>

        <section className="mt-6">
          <PlayerScoringPanel
            roster={buildPlayerRoster(result?.tracks, result?.match_context?.expected_player_count)}
          />
        </section>
      </PageFrame>
    );
  }

  return (
    <PageFrame>
      <section className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Camera size={16} aria-hidden="true" />
            智能视频分析
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">比赛分析工作台</h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
            视频回放是入口，报告和训练建议是下一步。当前数据来源：{sourceLabel}。
          </p>
          {!jobId && recentJob ? (
            <div className="mt-5 inline-flex flex-wrap items-center gap-3 rounded-2xl border border-[#22C55E]/25 bg-white/85 px-4 py-3 shadow-sm">
              <span className="text-sm font-semibold text-slate-600">
                最近分析：{recentJob.metadata.matchTitle} · {recentJob.metadata.fileName}
              </span>
              <button
                className="green-button px-4 py-2 text-xs"
                onClick={() => onNavigate(withTaskListContext(`/analysis/${recentJob.id}/vision`, taskContextForJob(recentJob)))}
                type="button"
              >
                回到刚刚的结果
              </button>
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-3">
          {supportedActions.map((action) => (
            <button
              className="quiet-button px-4 py-2.5"
              key={action.type}
              onClick={() => onNavigate(reportPath(action.type))}
              type="button"
            >
              {action.title}
            </button>
          ))}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="grid gap-5">
          <VideoAnalysisCard
            labels={analysis.videoOverlayLabels}
            ballTrajectory={ballTrajectory ?? null}
            ballTrajectoryDetail={result?.artifacts.cleaned_ball_trajectory_detail ?? result?.artifacts.ball_trajectory_detail}
            ballTrajectoryLoadState={ballTrajectoryLoadState}
            ballTrajectoryStatus={result?.artifacts.cleaned_ball_trajectory_status ?? result?.artifacts.ball_trajectory_status}
            bounceEvents={bounceEvents ?? null}
            bounceEventsDetail={result?.artifacts.bounce_events_detail}
            bounceEventsLoadState={bounceEventsLoadState}
            bounceEventsStatus={result?.artifacts.bounce_events_status}
            match={analysis.match}
            players={analysis.playerMarkers}
            poseOverlayDetail={result?.artifacts.pose_overlay_detail}
            poseOverlayLoadState={poseOverlayLoadState}
            poseOverlayStatus={result?.artifacts.pose_overlay_status}
            poseOverlay={poseOverlay ?? null}
            serveEvents={serveEvents ?? null}
            serveEventsDetail={result?.artifacts.serve_events_detail}
            serveEventsLoadState={serveEventsLoadState}
            serveEventsStatus={result?.artifacts.serve_events_status}
            timeline={analysis.timelineMarkers}
            trackingOverlayDetail={result?.artifacts.tracking_overlay_detail}
            trackingOverlayLoadState={trackingOverlayLoadState}
            trackingOverlayStatus={result?.artifacts.tracking_overlay_status}
            trackingOverlay={trackingOverlay ?? null}
            fusedPlayerOverlayDetail={result?.artifacts.fused_player_overlay_detail}
            fusedPlayerOverlayLoadState={fusedPlayerOverlayLoadState}
            fusedPlayerOverlayStatus={result?.artifacts.fused_player_overlay_status}
            fusedPlayerOverlay={fusedPlayerOverlay ?? null}
            // 优先使用 H.264 源视频（浏览器原生支持）；overlay 视频（mpeg4 编码）作为增强层
            videoSrc={videoSrc ?? undefined}
            fallbackVideoSrc={overlayVideoSrc ?? undefined}
            pipelineTracks={result?.tracks}
          />
          {analysis.source === "job" ? (
            <VisualizationArtifactGallery
              heatmapsManifest={heatmapsManifest ?? null}
              heatmapsLoadState={heatmapsLoadState}
              heatmapsStatus={result?.artifacts.position_visualizations_status}
              heatmapsDetail={result?.artifacts.position_visualizations_detail}
              scatterManifest={scatterManifest ?? null}
              scatterLoadState={scatterLoadState}
              scatterStatus={result?.artifacts.position_visualizations_status}
              scatterDetail={result?.artifacts.position_visualizations_detail}
              jobId={jobId}
            />
          ) : null}
        </div>
        <aside className="grid gap-5">
          <CoachNotesCard notes={analysis.coachNotes} />
          <HighlightsCard highlights={analysis.highlights} onNavigate={onNavigate} reportPath={reportPath} />
        </aside>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {supportedActions.map((action) => (
          <button
            className="sport-card group p-5 text-left transition hover:-translate-y-1 hover:border-[#22C55E]/35"
            key={action.type}
            onClick={() => onNavigate(reportPath(action.type))}
            type="button"
          >
            <span className="grid size-10 place-items-center rounded-2xl border border-[#22C55E]/25 bg-[#22C55E]/12 text-[#168A34]">
              <LineChart size={18} aria-hidden="true" />
            </span>
            <strong className="mt-4 block text-lg font-black text-[#14241B]">{action.title}</strong>
            <p className="mt-2 text-sm leading-6 text-slate-600">{action.description}</p>
            <span className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-slate-700 group-hover:text-[#168A34]">
              查看报告
              <ArrowRight size={15} aria-hidden="true" />
            </span>
          </button>
        ))}
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {analysis.dashboardMetrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      <div className="mt-6 grid gap-6">
        <SkillRatings ratings={analysis.skillRatings} />
        <RecommendedDrills drills={analysis.drillRecommendations} onNavigate={onNavigate} />
        <ProgressChart points={analysis.progressPoints} />
      </div>
    </PageFrame>
  );
}

function VisualizationArtifactGallery({
  heatmapsManifest,
  heatmapsLoadState,
  heatmapsStatus,
  heatmapsDetail,
  scatterManifest,
  scatterLoadState,
  scatterStatus,
  scatterDetail,
  jobId,
}: {
  heatmapsManifest: VisualizationManifest | null;
  heatmapsLoadState: OverlayLoadState;
  heatmapsStatus?: string;
  heatmapsDetail?: string;
  scatterManifest: VisualizationManifest | null;
  scatterLoadState: OverlayLoadState;
  scatterStatus?: string;
  scatterDetail?: string;
  jobId?: string;
}) {
  const [structuredViz, setStructuredViz] = useState<StructuredVisualizationData | null>(null);
  useEffect(() => {
    if (!jobId) return;
    getStructuredVizData(jobId)
      .then((data) => {
        setStructuredViz(data);
      })
      .catch(() => {
        setStructuredViz(null);
      });
  }, [jobId]);

  const hasStructuredHeatmap = !!(structuredViz?.heatmaps?.visual_grid?.cells.length);
  const hasStructuredScatter = !!(structuredViz?.scatter_plots.players?.length || structuredViz?.scatter_plots.ball?.length || structuredViz?.scatter_plots.bounces?.length);
  const hasZoneStats = !!(structuredViz?.zone_stats?.players?.length);

  const groups = [
    {
      title: "位置热力图",
      manifest: heatmapsManifest,
      loadState: heatmapsLoadState,
      status: heatmapsStatus,
      detail: heatmapsDetail,
      structuredKey: "heatmap" as const,
      hasStructured: hasStructuredHeatmap,
    },
    {
      title: "位置散点图",
      manifest: scatterManifest,
      loadState: scatterLoadState,
      status: scatterStatus,
      detail: scatterDetail,
      structuredKey: "scatter" as const,
      hasStructured: hasStructuredScatter,
    },
    {
      title: "区域空间热力图",
      manifest: undefined,
      loadState: "unavailable" as const,
      status: undefined,
      detail: "暂无区域统计",
      structuredKey: "zone" as const,
      hasStructured: hasZoneStats,
    },
  ];

  const hasAnyItems = groups.some((group) => (group.manifest?.items.length ?? 0) > 0 || group.hasStructured);
  if (!hasAnyItems && groups.every((group) => group.loadState === "unavailable" || group.status === "skipped" || !group.status)) {
    return null;
  }

  const structuredData = structuredViz;

  return (
    <section className="sport-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">可视化产物</p>
          <h2 className="mt-2 text-xl font-black text-[#14241B]">热力图与散点图</h2>
        </div>
        <LineChart className="text-[#168A34]" size={22} aria-hidden="true" />
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {groups.map((group) => {
          const status = overlayLayerStatus(group.loadState, group.manifest?.status ?? group.status);
          const meta = overlayStatusMeta(status);
          const items = group.manifest?.items ?? [];
          const firstPngUrl = items.length > 0 ? resolveAnalysisAssetUrl(items[0].url) : undefined;

          if (group.hasStructured && structuredData) {
            return (
              <article className="rounded-2xl border border-[#DDE9D6] bg-white/75 p-4" key={group.title}>
                <div className="flex items-center justify-between gap-3">
                  <strong className="text-sm text-[#14241B]">{group.title}</strong>
                  <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-black text-green-700">SVG</span>
                </div>
                <div className="mt-4">
                  {group.structuredKey === "heatmap" ? (
                    <StructuredHeatmap data={structuredData} fallbackPngUrl={firstPngUrl} />
                  ) : group.structuredKey === "zone" ? (
                    <StructuredZoneHeatmap data={structuredData} />
                  ) : (
                    <StructuredScatterPlot data={structuredData} fallbackPngUrl={firstPngUrl} />
                  )}
                </div>
              </article>
            );
          }

          return (
            <article className="rounded-2xl border border-[#DDE9D6] bg-white/75 p-4" key={group.title}>
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm text-[#14241B]">{group.title}</strong>
                <span className={`rounded-full px-2.5 py-1 text-xs font-black ${meta.className}`}>{meta.label}</span>
              </div>
              {items.length > 0 ? (
                <div className="mt-4 grid gap-3">
                  {items.map((item) => (
                    <figure className="overflow-hidden rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1]" key={item.id}>
                      <img
                        alt={item.title || item.label}
                        className="aspect-[11/16] w-full bg-white object-contain"
                        src={resolveAnalysisAssetUrl(item.url)}
                      />
                      <figcaption className="border-t border-[#DDE9D6] bg-white/80 p-3">
                        <strong className="block text-sm text-[#14241B]">{item.title || item.label}</strong>
                        <p className="mt-1 text-xs leading-5 text-slate-500">{item.description}</p>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-sm leading-6 text-slate-500">{group.manifest?.detail ?? group.detail ?? meta.detail}</p>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function AnalysisStatusRail({
  analysis,
  ballTrajectory,
  ballTrajectoryLoadState,
  bounceEvents,
  bounceEventsLoadState,
  heatmapsManifest,
  heatmapsLoadState,
  job,
  onNavigate,
  embedded,
  onSelectView,
  poseOverlay,
  poseOverlayLoadState,
  reportPath,
  result,
  scatterManifest,
  scatterLoadState,
  serveEvents,
  serveEventsLoadState,
  trackingOverlay,
  trackingOverlayLoadState,
}: {
  analysis: AnalysisReport;
  ballTrajectory: BallTrajectoryArtifact | null;
  ballTrajectoryLoadState: OverlayLoadState;
  bounceEvents: BounceEventsArtifact | null;
  bounceEventsLoadState: OverlayLoadState;
  heatmapsManifest: VisualizationManifest | null;
  heatmapsLoadState: OverlayLoadState;
  job?: AnalysisJobSummary | null;
  onNavigate: NavigateFn;
  embedded?: boolean;
  onSelectView?: (view: LibraryView) => void;
  poseOverlay: PoseOverlayArtifact | null;
  poseOverlayLoadState: OverlayLoadState;
  reportPath: (type: ReportType) => NavigatePath;
  result?: AnalysisPipelineResult | null;
  scatterManifest: VisualizationManifest | null;
  scatterLoadState: OverlayLoadState;
  serveEvents: ServeEventsArtifact | null;
  serveEventsLoadState: OverlayLoadState;
  trackingOverlay: TrackingOverlayArtifact | null;
  trackingOverlayLoadState: OverlayLoadState;
}) {
  const overlayRows = [
    {
      label: "人物框",
      status: overlayLayerStatus(trackingOverlayLoadState, trackingOverlay?.status ?? result?.artifacts.tracking_overlay_status),
      detail: result?.artifacts.tracking_overlay_detail ?? trackingOverlay?.detail,
    },
    {
      label: "骨架姿态",
      status: overlayLayerStatus(poseOverlayLoadState, poseOverlay?.status ?? result?.artifacts.pose_overlay_status),
      detail: result?.artifacts.pose_overlay_detail ?? poseOverlay?.detail,
    },
    {
      label: "发球候选",
      status: overlayLayerStatus(serveEventsLoadState, serveEvents?.status ?? result?.artifacts.serve_events_status),
      detail: result?.artifacts.serve_events_detail ?? serveEvents?.detail,
    },
    {
      label: "球轨迹",
      status: overlayLayerStatus(
        ballTrajectoryLoadState,
        ballTrajectory?.status ?? result?.artifacts.cleaned_ball_trajectory_status ?? result?.artifacts.ball_trajectory_status
      ),
      detail: result?.artifacts.cleaned_ball_trajectory_detail ?? result?.artifacts.ball_trajectory_detail ?? ballTrajectory?.detail,
    },
    {
      label: "弹跳候选",
      status: overlayLayerStatus(bounceEventsLoadState, bounceEvents?.status ?? result?.artifacts.bounce_events_status),
      detail: result?.artifacts.bounce_events_detail ?? bounceEvents?.detail,
    },
    {
      label: "叠加视频",
      status: result?.artifacts.analysis_overlay_video_status ?? "unavailable",
      detail: result?.artifacts.analysis_overlay_video_detail,
    },
    {
      label: "位置热力图",
      status: overlayLayerStatus(heatmapsLoadState, heatmapsManifest?.status ?? result?.artifacts.position_visualizations_status),
      detail: heatmapsManifest?.detail ?? result?.artifacts.position_visualizations_detail,
    },
    {
      label: "位置散点图",
      status: overlayLayerStatus(scatterLoadState, scatterManifest?.status ?? result?.artifacts.position_visualizations_status),
      detail: scatterManifest?.detail ?? result?.artifacts.position_visualizations_detail,
    },
  ];
  const activeStage = job?.stages.find((stage) => stage.status === "active") ?? job?.stages.find((stage) => stage.id === job.stage);
  const supportedActions = analysis.reportActions.filter((action) => supportedReportTypes.includes(action.type));
  const contextualPath = (path: string) => withTaskListContext(path, taskContextForJob(job));
  const taskReturnPath = taskListPathForJob(job);

  return (
    <aside className="grid gap-4">
      <section className="sport-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">任务状态</p>
            <h2 className="mt-2 text-xl font-black text-[#14241B]">{job ? analysisStatusMeta(job.status).label : "样例分析"}</h2>
          </div>
          <span className="grid size-10 place-items-center rounded-2xl bg-[#22C55E]/12 text-[#168A34]">
            <BadgeCheck size={19} aria-hidden="true" />
          </span>
        </div>
        {job ? (
          <>
            <div className="mt-4 h-2 rounded-full bg-[#DFEADA]">
              <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${job.progress}%` }} />
            </div>
            <dl className="mt-4 grid gap-2 text-sm">
              <RailMeta label="比赛" value={job.metadata.matchTitle} />
              <RailMeta label="视频" value={job.metadata.fileName} />
              <RailMeta label="分析模式" value={analysisModeLabel(job.analysisMode)} />
              <RailMeta label="当前阶段" value={activeStage?.label ?? job.stage} />
              <RailMeta
                label="分析窗口"
                value={
                  result?.analysis_window?.requested_clip?.start_ms != null && result.analysis_window.requested_clip.end_ms != null
                    ? `${(result.analysis_window.requested_clip.start_ms / 1000).toFixed(2)} - ${(result.analysis_window.requested_clip.end_ms / 1000).toFixed(2)} 秒`
                    : "全视频"
                }
              />
              {result?.analysis_window?.output_time_origin_ms != null ? (
                <RailMeta label="叠加视频时间起点" value={`${(result.analysis_window.output_time_origin_ms / 1000).toFixed(2)} 秒`} />
              ) : null}
              <RailMeta label="更新时间" value={formatDateTime(job.updatedAt || job.createdAt)} />
            </dl>
          </>
        ) : null}
      </section>

      <section className="sport-card p-5">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">视觉层状态</p>
        <div className="mt-4 grid gap-3">
          {overlayRows.map((row) => {
            const meta = overlayStatusMeta(row.status);
            return (
              <div className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-3" key={row.label}>
                <div className="flex items-center justify-between gap-3">
                  <strong className="text-sm text-[#14241B]">{row.label}</strong>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-black ${meta.className}`}>{meta.label}</span>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">{row.detail ?? meta.detail}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="sport-card p-5">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">下级报告</p>
        <div className="mt-4 grid gap-2">
          {job?.id ? (
            <button
              className="flex items-center justify-between gap-3 rounded-2xl border border-[#DDE9D6] bg-white/75 px-4 py-3 text-left text-sm font-black text-[#14241B] transition hover:border-[#22C55E]/35 hover:bg-[#F9FFF6]"
              onClick={() => (embedded && onSelectView ? onSelectView("technical") : onNavigate(contextualPath(`/analysis/${job.id}/details`)))}
              type="button"
            >
              分析详情
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          ) : null}
          {supportedActions.map((action) => (
            <button
              className="flex items-center justify-between gap-3 rounded-2xl border border-[#DDE9D6] bg-white/75 px-4 py-3 text-left text-sm font-black text-[#14241B] transition hover:border-[#22C55E]/35 hover:bg-[#F9FFF6]"
              key={action.type}
              onClick={() => (embedded && onSelectView ? onSelectView("report") : onNavigate(reportPath(action.type)))}
              type="button"
            >
              {action.title}
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          ))}
        </div>
        {!embedded ? (
          <button className="quiet-button mt-4 w-full px-4 py-2.5" onClick={() => onNavigate(taskReturnPath)} type="button">
            返回任务管理
          </button>
        ) : null}
      </section>
    </aside>
  );
}

function overlayLayerStatus(loadState: OverlayLoadState, artifactStatus?: string) {
  if (loadState === "loading") {
    return "loading";
  }
  if (loadState === "failed") {
    return "failed";
  }
  if (loadState === "available") {
    return artifactStatus ?? "available";
  }
  return artifactStatus ?? "unavailable";
}

function overlayStatusMeta(status?: string) {
  if (status === "loading") {
    return { label: "加载中", className: "bg-[#2F80ED]/14 text-[#1E63B6]", detail: "该视觉层正在按需读取，视频和报告可先使用。" };
  }
  if (status === "available") {
    return { label: "可用", className: "bg-[#22C55E]/14 text-[#168A34]", detail: "该视觉层来自上传视频分析结果。" };
  }
  if (status === "partial") {
    return { label: "部分可用", className: "bg-[#FF9500]/14 text-[#A45A00]", detail: "该视觉层只有部分帧或片段可用。" };
  }
  if (status === "failed") {
    return { label: "失败", className: "bg-[#FF4D4F]/12 text-[#C92A2A]", detail: "该视觉层生成失败，可查看后端诊断。" };
  }
  if (status === "skipped") {
    return { label: "已跳过", className: "bg-slate-100 text-slate-600", detail: "该视觉层在本次分析中未启用。" };
  }
  if (status === "unavailable") {
    return { label: "不可用", className: "bg-slate-100 text-slate-600", detail: "该视觉层缺少模型、配置或输入。" };
  }
  if (status === "no_detections" || status === "no_poses" || status === "no_candidates") {
    return { label: "无结果", className: "bg-[#FF9500]/14 text-[#A45A00]", detail: "模型已运行，但没有产生可用目标。" };
  }
  return { label: "不可用", className: "bg-slate-100 text-slate-600", detail: "本次任务没有可用的真实视觉层数据。" };
}

function CoachNotesCard({ notes }: { notes: AnalysisReport["coachNotes"] }) {
  return (
    <section className="sport-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">智能教练笔记</p>
          <h2 className="mt-2 text-xl font-black text-[#14241B]">可执行洞察</h2>
        </div>
        <Brain className="text-[#168A34]" size={22} aria-hidden="true" />
      </div>
      <div className="mt-5 grid gap-3">
        {notes.map((note) => {
          const style = toneStyles[note.tone];

          return (
            <article className={`rounded-2xl border p-4 ${style.border} ${style.bg}`} key={note.id}>
              <div className="flex items-start gap-3">
                <span className={`mt-1 size-2.5 shrink-0 rounded-full ${style.dot}`} />
                <div>
                  <strong className={`text-sm ${style.text}`}>{note.title}</strong>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{note.body}</p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function HighlightsCard({
  highlights,
  onNavigate,
  reportPath,
}: {
  highlights: AnalysisReport["highlights"];
  onNavigate: NavigateFn;
  reportPath: (type: ReportType) => NavigatePath;
}) {
  return (
    <section className="sport-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">关键片段</p>
          <h2 className="mt-2 text-xl font-black text-[#14241B]">关键片段</h2>
        </div>
        <Timer className="text-[#D9FF3F]" size={22} aria-hidden="true" />
      </div>
      <div className="mt-5 grid gap-3">
        {highlights.map((highlight) => {
          const style = toneStyles[highlight.tone];

          return (
            <button
              className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4 text-left transition hover:border-[#22C55E]/35 hover:bg-[#F9FFF6]"
              key={highlight.id}
              onClick={() => onNavigate(highlight.tone === "training" ? "/training" : reportPath("movement"))}
              type="button"
            >
              <div className="flex items-center justify-between gap-3">
                <strong className="text-[#14241B]">{highlight.title}</strong>
                <span className={`rounded-full px-2 py-1 text-xs font-black ${style.bg} ${style.text}`}>{highlight.time}</span>
              </div>
              <p className={`mt-2 text-xs font-black uppercase tracking-[0.12em] ${style.text}`}>
                {highlight.result}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{highlight.description}</p>
            </button>
          );
        })}
      </div>
    </section>
  );
}
