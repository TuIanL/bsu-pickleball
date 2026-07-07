// 导入 Lucide 图标库
import {
  ArrowRight,
  BadgeCheck,
  Brain,
  Camera,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Dumbbell,
  Gauge,
  LineChart,
  Play,
  Radar,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Timer,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
// 导入 React 核心钩子和类型
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { AppShell } from "./components/platform/AppShell";
import { MetricCard } from "./components/platform/MetricCard";
import { ProgressChart } from "./components/platform/ProgressChart";
import { ReportVisualization } from "./components/platform/ReportVisualization";
import { SkillRatings } from "./components/platform/SkillRatings";
import { VideoAnalysisCard } from "./components/platform/VideoAnalysisCard";
import {
  drillRecommendations,
  hardwarePreview,
  matchSummary,
  overviewCards,
  platformNavigation,
  playerMarkers,
  progressPoints,
  reportActions,
  timelineMarkers,
  trainingRecommendations,
  videoOverlayLabels,
} from "./data/demoData";
import type {
  AnalysisJobSummary,
  AnalysisPipelineResult,
  AnalysisReport,
  AnalysisUploadMetadata,
  AppPath,
  AutomaticCalibrationResponse,
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  CameraInfo,
  CameraCreateRequest,
  DrillRecommendation,
  InsightTone,
  PoseOverlayArtifact,
  ProbeResult,
  RecordingSession,
  RecordingStartRequest,
  ReportType,
  ServeEventsArtifact,
  TrackingOverlayArtifact,
  VisualizationManifest,
} from "./types/report";
import {
  type AnalysisApiError,
  acceptAutomaticCalibration,
  cancelAnalysisJob,
  createAnalysisJob,
  createManualCalibration,
  demoAnalysisReport as demoReport,
  getBallTrajectory,
  getBounceEvents,
  getAnalysisJob,
  getAnalysisOverlayVideoUrl,
  getPoseOverlay,
  getPositionHeatmaps,
  getPositionScatterPlots,
  getServeEvents,
  getAnalysisResult,
  getAnalysisReport,
  getRecentAnalysisJob,
  getTrackingOverlay,
  deleteAnalysisJob,
  deleteAnalysisJobs,
  getVideoStreamUrl,
  isAnalysisApiError,
  listAnalysisJobs,
  RECENT_ANALYSIS_JOB_EVENT,
  rememberAnalysisJob,
  requestAutomaticCalibration,
  resolveAnalysisAssetUrl,
  uploadVideo,
  listCameras,
  createCamera,
  deleteCamera,
  probeCamera,
  startRecording,
  stopRecording,
  cancelRecording,
  listRecordings,
} from "./services/analysisClient";
import {
  type DiagnosticNotice,
  automaticCalibrationNotice,
  errorToNotice as buildErrorNotice,
  formatPercent,
  formatSeconds,
} from "./services/analysisDiagnostics";
import { buildCourtTrackSummaries, type CourtTrackSummary } from "./services/courtProjectionTracks";
import { adaptPipelineResultToReport, isPipelineResult } from "./services/pipelineReportAdapter";

// 定义路由状态类型，用于管理应用内的页面导航
type RouteState =
  | { page: "overview"; path: "/" } // 总览页
  | { page: "new-analysis"; path: "/analysis/new" } // 新建分析任务页
  | { page: "analysis-tasks"; path: "/analysis/tasks" } // 分析任务管理页
  | { page: "analysis-job"; path: `/analysis/${string}`; jobId: string } // 分析任务详情页
  | { page: "analysis-details"; path: `/analysis/${string}/details`; jobId: string } // 分析详情页
  | { page: "vision"; path: "/vision" } // 视觉分析工作台
  | { page: "vision"; path: `/analysis/${string}/vision`; jobId: string } // 特定任务的视觉分析
  | { page: "report"; path: `/reports/${ReportType}`; reportType: ReportType } // 报告页
  | { page: "report"; path: `/analysis/${string}/reports/${ReportType}`; reportType: ReportType; jobId: string } // 特定任务的报告
  | { page: "camera-hub"; path: "/camera" } // 球场采集管理页
  | { page: "training"; path: "/training" } // 训练建议页
  | { page: "hardware"; path: "/hardware" }; // 硬件融合预览页

const supportedReportTypes: ReportType[] = ["movement", "diagnosis"];

const toneStyles: Record<InsightTone, { dot: string; text: string; border: string; bg: string }> = {
  advantage: {
    dot: "bg-[#22C55E]",
    text: "text-[#168A34]",
    border: "border-[#22C55E]/25",
    bg: "bg-[#22C55E]/12",
  },
  risk: {
    dot: "bg-[#FF9500]",
    text: "text-[#A45A00]",
    border: "border-[#FF9500]/25",
    bg: "bg-[#FF9500]/12",
  },
  error: {
    dot: "bg-[#FF4D4F]",
    text: "text-[#C92A2A]",
    border: "border-[#FF4D4F]/25",
    bg: "bg-[#FF4D4F]/12",
  },
  training: {
    dot: "bg-[#2F80ED]",
    text: "text-[#1E63B6]",
    border: "border-[#2F80ED]/25",
    bg: "bg-[#2F80ED]/12",
  },
};

function errorToNotice(title: string, fallbackBody: string, error: unknown): DiagnosticNotice {
  return buildErrorNotice(title, fallbackBody, error, isAnalysisApiError);
}

function parsePath(pathname: string): RouteState {
  if (pathname === "/analysis/new" || pathname === "/upload") {
    return { page: "new-analysis", path: "/analysis/new" };
  }

  if (pathname === "/analysis/tasks") {
    return { page: "analysis-tasks", path: "/analysis/tasks" };
  }

  const analysisDetailsMatch = pathname.match(/^\/analysis\/([^/]+)\/details$/);

  if (analysisDetailsMatch) {
    const [, jobId] = analysisDetailsMatch;
    return { page: "analysis-details", path: `/analysis/${jobId}/details`, jobId };
  }

  const analysisReportMatch = pathname.match(/^\/analysis\/([^/]+)\/reports\/([^/]+)$/);

  if (analysisReportMatch) {
    const [, jobId, reportType] = analysisReportMatch;

    if (supportedReportTypes.includes(reportType as ReportType)) {
      return {
        page: "report",
        path: `/analysis/${jobId}/reports/${reportType as ReportType}`,
        reportType: reportType as ReportType,
        jobId,
      };
    }

    return { page: "analysis-details", path: `/analysis/${jobId}/details`, jobId };
  }

  const analysisVisionMatch = pathname.match(/^\/analysis\/([^/]+)\/vision$/);

  if (analysisVisionMatch) {
    const [, jobId] = analysisVisionMatch;
    return { page: "vision", path: `/analysis/${jobId}/vision`, jobId };
  }

  const analysisJobMatch = pathname.match(/^\/analysis\/([^/]+)$/);

  if (analysisJobMatch) {
    const [, jobId] = analysisJobMatch;
    if (jobId === "tasks") {
      return { page: "analysis-tasks", path: "/analysis/tasks" };
    }
    return { page: "analysis-job", path: `/analysis/${jobId}`, jobId };
  }

  if (pathname === "/camera") {
    return { page: "camera-hub", path: "/camera" };
  }

  if (pathname === "/vision") {
    return { page: "vision", path: "/vision" };
  }

  if (pathname === "/training") {
    return { page: "training", path: "/training" };
  }

  if (pathname === "/hardware") {
    return { page: "hardware", path: "/hardware" };
  }

  if (pathname.startsWith("/reports/")) {
    const reportType = pathname.replace("/reports/", "") as ReportType;

    if (supportedReportTypes.includes(reportType)) {
      return { page: "report", path: `/reports/${reportType}`, reportType };
    }

    return { page: "report", path: "/reports/movement", reportType: "movement" };
  }

  return { page: "overview", path: "/" };
}

function App() {
  // 初始化路由状态
  const [route, setRoute] = useState<RouteState>(() => parsePath(window.location.pathname));
  const [recentJob, setRecentJob] = useState<AnalysisJobSummary | null>(() => getRecentAnalysisJob());

  // 自定义导航函数，支持平滑滚动到顶部
  const navigate = useCallback((path: AppPath | "/upload") => {
    const nextRoute = parsePath(path);
    window.history.pushState({}, "", nextRoute.path);
    setRoute(nextRoute);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  // 监听浏览器前进/后退事件
  useEffect(() => {
    const handlePopState = () => setRoute(parsePath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);

    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    const handleRecentJobChange = () => setRecentJob(getRecentAnalysisJob());
    window.addEventListener(RECENT_ANALYSIS_JOB_EVENT, handleRecentJobChange);
    window.addEventListener("storage", handleRecentJobChange);

    return () => {
      window.removeEventListener(RECENT_ANALYSIS_JOB_EVENT, handleRecentJobChange);
      window.removeEventListener("storage", handleRecentJobChange);
    };
  }, []);

  // 根据当前路由渲染对应的页面内容
  const content = useMemo(() => {
    switch (route.page) {
      case "new-analysis":
        return <NewAnalysisPage onNavigate={navigate} />;
      case "analysis-tasks":
        return <AnalysisTasksPage onNavigate={navigate} recentJob={recentJob} />;
      case "analysis-job":
        return <AnalysisJobPage jobId={route.jobId} onNavigate={navigate} />;
      case "analysis-details":
        return <AnalysisDetailsPage jobId={route.jobId} onNavigate={navigate} />;
      case "vision":
        return <VisionPage jobId={"jobId" in route ? route.jobId : undefined} onNavigate={navigate} recentJob={recentJob} />;
      case "report":
        return <ReportPage jobId={"jobId" in route ? route.jobId : undefined} reportType={route.reportType} onNavigate={navigate} />;
      case "camera-hub":
        return <CameraHubPage onNavigate={navigate} />;
      case "training":
        return <TrainingPage onNavigate={navigate} />;
      case "hardware":
        return <HardwarePage onNavigate={navigate} />;
      case "overview":
      default:
        return <OverviewPage onNavigate={navigate} />;
    }
  }, [navigate, route, recentJob]);

  return (
    <AppShell activePath={route.path} navigation={platformNavigation} onNavigate={navigate}>
      {content}
    </AppShell>
  );
}

function PageFrame({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return (
    <div className={`mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 ${compact ? "py-8" : "py-10 lg:py-12"}`}>
      {children}
    </div>
  );
}

type NavigateFn = (path: AppPath | "/upload") => void;

const calibrationPointOrder = [
  { id: "top_left", label: "远端左角" },
  { id: "top_right", label: "远端右角" },
  { id: "bottom_right", label: "近端右角" },
  { id: "bottom_left", label: "近端左角" },
] as const;

const isProbablyBlankFrame = (context: CanvasRenderingContext2D, width: number, height: number) => {
  const data = context.getImageData(0, 0, width, height).data;
  const pixelCount = width * height;
  const sampleStep = Math.max(1, Math.floor(pixelCount / 1800));
  let samples = 0;
  let darkSamples = 0;
  let luminanceSum = 0;

  for (let pixel = 0; pixel < pixelCount; pixel += sampleStep) {
    const offset = pixel * 4;
    const luminance = data[offset] * 0.2126 + data[offset + 1] * 0.7152 + data[offset + 2] * 0.0722;
    luminanceSum += luminance;
    samples += 1;
    if (luminance < 16) {
      darkSamples += 1;
    }
  }

  return samples > 0 && luminanceSum / samples < 14 && darkSamples / samples > 0.94;
};

type CalibrationPointDraft = {
  id: (typeof calibrationPointOrder)[number]["id"];
  label: string;
  viewX: number;
  viewY: number;
  x: number;
  y: number;
};

/**
 * 总览页组件
 */
function OverviewPage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid min-h-[calc(100vh-8rem)] gap-8 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-[#22C55E]/35 bg-[#22C55E]/15 px-4 py-2 text-sm font-bold text-[#168A34]">
            <Sparkles size={16} aria-hidden="true" />
            智能比赛分析 · 真实产品与科研平台
          </div>
          <h1 className="mt-7 max-w-4xl text-5xl font-black leading-[0.98] text-[#14241B] sm:text-6xl xl:text-7xl">
            把每一场匹克球比赛，转化为可执行的训练洞察
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            当前聚焦真实视频上传、人员检测、姿态叠加、移动轨迹和标准球场投影底图；每次分析都会保留可追踪的执行记录，支撑产品复盘和后续科研产出。
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <button className="green-button" onClick={() => onNavigate("/analysis/new")} type="button">
              <Play size={18} fill="currentColor" aria-hidden="true" />
              分析新比赛
            </button>
            <button className="quiet-button" onClick={() => onNavigate("/analysis/tasks")} type="button">
              查看分析任务
              <ArrowRight size={17} aria-hidden="true" />
            </button>
          </div>

          <div className="mt-10 grid max-w-2xl grid-cols-3 gap-3">
            {[
              ["20x44", "标准球场"],
              ["82", "表现评分"],
              ["2", "当前报告"],
            ].map(([value, label]) => (
              <div className="rounded-2xl border border-[#DDE9D6] bg-white/80 p-4 shadow-sm" key={label}>
                <strong className="block text-3xl font-black text-[#168A34]">{value}</strong>
                <span className="mt-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative">
          <div className="absolute -inset-4 rounded-[2.5rem] bg-[#22C55E]/10 blur-3xl" />
          <div className="relative">
            <VideoAnalysisCard
              compact
              labels={videoOverlayLabels.slice(0, 3)}
              match={matchSummary}
              players={playerMarkers}
              timeline={timelineMarkers}
            />
          </div>
        </div>
      </section>

      <section className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {overviewCards.map((card) => (
          <button
            className="sport-card group p-5 text-left transition hover:-translate-y-1 hover:border-[#22C55E]/35"
            key={card.id}
            onClick={() => onNavigate(card.path)}
            type="button"
          >
            <span className="text-xs font-black uppercase tracking-[0.16em] text-[#168A34]">{card.metric}</span>
            <strong className="mt-4 block text-xl font-black text-[#14241B]">{card.title}</strong>
            <p className="mt-3 text-sm leading-6 text-slate-600">{card.body}</p>
            <span className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-slate-700 transition group-hover:text-[#168A34]">
              打开
              <ChevronRight size={16} aria-hidden="true" />
            </span>
          </button>
        ))}
      </section>
    </PageFrame>
  );
}

function AnalysisTasksPage({
  onNavigate,
  recentJob,
}: {
  onNavigate: NavigateFn;
  recentJob?: AnalysisJobSummary | null;
}) {
  const [jobs, setJobs] = useState<AnalysisJobSummary[] | null>(null);
  const [loadError, setLoadError] = useState<DiagnosticNotice | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [deleteNotice, setDeleteNotice] = useState<DiagnosticNotice | null>(null);
  const [deletingJobIds, setDeletingJobIds] = useState<string[]>([]);
  const [cancelingJobIds, setCancelingJobIds] = useState<string[]>([]);

  const loadJobs = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    if (!silent) {
      setIsRefreshing(true);
    }
    try {
      const nextJobs = await listAnalysisJobs();
      setJobs(nextJobs);
      setLoadError(null);
    } catch (error) {
      setLoadError(errorToNotice("读取分析任务失败", "无法读取任务列表，请检查后端服务或稍后重试。", error));
      setJobs([]);
    } finally {
      if (!silent) {
        setIsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;

    const tick = async () => {
      if (!alive) {
        return;
      }
      try {
        const nextJobs = await listAnalysisJobs();
        if (!alive) {
          return;
        }
        setJobs(nextJobs);
        setLoadError(null);
        if (nextJobs.some(isActiveAnalysisJob)) {
          timer = window.setTimeout(tick, 2200);
        }
      } catch (error) {
        if (!alive) {
          return;
        }
        setLoadError(errorToNotice("读取分析任务失败", "无法读取任务列表，请检查后端服务或稍后重试。", error));
        setJobs([]);
      }
    };

    tick();

    return () => {
      alive = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  const visibleJobs = jobs ?? [];
  const activeCount = visibleJobs.filter(isActiveAnalysisJob).length;
  const completedCount = visibleJobs.filter((job) => job.status === "completed").length;
  const failedCount = visibleJobs.filter((job) => job.status === "failed").length;
  const canceledCount = visibleJobs.filter((job) => job.status === "canceled").length;
  const eligibleJobs = visibleJobs.filter((job) => !isActiveAnalysisJob(job));
  const eligibleJobIds = eligibleJobs.map((job) => job.id);
  const eligibleJobKey = eligibleJobIds.join("|");
  const selectedEligibleIds = selectedJobIds.filter((jobId) => eligibleJobIds.includes(jobId));
  const allEligibleSelected = eligibleJobIds.length > 0 && eligibleJobIds.every((jobId) => selectedJobIds.includes(jobId));
  const isDeleting = deletingJobIds.length > 0;

  useEffect(() => {
    setSelectedJobIds((current) => current.filter((jobId) => eligibleJobIds.includes(jobId)));
  }, [eligibleJobKey]);

  const summarizeDeleteResults = (results: Awaited<ReturnType<typeof deleteAnalysisJobs>>) => {
    const deleted = results.filter((result) => result.status === "deleted");
    const blocked = results.filter((result) => result.status === "blocked");
    const missing = results.filter((result) => result.status === "not_found");
    const failed = results.filter((result) => result.status === "failed");
    const attention = [...blocked, ...missing, ...failed];

    setDeleteNotice({
      title: attention.length ? "删除完成，部分任务需要处理" : "删除完成",
      body: attention.length
        ? `已删除 ${deleted.length} 个任务，${attention.length} 个任务未删除。运行中任务会被后端保护，缺失任务会在刷新后消失。`
        : `已删除 ${deleted.length} 个任务，并同步清理本地产物。`,
      detailItems: [
        ["已删除", deleted.length],
        ["受保护", blocked.length],
        ["未找到", missing.length],
        ["失败", failed.length],
      ],
    });
  };

  const toggleSelection = (jobId: string) => {
    setDeleteNotice(null);
    setSelectedJobIds((current) => (
      current.includes(jobId) ? current.filter((item) => item !== jobId) : [...current, jobId]
    ));
  };

  const toggleSelectAll = () => {
    setDeleteNotice(null);
    setSelectedJobIds(allEligibleSelected ? [] : eligibleJobIds);
  };

  const handleSingleDelete = async (job: AnalysisJobSummary) => {
    if (isActiveAnalysisJob(job) || isDeleting) {
      return;
    }
    const confirmed = window.confirm(`确定删除「${job.metadata.matchTitle}」吗？后端会同步删除该任务的本地产物，无法恢复。`);
    if (!confirmed) {
      return;
    }
    setDeletingJobIds([job.id]);
    setDeleteNotice(null);
    try {
      const result = await deleteAnalysisJob(job.id);
      summarizeDeleteResults([result]);
      setSelectedJobIds((current) => current.filter((jobId) => jobId !== job.id));
      await loadJobs({ silent: true });
    } catch (error) {
      setDeleteNotice(errorToNotice("删除任务失败", "没有删除任何任务，请检查后端服务后重试。", error));
    } finally {
      setDeletingJobIds([]);
    }
  };

  const handleCancelJob = async (job: AnalysisJobSummary) => {
    if (!isCancelableAnalysisJob(job) || cancelingJobIds.includes(job.id)) {
      return;
    }
    const confirmed = window.confirm(`确定取消「${job.metadata.matchTitle}」吗？运行中的任务会在安全检查点停止。`);
    if (!confirmed) {
      return;
    }
    setCancelingJobIds((current) => [...current, job.id]);
    setDeleteNotice(null);
    try {
      const nextJob = await cancelAnalysisJob(job.id);
      setJobs((current) => current?.map((item) => (item.id === nextJob.id ? nextJob : item)) ?? [nextJob]);
      rememberAnalysisJob(nextJob);
      setDeleteNotice({
        title: nextJob.status === "canceled" ? "任务已取消" : "已请求取消任务",
        body:
          nextJob.status === "canceled"
            ? "任务已停止，生成的临时产物会由后端清理。"
            : "运行中的分析会在下一处安全检查点停止，任务列表会继续刷新。",
      });
      await loadJobs({ silent: true });
    } catch (error) {
      setDeleteNotice(errorToNotice("取消任务失败", "无法取消该分析任务，请刷新后重试。", error));
    } finally {
      setCancelingJobIds((current) => current.filter((jobId) => jobId !== job.id));
    }
  };

  const handleBatchDelete = async () => {
    if (!selectedEligibleIds.length || isDeleting) {
      return;
    }
    const confirmed = window.confirm(`确定批量删除 ${selectedEligibleIds.length} 个历史分析任务吗？本地任务产物会被同步删除，无法恢复。`);
    if (!confirmed) {
      return;
    }
    setDeletingJobIds(selectedEligibleIds);
    setDeleteNotice(null);
    try {
      const results = await deleteAnalysisJobs(selectedEligibleIds);
      summarizeDeleteResults(results);
      const deletedIds = results.filter((result) => result.status === "deleted" || result.status === "not_found").map((result) => result.job_id);
      setSelectedJobIds((current) => current.filter((jobId) => !deletedIds.includes(jobId)));
      await loadJobs({ silent: true });
    } catch (error) {
      setDeleteNotice(errorToNotice("批量删除失败", "没有删除任何任务，请检查后端服务后重试。", error));
    } finally {
      setDeletingJobIds([]);
    }
  };

  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[1fr_0.38fr] lg:items-stretch">
        <div className="sport-card p-6 sm:p-8">
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Camera size={16} aria-hidden="true" />
            视频分析
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">分析任务管理</h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
            这里汇总从上传到完成的所有视觉分析任务。任务由后端队列和 worker 执行，阶段耗时、错误码和结果产物会被保留，方便产品调试和科研复现。
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
              <Upload size={16} aria-hidden="true" />
              上传比赛
            </button>
            <button className="quiet-button px-4 py-2.5" onClick={() => loadJobs()} disabled={isRefreshing} type="button">
              <RefreshCw size={16} aria-hidden="true" />
              {isRefreshing ? "刷新中" : "刷新任务"}
            </button>
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/vision")} type="button">
              查看演示
            </button>
          </div>
        </div>
        <div className="grid gap-3 rounded-3xl border border-[#DDE9D6] bg-white/75 p-5 shadow-sm">
          {[
            ["全部任务", visibleJobs.length],
            ["分析中", activeCount],
            ["已完成", completedCount],
            ["失败", failedCount],
            ["已取消", canceledCount],
          ].map(([label, value]) => (
            <div className="flex items-center justify-between rounded-2xl bg-[#F5FAF1] px-4 py-3" key={label}>
              <span className="text-sm font-bold text-slate-500">{label}</span>
              <strong className="text-2xl font-black text-[#14241B]">{value}</strong>
            </div>
          ))}
        </div>
      </section>

      {loadError ? (
        <div className="mt-6">
          <DiagnosticNoticeCard notice={loadError} />
        </div>
      ) : null}

      {deleteNotice ? (
        <div className="mt-6">
          <DiagnosticNoticeCard notice={deleteNotice} tone={deleteNotice.title.includes("失败") ? "error" : "info"} />
        </div>
      ) : null}

      {jobs === null ? (
        <section className="mt-6 sport-card p-8 text-center">
          <p className="text-sm font-bold text-[#168A34]">正在读取任务列表</p>
          <p className="mt-2 text-sm text-slate-500">正在连接后端并同步历史分析任务。</p>
        </section>
      ) : visibleJobs.length === 0 ? (
        <section className="mt-6 sport-card p-8 text-center">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">暂无分析任务</p>
          <h2 className="mt-3 text-3xl font-black text-[#14241B]">先上传一场比赛</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-600">
            上传视频并完成四角标定后，任务会出现在这里，状态会从排队、分析中更新到分析完成。
          </p>
          <button className="green-button mx-auto mt-5" onClick={() => onNavigate("/analysis/new")} type="button">
            上传比赛
          </button>
        </section>
      ) : (
        <section className="mt-6 grid gap-4">
          <div className="flex flex-col gap-3 rounded-3xl border border-[#DDE9D6] bg-white/75 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <label className="inline-flex items-center gap-3 text-sm font-bold text-[#14241B]">
              <input
                checked={allEligibleSelected}
                className="size-4 accent-[#22C55E]"
                disabled={!eligibleJobIds.length || isDeleting}
                onChange={toggleSelectAll}
                type="checkbox"
              />
              已选 {selectedEligibleIds.length} / {eligibleJobIds.length} 个可删除历史任务
            </label>
            <div className="flex flex-wrap gap-2">
              <button className="quiet-button px-4 py-2.5" disabled={!selectedEligibleIds.length || isDeleting} onClick={() => setSelectedJobIds([])} type="button">
                清空选择
              </button>
              <button className="green-button px-4 py-2.5" disabled={!selectedEligibleIds.length || isDeleting} onClick={handleBatchDelete} type="button">
                <Trash2 size={16} aria-hidden="true" />
                {isDeleting ? "删除中" : "批量删除"}
              </button>
            </div>
          </div>
          {visibleJobs.map((job) => (
            <AnalysisTaskCard
              canceling={cancelingJobIds.includes(job.id)}
              deleting={deletingJobIds.includes(job.id)}
              job={job}
              key={job.id}
              onCancel={handleCancelJob}
              onDelete={handleSingleDelete}
              onNavigate={onNavigate}
              onToggleSelected={toggleSelection}
              recent={recentJob?.id === job.id}
              selectable={!isActiveAnalysisJob(job)}
              selected={selectedJobIds.includes(job.id)}
            />
          ))}
        </section>
      )}
    </PageFrame>
  );
}

function AnalysisTaskCard({
  job,
  canceling = false,
  deleting = false,
  onCancel,
  onDelete,
  onNavigate,
  onToggleSelected,
  recent,
  selectable = false,
  selected = false,
}: {
  canceling?: boolean;
  deleting?: boolean;
  job: AnalysisJobSummary;
  onCancel: (job: AnalysisJobSummary) => void;
  onDelete: (job: AnalysisJobSummary) => void;
  onNavigate: NavigateFn;
  onToggleSelected: (jobId: string) => void;
  recent?: boolean;
  selectable?: boolean;
  selected?: boolean;
}) {
  const status = analysisStatusMeta(job.status);
  const currentStage = job.stages.find((stage) => stage.id === job.stage) ?? job.stages.find((stage) => stage.status === "active");
  const updatedAt = formatDateTime(job.updatedAt || job.createdAt);
  const canCancel = isCancelableAnalysisJob(job);

  return (
    <article className={`sport-card p-5 sm:p-6 ${recent ? "border-[#22C55E]/50" : ""}`}>
      <div className="grid gap-5 lg:grid-cols-[1fr_0.38fr] lg:items-center">
        <div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-black ${status.className}`}>{status.label}</span>
              <span className="rounded-full border border-[#DDE9D6] bg-white/80 px-3 py-1 text-xs font-bold text-slate-500">
                {analysisModeLabel(job.analysisMode)}
              </span>
              {recent ? (
                <span className="rounded-full border border-[#22C55E]/30 bg-[#22C55E]/12 px-3 py-1 text-xs font-black text-[#168A34]">
                  最近任务
                </span>
              ) : null}
            </div>
            {selectable ? (
              <label className="inline-flex items-center gap-2 text-xs font-black text-slate-500">
                <input
                  checked={selected}
                  className="size-4 accent-[#22C55E]"
                  disabled={deleting}
                  onChange={() => onToggleSelected(job.id)}
                  type="checkbox"
                />
                选择
              </label>
            ) : null}
          </div>
          <h2 className="mt-4 text-2xl font-black text-[#14241B]">{job.metadata.matchTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {job.metadata.fileName} · {job.metadata.venue} · {job.metadata.athleteLabel}
          </p>
          <div className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
            <TaskMeta label="更新时间" value={updatedAt} />
            <TaskMeta label="当前阶段" value={currentStage?.label ?? job.stage} />
            <TaskMeta label="任务 ID" value={job.id} />
          </div>
          {job.status === "failed" ? (
            <p className="mt-3 rounded-2xl border border-[#FF4D4F]/20 bg-[#FF4D4F]/10 p-3 text-sm font-semibold leading-6 text-[#C92A2A]">
              {job.publicErrorMessage ?? job.errorMessage ?? currentStage?.detail ?? "分析失败，请检查后端日志或重新上传。"}
              {job.errorCode ? <span className="mt-1 block text-xs font-black uppercase">错误码：{job.errorCode}</span> : null}
            </p>
          ) : null}
          {job.status === "canceled" ? (
            <p className="mt-3 rounded-2xl border border-slate-300 bg-slate-100 p-3 text-sm font-semibold leading-6 text-slate-600">
              任务已取消{job.canceledAt ? ` · ${formatDateTime(job.canceledAt)}` : ""}。
            </p>
          ) : null}
        </div>
        <div>
          <div className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
            <div className="flex items-end justify-between">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">进度</span>
              <strong className="text-3xl font-black text-[#168A34]">{job.progress}%</strong>
            </div>
            <div className="mt-3 h-2 rounded-full bg-[#DFEADA]">
              <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${job.progress}%` }} />
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {job.status === "completed" ? (
              <>
                <button className="green-button px-4 py-2.5" onClick={() => onNavigate(`/analysis/${job.id}/vision`)} type="button">
                  查看分析结果
                </button>
                <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(`/analysis/${job.id}/details`)} type="button">
                  分析详情
                </button>
              </>
            ) : (
              <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(`/analysis/${job.id}`)} type="button">
                查看任务详情
              </button>
            )}
            {job.status === "failed" ? (
              <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
                重新上传
              </button>
            ) : null}
            {job.status === "canceled" ? (
              <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
                新建分析
              </button>
            ) : null}
            {canCancel ? (
              <button className="quiet-button px-4 py-2.5 text-[#A45A00]" disabled={canceling} onClick={() => onCancel(job)} type="button">
                {canceling ? "取消中" : "取消任务"}
              </button>
            ) : null}
            {selectable ? (
              <button className="quiet-button px-4 py-2.5 text-[#C92A2A]" disabled={deleting} onClick={() => onDelete(job)} type="button">
                <Trash2 size={15} aria-hidden="true" />
                {deleting ? "删除中" : "删除"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

function TaskMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[#F5FAF1] p-3">
      <span className="block text-xs font-black uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <strong className="mt-1 block break-words text-[#14241B]">{value}</strong>
    </div>
  );
}

function isActiveAnalysisJob(job: AnalysisJobSummary) {
  return ["uploaded", "queued", "processing"].includes(job.status);
}

function isCancelableAnalysisJob(job: AnalysisJobSummary) {
  return ["uploaded", "queued", "processing"].includes(job.status);
}

function analysisStatusMeta(status: AnalysisJobSummary["status"]) {
  const styles = {
    uploaded: { label: "视频已接收", className: "bg-[#2F80ED]/12 text-[#1E63B6]" },
    queued: { label: "排队中", className: "bg-[#2F80ED]/12 text-[#1E63B6]" },
    processing: { label: "正在分析", className: "bg-[#FF9500]/14 text-[#A45A00]" },
    completed: { label: "分析完成", className: "bg-[#22C55E]/14 text-[#168A34]" },
    failed: { label: "分析失败", className: "bg-[#FF4D4F]/12 text-[#C92A2A]" },
    canceled: { label: "已取消", className: "bg-slate-200 text-slate-700" },
  } satisfies Record<AnalysisJobSummary["status"], { label: string; className: string }>;

  return styles[status];
}

function analysisModeLabel(mode?: AnalysisJobSummary["analysisMode"]) {
  if (mode === "real") {
    return "真实视频分析";
  }
  if (mode === "limited") {
    return "有限分析";
  }
  return "样例任务";
}

function formatDateTime(value: string) {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return value;
  }
  return new Date(timestamp).toLocaleString();
}

function formatDurationMs(value: number) {
  if (value < 1000) {
    return `${value}ms`;
  }
  if (value < 60_000) {
    return `${(value / 1000).toFixed(1)}s`;
  }
  return `${Math.floor(value / 60_000)}m ${Math.round((value % 60_000) / 1000)}s`;
}

/**
 * 新建分析任务页组件
 */
function NewAnalysisPage({ onNavigate }: { onNavigate: NavigateFn }) {
  const today = new Date().toISOString().slice(0, 10);
  const calibrationVideoRef = useRef<HTMLVideoElement | null>(null);
  const calibrationCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const calibrationAutoSeekAttemptsRef = useRef(0);
  const calibrationAutoSeekEnabledRef = useRef(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [calibrationPoints, setCalibrationPoints] = useState<CalibrationPointDraft[]>([]);
  const [calibrationFrameStatus, setCalibrationFrameStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [calibrationFrameError, setCalibrationFrameError] = useState<string | null>(null);
  const [calibrationFramePreviewUrl, setCalibrationFramePreviewUrl] = useState<string | null>(null);
  const [uploadedVideoId, setUploadedVideoId] = useState<string | null>(null);
  const [automaticCalibration, setAutomaticCalibration] = useState<AutomaticCalibrationResponse | null>(null);
  const [automaticCalibrationStatus, setAutomaticCalibrationStatus] = useState<"idle" | "uploading" | "detecting" | "ready" | "unavailable" | "rejected" | "error">("idle");
  const [automaticCalibrationError, setAutomaticCalibrationError] = useState<AnalysisApiError | null>(null);
  const [submitStep, setSubmitStep] = useState<"idle" | "uploading" | "calibrating" | "creating">("idle");
  const [metadata, setMetadata] = useState({
    matchTitle: "匹克球训练对局",
    venue: "北京体育大学匹克球训练场",
    matchDate: today,
    matchFormat: "doubles" as AnalysisUploadMetadata["matchFormat"],
    cameraAngle: "elevated" as AnalysisUploadMetadata["cameraAngle"],
    athleteLabel: "球馆体验用户 A",
    level: "大众进阶",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<DiagnosticNotice | null>(null);

  const canSubmit = Boolean(
    selectedFile &&
      calibrationPoints.length === calibrationPointOrder.length &&
      metadata.matchTitle.trim() &&
      metadata.venue.trim() &&
      metadata.matchDate &&
      metadata.athleteLabel.trim() &&
      metadata.level.trim()
  );
  const canRequestAutomaticCalibration = Boolean(selectedFile && !isSubmitting && automaticCalibrationStatus !== "uploading" && automaticCalibrationStatus !== "detecting");

  const updateMetadata = <K extends keyof typeof metadata>(key: K, value: (typeof metadata)[K]) => {
    setMetadata((current) => ({ ...current, [key]: value }));
    setError(null);
  };

  const videoPreviewUrl = useMemo(() => (selectedFile ? URL.createObjectURL(selectedFile) : null), [selectedFile]);

  useEffect(() => {
    calibrationAutoSeekAttemptsRef.current = 0;
    calibrationAutoSeekEnabledRef.current = Boolean(videoPreviewUrl);
    return () => {
      if (videoPreviewUrl) {
        URL.revokeObjectURL(videoPreviewUrl);
      }
    };
  }, [videoPreviewUrl]);

  const calibrationComplete = calibrationPoints.length === calibrationPointOrder.length;
  const calibrationFrameReady = calibrationFrameStatus === "ready";
  const automaticPreviewUrl = resolveAnalysisAssetUrl(automaticCalibration?.preview_image_url);

  const captureCalibrationFrame = () => {
    const video = calibrationVideoRef.current;
    if (!video || video.readyState < 2) {
      return;
    }

    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) {
      setCalibrationFrameStatus("ready");
      return;
    }

    try {
      const canvas = calibrationCanvasRef.current ?? document.createElement("canvas");
      calibrationCanvasRef.current = canvas;
      const scale = Math.min(1, 1280 / width);
      canvas.width = Math.max(1, Math.round(width * scale));
      canvas.height = Math.max(1, Math.round(height * scale));

      const context = canvas.getContext("2d");
      if (!context) {
        setCalibrationFrameStatus("ready");
        return;
      }

      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      if (
        calibrationAutoSeekEnabledRef.current &&
        calibrationAutoSeekAttemptsRef.current < 6 &&
        Number.isFinite(video.duration) &&
        video.currentTime < video.duration - 0.75 &&
        isProbablyBlankFrame(context, canvas.width, canvas.height)
      ) {
        calibrationAutoSeekAttemptsRef.current += 1;
        seekCalibrationVideo(video.currentTime + Math.min(Math.max(video.duration * 0.05, 0.75), 2), {
          autoSkipDark: true,
        });
        return;
      }

      calibrationAutoSeekEnabledRef.current = false;
      setCalibrationFramePreviewUrl(canvas.toDataURL("image/jpeg", 0.88));
      setCalibrationFrameStatus("ready");
    } catch {
      setCalibrationFrameStatus("ready");
    }
  };

  const seekCalibrationVideo = (targetSeconds?: number, options: { autoSkipDark?: boolean } = {}) => {
    const video = calibrationVideoRef.current;
    if (!video) {
      return;
    }

    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    if (duration <= 0) {
      if (video.readyState >= 2) {
        captureCalibrationFrame();
      } else {
        setCalibrationFrameStatus("loading");
      }
      return;
    }

    calibrationAutoSeekEnabledRef.current = Boolean(options.autoSkipDark);
    const defaultTarget = Math.min(Math.max(duration * 0.1, 0.15), Math.max(duration - 0.05, 0));
    const nextTime = Math.min(Math.max(targetSeconds ?? defaultTarget, 0), Math.max(duration - 0.05, 0));
    setCalibrationFrameStatus("loading");
    setCalibrationFrameError(null);
    setCalibrationFramePreviewUrl(null);
    video.pause();
    if (Math.abs(video.currentTime - nextTime) < 0.03 && video.readyState >= 2) {
      captureCalibrationFrame();
      return;
    }
    video.currentTime = nextTime;
  };

  const shiftCalibrationFrame = (seconds: number) => {
    const video = calibrationVideoRef.current;
    if (!video || calibrationPoints.length > 0) {
      return;
    }
    calibrationAutoSeekAttemptsRef.current = 0;
    seekCalibrationVideo(video.currentTime + seconds, { autoSkipDark: false });
  };

  const handleCalibrationClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (calibrationPoints.length >= calibrationPointOrder.length) {
      return;
    }
    if (!calibrationFrameReady) {
      setError({
        title: "标定画面未就绪",
        body: "标定帧还没有加载完成，请等画面出现后再点选四角。",
      });
      return;
    }

    const video = calibrationVideoRef.current;
    if (!video) {
      return;
    }

    video.pause();
    const rect = event.currentTarget.getBoundingClientRect();
    const nextPoint = calibrationPointOrder[calibrationPoints.length];
    const naturalWidth = video.videoWidth || rect.width;
    const naturalHeight = video.videoHeight || rect.height;
    const mediaAspect = naturalWidth / naturalHeight;
    const viewAspect = rect.width / rect.height;
    const renderedWidth = viewAspect > mediaAspect ? rect.height * mediaAspect : rect.width;
    const renderedHeight = viewAspect > mediaAspect ? rect.height : rect.width / mediaAspect;
    const offsetX = (rect.width - renderedWidth) / 2;
    const offsetY = (rect.height - renderedHeight) / 2;
    const xInMedia = Math.min(Math.max(event.clientX - rect.left - offsetX, 0), renderedWidth);
    const yInMedia = Math.min(Math.max(event.clientY - rect.top - offsetY, 0), renderedHeight);
    setCalibrationPoints((current) => [
      ...current,
      {
        id: nextPoint.id,
        label: nextPoint.label,
        x: Math.round(xInMedia * (naturalWidth / renderedWidth)),
        y: Math.round(yInMedia * (naturalHeight / renderedHeight)),
        viewX: ((offsetX + xInMedia) / rect.width) * 100,
        viewY: ((offsetY + yInMedia) / rect.height) * 100,
      },
    ]);
    setError(null);
  };

  const resetCalibration = () => {
    setCalibrationPoints([]);
    setAutomaticCalibration(null);
    setAutomaticCalibrationError(null);
    setAutomaticCalibrationStatus("idle");
    setError(null);
  };

  const ensureUploadedVideo = async () => {
    if (uploadedVideoId) {
      return uploadedVideoId;
    }
    if (!selectedFile) {
      throw new Error("No selected file");
    }
    const upload = await uploadVideo(selectedFile);
    setUploadedVideoId(upload.video.id);
    return upload.video.id;
  };

  const pointMapFromDraft = () =>
    calibrationPoints.reduce(
      (acc, point) => {
        acc[point.id] = { x: point.x, y: point.y };
        return acc;
      },
      {} as Record<CalibrationPointDraft["id"], { x: number; y: number }>
    );

  const applyAutomaticKeypoints = (response: AutomaticCalibrationResponse) => {
    if (!response.keypoints || !response.selected_frame?.width || !response.selected_frame.height) {
      return;
    }
    const width = response.selected_frame.width;
    const height = response.selected_frame.height;
    setCalibrationPoints(
      calibrationPointOrder.map((point) => {
        const detected = response.keypoints?.[point.id];
        const x = detected?.x ?? 0;
        const y = detected?.y ?? 0;
        return {
          id: point.id,
          label: point.label,
          x: Math.round(x),
          y: Math.round(y),
          viewX: Math.min(100, Math.max(0, (x / width) * 100)),
          viewY: Math.min(100, Math.max(0, (y / height) * 100)),
        };
      })
    );
  };

  const handleAutomaticCalibration = async () => {
    if (!selectedFile || !canRequestAutomaticCalibration) {
      return;
    }

    setError(null);
    setAutomaticCalibration(null);
    setAutomaticCalibrationError(null);
    try {
      setAutomaticCalibrationStatus(uploadedVideoId ? "detecting" : "uploading");
      const videoId = await ensureUploadedVideo();
      setAutomaticCalibrationStatus("detecting");
      const response = await requestAutomaticCalibration(videoId);
      setAutomaticCalibration(response);
      if (response.status === "available" && response.keypoints) {
        applyAutomaticKeypoints(response);
        setAutomaticCalibrationStatus("ready");
      } else if (response.status === "rejected") {
        setAutomaticCalibrationStatus("rejected");
      } else {
        setAutomaticCalibrationStatus("unavailable");
      }
    } catch (error) {
      setAutomaticCalibrationStatus("error");
      setAutomaticCalibrationError(isAnalysisApiError(error) ? error : null);
      setError(errorToNotice("自动识别边线失败", "可以继续手动点选四个角点，已保留当前视频和比赛信息。", error));
    }
  };

  const handleSubmit = async () => {
    if (!selectedFile || !canSubmit) {
      setError({
        title: "分析信息不完整",
        body: "请选择视频、点选四个场地角点并补全比赛信息。",
      });
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      setSubmitStep(uploadedVideoId ? "calibrating" : "uploading");
      const videoId = await ensureUploadedVideo();
      const pointMap = pointMapFromDraft();

      setSubmitStep("calibrating");
      const source = automaticCalibration?.status === "available" ? "automatic" : "corrected";
      const automaticAccepted =
        automaticCalibration?.status === "available"
          ? await acceptAutomaticCalibration(videoId, pointMap, source)
          : null;
      const calibrationId =
        automaticAccepted?.calibration_id ??
        (await createManualCalibration(videoId, pointMap)).calibration_id;

      setSubmitStep("creating");
      const job = await createAnalysisJob({
        metadata: {
          ...metadata,
          fileName: selectedFile.name,
          fileSize: selectedFile.size,
        },
        videoId,
        calibrationId,
        frameStride: 2,
        useDemoFallback: false,
      });
      rememberAnalysisJob(job);
      onNavigate("/analysis/tasks");
    } catch (error) {
      setError(
        errorToNotice(
          "真实上传或分析任务创建失败",
          "请确认后端已启动、视频格式受支持，并重新检查四角标定。",
          error
        )
      );
    } finally {
      setIsSubmitting(false);
      setSubmitStep("idle");
    }
  };

  const nextCalibrationPoint = calibrationPointOrder[calibrationPoints.length];
  const submitCopy = {
    idle: "开始真实分析",
    uploading: "上传视频中...",
    calibrating: "提交标定中...",
    creating: "创建任务中...",
  }[submitStep];
  const automaticCalibrationDiagnostic = automaticCalibrationNotice(
    automaticCalibration,
    automaticCalibrationStatus,
    automaticCalibrationError
  );

  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Upload size={16} aria-hidden="true" />
            上传比赛视频
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">创建视觉分析任务</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            上传视频会进入本地 Python 后端，四角标定后创建持久化任务，由 worker 执行视觉分析，先输出移动、速度、热力图等真实可追溯反馈。
          </p>

          <div className="mt-6 grid gap-3 rounded-3xl border border-[#DDE9D6] bg-white/70 p-4">
            {[
              ["1", "上传视频", "保留原始文件和基础比赛信息"],
              ["2", "四角标定", "把画面坐标映射到标准匹克球场"],
              ["3", "生成报告", "输出移动轨迹、速度、热力图和有限诊断"],
            ].map(([index, title, body]) => (
              <div className="flex gap-3 rounded-2xl bg-[#F5FAF1] p-3" key={index}>
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[#22C55E] text-sm font-black text-[#071008]">
                  {index}
                </span>
                <div>
                  <strong className="text-[#14241B]">{title}</strong>
                  <p className="mt-1 text-sm text-slate-600">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <section className="sport-card p-5 sm:p-6">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">视频文件</p>
            <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed border-[#BFD5B8] bg-[#F5FAF1] p-8 text-center transition hover:border-[#22C55E]/60 hover:bg-[#F9FFF6]">
              <input
                accept="video/*"
                className="sr-only"
                onChange={(event) => {
                  const nextFile = event.target.files?.[0] ?? null;
                  setSelectedFile(nextFile);
                  setCalibrationPoints([]);
                  setCalibrationFrameStatus(nextFile ? "loading" : "idle");
                  setCalibrationFrameError(null);
                  setCalibrationFramePreviewUrl(null);
                  setUploadedVideoId(null);
                  setAutomaticCalibration(null);
                  setAutomaticCalibrationError(null);
                  setAutomaticCalibrationStatus("idle");
                  setError(null);
                }}
                type="file"
              />
              <span className="grid size-14 place-items-center rounded-full bg-[#22C55E]/15 text-[#168A34]">
                <Upload size={24} aria-hidden="true" />
              </span>
              <strong className="mt-4 text-lg text-[#14241B]">
                {selectedFile ? selectedFile.name : "选择比赛视频"}
              </strong>
              <p className="mt-2 text-sm text-slate-500">
                {selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(1)} MB · 将上传到本地分析后端` : "支持常见视频格式，真实上传由后端接管"}
              </p>
            </label>
          </div>

          {videoPreviewUrl ? (
            <div className="mt-6 rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">四角标定</p>
                  <h2 className="mt-1 text-lg font-black text-[#14241B]">
                    {nextCalibrationPoint ? `点击画面中的${nextCalibrationPoint.label}` : "四个角点已记录"}
                  </h2>
                  <p className="mt-1 text-xs font-semibold text-slate-500">
                    点选期间视频控件会隐藏，避免误触播放键或进度条。
                  </p>
                </div>
                <button className="quiet-button px-3 py-2 text-xs" onClick={resetCalibration} type="button">
                  重新点选
                </button>
              </div>
              <div className="mt-3 grid gap-3 rounded-2xl border border-[#22C55E]/20 bg-white/70 p-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <strong className="text-sm text-[#14241B]">自动识别球场边线</strong>
                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      先上传视频并请求后端模型建议，识别结果会填入四角点，仍可手动修正。
                    </p>
                  </div>
                  <button
                    className="quiet-button px-3 py-2 text-xs"
                    disabled={!canRequestAutomaticCalibration}
                    onClick={handleAutomaticCalibration}
                    type="button"
                  >
                    {automaticCalibrationStatus === "uploading"
                      ? "上传中..."
                      : automaticCalibrationStatus === "detecting"
                        ? "识别中..."
                        : "自动识别"}
                  </button>
                </div>
                {automaticCalibrationDiagnostic ? (
                  <DiagnosticNoticeCard
                    notice={automaticCalibrationDiagnostic}
                    tone={automaticCalibrationStatus === "ready" || automaticCalibrationStatus === "detecting" || automaticCalibrationStatus === "uploading" ? "info" : "error"}
                  />
                ) : null}
                {automaticCalibration?.confidence_breakdown ? (
                  <div className="mt-3 grid grid-cols-4 gap-2 text-xs">
                    {([
                      ["分割模型", automaticCalibration.confidence_breakdown.segmentation],
                      ["几何拟合", automaticCalibration.confidence_breakdown.geometry],
                      ["球场线校准", automaticCalibration.confidence_breakdown.reference],
                      ["综合置信度", automaticCalibration.confidence_breakdown.combined],
                    ] as const).map(([label, value]) => (
                      <div key={label} className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-2 text-center">
                        <div className="font-black text-base text-[#17231D]">{(value * 100).toFixed(0)}%</div>
                        <div className="mt-0.5 text-slate-400">{label}</div>
                      </div>
                    ))}
                  </div>
                ) : null}
                {automaticCalibration?.reference ? (
                  <div className="mt-2 rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-3 text-xs text-slate-600">
                    <span className="font-bold text-[#17231D]">球场线参考: </span>
                    {automaticCalibration.reference.summary}
                    {automaticCalibration.reference.passing_line_names?.length > 0 && (
                      <span className="ml-1 text-slate-400">
                        (通过: {automaticCalibration.reference.passing_line_names.slice(0, 4).join(", ")})
                      </span>
                    )}
                    {automaticCalibration.reference.rejection_reason && (
                      <div className="mt-1 text-[#C92A2A]">
                        拒绝原因: {automaticCalibration.reference.rejection_reason}
                      </div>
                    )}
                  </div>
                ) : null}
                {automaticPreviewUrl ? (
                  <img
                    alt=""
                    className="max-h-56 w-full rounded-xl border border-[#DDE9D6] object-contain"
                    src={automaticPreviewUrl}
                  />
                ) : null}
              </div>
              {!calibrationComplete && calibrationPoints.length === 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    className="quiet-button px-3 py-2 text-xs"
                    disabled={!videoPreviewUrl || calibrationFrameStatus === "error"}
                    onClick={() => shiftCalibrationFrame(-1)}
                    type="button"
                  >
                    前一秒
                  </button>
                  <button
                    className="quiet-button px-3 py-2 text-xs"
                    disabled={!videoPreviewUrl || calibrationFrameStatus === "error"}
                    onClick={() => shiftCalibrationFrame(1)}
                    type="button"
                  >
                    后一秒
                  </button>
                  <span className="self-center text-xs font-semibold text-slate-500">
                    如果开头是黑场，可以先切换标定帧。
                  </span>
                </div>
              ) : null}
              <div className="relative mt-4 overflow-hidden rounded-2xl bg-[#091016]">
                <video
                  className="block aspect-video w-full object-contain"
                  controls={calibrationComplete}
                  muted
                  onError={() => {
                    setCalibrationFrameStatus("error");
                    setCalibrationFramePreviewUrl(null);
                    setCalibrationFrameError("浏览器无法预览这个视频编码。请换用 H.264 MP4，或先转码后再标定。");
                  }}
                  onLoadedData={() => {
                    if (!Number.isFinite(calibrationVideoRef.current?.duration ?? Number.NaN)) {
                      captureCalibrationFrame();
                    }
                  }}
                  onLoadedMetadata={() => seekCalibrationVideo(undefined, { autoSkipDark: true })}
                  onSeeked={() => captureCalibrationFrame()}
                  playsInline
                  preload="auto"
                  ref={calibrationVideoRef}
                  src={videoPreviewUrl}
                />
                {!calibrationComplete && calibrationFramePreviewUrl ? (
                  <img
                    alt=""
                    className="pointer-events-none absolute inset-0 h-full w-full object-contain"
                    src={calibrationFramePreviewUrl}
                  />
                ) : null}
                {!calibrationComplete ? (
                  <button
                    aria-label={nextCalibrationPoint ? `点击${nextCalibrationPoint.label}` : "标定画面"}
                    className={`absolute inset-0 text-left ${
                      calibrationFrameReady ? "cursor-crosshair bg-black/5" : "cursor-not-allowed bg-black/35"
                    }`}
                    disabled={!calibrationFrameReady}
                    onClick={handleCalibrationClick}
                    type="button"
                  >
                    <span className="absolute left-3 top-3 rounded-full border border-white/15 bg-black/55 px-3 py-1 text-xs font-black text-white shadow-lg">
                      {calibrationFrameReady && nextCalibrationPoint
                        ? `标定中 · ${calibrationPoints.length + 1}/4 · ${nextCalibrationPoint.label}`
                        : "正在准备标定画面"}
                    </span>
                  </button>
                ) : null}
                {!calibrationComplete && calibrationFrameStatus !== "ready" ? (
                  <div className="pointer-events-none absolute inset-0 grid place-items-center px-5 text-center text-white">
                    <div className="max-w-sm rounded-2xl border border-white/15 bg-black/65 px-4 py-3 shadow-xl">
                      <strong className="text-sm">
                        {calibrationFrameStatus === "error" ? "视频预览失败" : "正在读取可标定画面"}
                      </strong>
                      <p className="mt-1 text-xs leading-5 text-white/80">
                        {calibrationFrameError ?? "系统会自动跳过开头黑场，等画面出现后再点选四个场地角。"}
                      </p>
                    </div>
                  </div>
                ) : null}
                {calibrationPoints.map((point, index) => (
                  <span
                    className="pointer-events-none absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white bg-[#22C55E] text-xs font-black text-[#071008] shadow-lg"
                    key={point.id}
                    style={{ left: `${point.viewX}%`, top: `${point.viewY}%` }}
                  >
                    {index + 1}
                  </span>
                ))}
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-4">
                {calibrationPointOrder.map((point, index) => {
                  const selected = calibrationPoints.find((item) => item.id === point.id);
                  return (
                    <div className="rounded-2xl bg-white/75 p-3 text-xs" key={point.id}>
                      <strong className={selected ? "text-[#168A34]" : "text-slate-500"}>
                        {index + 1}. {point.label}
                      </strong>
                      <p className="mt-1 text-slate-500">{selected ? `${selected.x}, ${selected.y}` : "等待点击"}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <Field label="比赛名称">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("matchTitle", event.target.value)}
                value={metadata.matchTitle}
              />
            </Field>
            <Field label="比赛日期">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("matchDate", event.target.value)}
                type="date"
                value={metadata.matchDate}
              />
            </Field>
            <Field label="场地">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("venue", event.target.value)}
                value={metadata.venue}
              />
            </Field>
            <Field label="球员/队伍">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("athleteLabel", event.target.value)}
                value={metadata.athleteLabel}
              />
            </Field>
            <Field label="比赛形式">
              <select
                className="field-input"
                onChange={(event) => updateMetadata("matchFormat", event.target.value as AnalysisUploadMetadata["matchFormat"])}
                value={metadata.matchFormat}
              >
                <option value="doubles">双打</option>
                <option value="singles">单打</option>
              </select>
            </Field>
            <Field label="拍摄角度">
              <select
                className="field-input"
                onChange={(event) => updateMetadata("cameraAngle", event.target.value as AnalysisUploadMetadata["cameraAngle"])}
                value={metadata.cameraAngle}
              >
                <option value="elevated">高位俯拍</option>
                <option value="baseline">底线视角</option>
                <option value="sideline">边线视角</option>
                <option value="unknown">未知</option>
              </select>
            </Field>
            <Field label="水平">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("level", event.target.value)}
                value={metadata.level}
              />
            </Field>
          </div>

          {error ? (
            <div className="mt-4">
              <DiagnosticNoticeCard notice={error} />
            </div>
          ) : null}

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button className="green-button" disabled={!canSubmit || isSubmitting} onClick={handleSubmit} type="button">
              {isSubmitting ? submitCopy : "开始真实分析"}
              <ArrowRight size={17} aria-hidden="true" />
            </button>
            <button className="quiet-button" onClick={() => onNavigate("/vision")} type="button">
              查看演示工作台
            </button>
            <button className="quiet-button" onClick={() => onNavigate("/analysis/tasks")} type="button">
              查看任务管理
            </button>
          </div>
        </section>
      </section>
    </PageFrame>
  );
}

function Field({ children, label }: { children: ReactNode; label: string }) {
  return (
    <label className="grid gap-2">
      <span className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function DiagnosticNoticeCard({ notice, tone = "error" }: { notice: DiagnosticNotice; tone?: "error" | "info" }) {
  const visibleDetails = (notice.detailItems ?? []).filter(
    (item): item is [string, string | number] => item[1] !== undefined && item[1] !== null && `${item[1]}`.trim() !== ""
  );
  const toneClass =
    tone === "error"
      ? "border-[#FF4D4F]/30 bg-[#FF4D4F]/10 text-[#C92A2A]"
      : "border-[#2F80ED]/25 bg-[#2F80ED]/10 text-[#1E63B6]";

  return (
    <div className={`rounded-2xl border p-3 text-sm ${toneClass}`}>
      <strong className="font-black">{notice.title}</strong>
      <p className="mt-1 font-semibold leading-6">{notice.body}</p>
      {visibleDetails.length ? (
        <dl className="mt-3 grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
          {visibleDetails.map(([label, value]) => (
            <div className="rounded-xl bg-white/65 p-2" key={label}>
              <dt className="font-black text-slate-500">{label}</dt>
              <dd className="mt-1 break-words font-semibold text-[#14241B]">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

/**
 * 分析任务状态详情页
 */
function AnalysisJobPage({ jobId, onNavigate }: { jobId: string; onNavigate: NavigateFn }) {
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

function StatusState({
  body,
  notice,
  onNavigate,
  title,
}: {
  body: string;
  notice?: DiagnosticNotice | null;
  onNavigate: NavigateFn;
  title: string;
}) {
  return (
    <PageFrame>
      <section className="sport-card p-8 text-center">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">分析任务</p>
        <h1 className="mt-3 text-4xl font-black text-[#14241B]">{title}</h1>
        <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-600">{body}</p>
        {notice ? (
          <div className="mx-auto mt-5 max-w-3xl text-left">
            <DiagnosticNoticeCard notice={notice} />
          </div>
        ) : null}
        <div className="mt-6 flex justify-center gap-3">
          <button className="green-button" onClick={() => onNavigate("/analysis/new")} type="button">
            上传新视频
          </button>
          <button className="quiet-button" onClick={() => onNavigate("/analysis/tasks")} type="button">
            返回任务管理
          </button>
          <button className="quiet-button" onClick={() => onNavigate("/vision")} type="button">
            查看演示
          </button>
        </div>
      </section>
    </PageFrame>
  );
}

function AnalysisDetailsPage({ jobId, onNavigate }: { jobId: string; onNavigate: NavigateFn }) {
  const { error, job, report, result } = useAnalysisResultReport(jobId);

  if (job === undefined || report === undefined) {
    return <StatusState title="正在加载分析详情" body="正在读取任务元数据、报告和算法结果。" onNavigate={onNavigate} />;
  }

  if (error) {
    return <StatusState title={error.title} body={error.body} notice={error} onNavigate={onNavigate} />;
  }

  if (!job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，可能已经被删除。`} onNavigate={onNavigate} />;
  }

  if (isActiveAnalysisJob(job)) {
    return <AnalysisJobPage jobId={jobId} onNavigate={onNavigate} />;
  }

  if (job.status === "failed") {
    return (
      <StatusState
        title="分析任务失败"
        body={job.publicErrorMessage ?? job.errorMessage ?? "该任务没有生成可用分析详情，请返回任务管理或重新上传。"}
        notice={{
          title: "失败位置",
          body: job.publicErrorMessage ?? job.errorMessage ?? "请重新上传或检查后端日志。",
          detailItems: [
            ["错误码", job.errorCode],
            ["任务 ID", job.id],
            ["失败阶段", job.stages.find((stage) => stage.status === "failed")?.label ?? job.stage],
          ],
        }}
        onNavigate={onNavigate}
      />
    );
  }

  if (job.status === "canceled") {
    return (
      <StatusState
        title="分析任务已取消"
        body="该任务没有生成分析详情。可以返回任务管理删除记录，或重新上传创建新任务。"
        notice={{
          title: "取消记录",
          body: "任务在完成前被取消，保留记录用于追踪执行过程。",
          detailItems: [
            ["任务 ID", job.id],
            ["取消时间", job.canceledAt ? formatDateTime(job.canceledAt) : undefined],
          ],
        }}
        onNavigate={onNavigate}
      />
    );
  }

  const analysis = report ?? demoReport;
  const stageSummary = job.stages.filter((stage) => stage.status === "done").length;
  const trackCount = result?.tracks.length ?? 0;
  const trackIds = new Set(result?.tracks.map((track) => track.track_id) ?? []);
  const hasProjection = trackCount > 0;

  return (
    <PageFrame>
      <section className="sport-card overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.42fr] lg:p-8">
          <div>
            <button
              className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
              onClick={() => onNavigate("/analysis/tasks")}
              type="button"
            >
              <ArrowRight className="rotate-180" size={16} aria-hidden="true" />
              返回任务管理
            </button>
            <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
              <LineChart size={16} aria-hidden="true" />
              分析详情
            </p>
            <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">{job.metadata.matchTitle}</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
              当前页面保留任务元数据、算法状态和标准匹克球场二维平面图。坐标转换和人员位移捕捉完成后，会在同一张 20 x 44 ft 球场上投影可视化。
            </p>
          </div>
          <div className="rounded-3xl border border-[#22C55E]/25 bg-[#22C55E]/10 p-6">
            <span className="text-sm font-bold text-[#168A34]">状态摘要</span>
            <strong className="mt-4 block text-4xl font-black text-[#13A12C]">{analysisStatusMeta(job.status).label}</strong>
            <p className="mt-3 text-sm font-semibold leading-6 text-slate-600">
              {stageSummary} 个阶段完成 · {trackIds.size} 条球员轨迹 · {trackCount} 个投影点
            </p>
            <button className="mt-5 green-button w-full" onClick={() => onNavigate(`/analysis/${job.id}/vision`)} type="button">
              打开视频分析
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_380px]">
        <StandardCourtPlan tracks={result?.tracks ?? []} />
        <aside className="grid gap-5">
          <article className="sport-card p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">任务元数据</p>
            <dl className="mt-4 grid gap-2 text-sm">
              <RailMeta label="视频文件" value={job.metadata.fileName} />
              <RailMeta label="比赛日期" value={job.metadata.matchDate} />
              <RailMeta label="场地" value={job.metadata.venue} />
              <RailMeta label="球员/队伍" value={job.metadata.athleteLabel} />
              <RailMeta label="比赛形式" value={job.metadata.matchFormat === "doubles" ? "双打" : "单打"} />
              <RailMeta label="拍摄角度" value={cameraAngleLabel(job.metadata.cameraAngle)} />
              <RailMeta label="分析模式" value={analysisModeLabel(job.analysisMode)} />
              <RailMeta label="报告 ID" value={analysis.reportId} />
            </dl>
          </article>

          <article className="sport-card p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">投影准备</p>
            <div className="mt-4 grid gap-3">
              <ProjectionReadiness label="四角标定" ready={Boolean(job.calibrationId)} body={job.calibrationId ?? "缺少标定时无法进行真实坐标投影"} />
              <ProjectionReadiness label="球员轨迹" ready={hasProjection} body={hasProjection ? `${trackCount} 个标准球场坐标点` : "尚未生成可用人员位移轨迹"} />
              <ProjectionReadiness label="可视化状态" ready={false} body="热力图、位移轨迹和人员分布后续接入" />
            </div>
          </article>
        </aside>
      </section>
    </PageFrame>
  );
}

function ProjectionReadiness({ body, label, ready }: { body: string; label: string; ready: boolean }) {
  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-3">
      <div className="flex items-center justify-between gap-3">
        <strong className="text-sm text-[#14241B]">{label}</strong>
        <span className={`rounded-full px-2.5 py-1 text-xs font-black ${ready ? "bg-[#22C55E]/14 text-[#168A34]" : "bg-slate-100 text-slate-600"}`}>
          {ready ? "就绪" : "待接入"}
        </span>
      </div>
      <p className="mt-2 text-xs font-semibold leading-5 text-slate-500">{body}</p>
    </div>
  );
}

function StandardCourtPlan({ tracks }: { tracks: AnalysisPipelineResult["tracks"] }) {
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [showFragments, setShowFragments] = useState(false);
  const [inspectedPointKey, setInspectedPointKey] = useState<string | null>(null);
  const trackSummaries = useMemo(() => buildCourtTrackSummaries(tracks), [tracks]);
  const selectedTrack = trackSummaries.find((track) => track.trackId === selectedTrackId);
  const visibleTracks = useMemo(() => {
    const baseTracks = showFragments ? trackSummaries : trackSummaries.filter((track) => !track.isShortFragment);
    const fallbackTracks = baseTracks.length > 0 ? baseTracks : trackSummaries.slice(0, Math.min(trackSummaries.length, 6));
    return fallbackTracks.slice(0, 6);
  }, [showFragments, trackSummaries]);
  const inspectedPoint = useMemo(() => {
    if (!inspectedPointKey) {
      return null;
    }

    for (const summary of trackSummaries) {
      const point = summary.sampledPoints.find((item) => courtPointKey(summary.trackId, item) === inspectedPointKey);
      if (point) {
        return { point, summary };
      }
    }

    return null;
  }, [inspectedPointKey, trackSummaries]);
  const highlightedTracks = selectedTrack ? [selectedTrack, ...visibleTracks.filter((track) => track.trackId !== selectedTrack.trackId)] : visibleTracks;
  const hiddenFragmentCount = trackSummaries.filter((track) => track.isShortFragment).length;
  const renderedPointCount = highlightedTracks.reduce((total, track) => total + track.sampledPoints.length, 0);
  const hasProjectedTracks = trackSummaries.length > 0;

  return (
    <article className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">标准球场二维平面图</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">20 ft x 44 ft 投影底图</h2>
        </div>
        <span className="rounded-full border border-[#DDE9D6] bg-white/80 px-3 py-1 text-xs font-black text-slate-500">
          坐标系：x 0-20 · y 0-44
        </span>
      </div>

      <div className="mt-4 rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
        <p className="text-sm font-semibold leading-6 text-slate-600">
          圆点表示算法估计的球员脚点，经过标定投影到标准场地坐标；它们不是球的落点、击球点或人工标注事件。
          轨迹编号来自视觉跟踪器，代表一段检测到的移动轨迹，不等同于确认的球员姓名。
        </p>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(260px,420px)_minmax(0,1fr)]">
        <div className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
          <svg className="mx-auto block aspect-[20/44] max-h-[760px] w-full max-w-[420px]" viewBox="-2 -2 24 48" role="img" aria-label="标准匹克球球场二维平面图">
            <rect x="0" y="0" width="20" height="44" rx="0.2" fill="#DDEFE2" stroke="#173321" strokeWidth="0.24" />
            <rect x="0" y="15" width="20" height="14" fill="#C7E7D5" opacity="0.85" />
            <line x1="0" x2="20" y1="22" y2="22" stroke="#173321" strokeWidth="0.32" />
            <line x1="0" x2="20" y1="15" y2="15" stroke="#173321" strokeWidth="0.22" />
            <line x1="0" x2="20" y1="29" y2="29" stroke="#173321" strokeWidth="0.22" />
            <line x1="10" x2="10" y1="0" y2="15" stroke="#173321" strokeWidth="0.18" />
            <line x1="10" x2="10" y1="29" y2="44" stroke="#173321" strokeWidth="0.18" />

            <text x="10" y="-0.75" textAnchor="middle" fontSize="1.1" fontWeight="800" fill="#173321">远端底线</text>
            <text x="10" y="22.95" textAnchor="middle" fontSize="1.05" fontWeight="800" fill="#173321">Net</text>
            <text x="10" y="45.4" textAnchor="middle" fontSize="1.1" fontWeight="800" fill="#173321">近端底线</text>
            <text x="10" y="18.3" textAnchor="middle" fontSize="1" fontWeight="800" fill="#168A34">非截击区 7 ft</text>
            <text x="5" y="8" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">远端左发球区</text>
            <text x="15" y="8" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">远端右发球区</text>
            <text x="5" y="37" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">近端左发球区</text>
            <text x="15" y="37" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">近端右发球区</text>

            {hasProjectedTracks ? (
              highlightedTracks.map((summary) => (
                <CourtTrackSvgLayer
                  dimmed={Boolean(selectedTrack && selectedTrack.trackId !== summary.trackId)}
                  inspectedPointKey={inspectedPointKey}
                  key={summary.trackId}
                  onInspectPoint={setInspectedPointKey}
                  selected={selectedTrack?.trackId === summary.trackId}
                  summary={summary}
                />
              ))
            ) : (
              <g>
                <rect x="2.3" y="19.6" width="15.4" height="4.8" rx="0.6" fill="white" opacity="0.88" />
                <text x="10" y="21.35" textAnchor="middle" fontSize="0.86" fontWeight="800" fill="#64748B">
                  暂无人员位移投影
                </text>
                <text x="10" y="22.75" textAnchor="middle" fontSize="0.68" fontWeight="700" fill="#64748B">
                  需要完成标定和球员脚点投影
                </text>
              </g>
            )}
          </svg>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs font-black text-slate-500">
            <span className="rounded-2xl bg-white/80 px-2 py-2">起点：空心圆</span>
            <span className="rounded-2xl bg-white/80 px-2 py-2">最新：实心圆</span>
            <span className="rounded-2xl bg-white/80 px-2 py-2">中间：小点</span>
          </div>
        </div>

        <div className="grid content-start gap-4">
          <div className="grid gap-3 rounded-3xl border border-[#DDE9D6] bg-white/78 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">轨迹图例</p>
                <p className="mt-1 text-sm font-semibold text-slate-500">
                  {trackSummaries.length} 条轨迹 · {tracks.length} 个原始投影点 · 当前绘制 {renderedPointCount} 个采样点
                </p>
              </div>
              <button className="quiet-button px-3 py-2 text-xs" onClick={() => setSelectedTrackId(null)} type="button">
                显示全部
              </button>
            </div>
            <label className="inline-flex items-center gap-2 text-sm font-bold text-slate-600">
              <input checked={showFragments} className="size-4 accent-[#168A34]" onChange={(event) => setShowFragments(event.target.checked)} type="checkbox" />
              显示短片段
              {hiddenFragmentCount > 0 ? <span className="text-xs text-slate-400">({hiddenFragmentCount} 条)</span> : null}
            </label>
            <p className="text-xs font-semibold leading-5 text-slate-500">
              默认优先显示持续时间更长、点数更多的主要轨迹；短片段可能来自遮挡、漏检或重新分配 ID。
            </p>
          </div>

          {hasProjectedTracks ? (
            <div className="grid max-h-[430px] gap-3 overflow-y-auto pr-1">
              {trackSummaries.map((summary) => (
                <button
                  className={`rounded-2xl border p-4 text-left transition ${
                    selectedTrackId === summary.trackId
                      ? "border-[#168A34] bg-[#22C55E]/12 shadow-sm"
                      : "border-[#DDE9D6] bg-white/80 hover:border-[#22C55E]/60"
                  }`}
                  key={summary.trackId}
                  onClick={() => setSelectedTrackId(selectedTrackId === summary.trackId ? null : summary.trackId)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <span className="inline-flex items-center gap-2 text-base font-black text-[#14241B]">
                        <span className="size-3 rounded-full" style={{ backgroundColor: summary.color }} />
                        {summary.label}
                      </span>
                      <p className="mt-1 text-xs font-semibold text-slate-500">原始 ID：{summary.trackId}</p>
                    </div>
                    {summary.isShortFragment ? (
                      <span className="shrink-0 rounded-full bg-[#FF9500]/12 px-2.5 py-1 text-xs font-black text-[#A45A00]">短片段</span>
                    ) : (
                      <span className="shrink-0 rounded-full bg-[#22C55E]/14 px-2.5 py-1 text-xs font-black text-[#168A34]">主要</span>
                    )}
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-bold text-slate-600">
                    <span>点数 {summary.pointCount}</span>
                    <span>采样 {summary.sampledPoints.length}</span>
                    <span>{formatTrackTimeRange(summary)}</span>
                    <span>置信度 {formatPercent(summary.averageConfidence) ?? "未知"}</span>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-[#DDE9D6] bg-white/72 p-5">
              <p className="text-sm font-black text-[#14241B]">没有可解释的轨迹点</p>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">
                当前任务可能缺少标定、未检测到球员脚点，或后端没有生成标准场地坐标。
              </p>
            </div>
          )}

          <div className="rounded-3xl border border-[#DDE9D6] bg-white/78 p-4">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">点位检查</p>
            {inspectedPoint ? (
              <dl className="mt-3 grid gap-2 text-sm">
                <RailMeta label="轨迹" value={`${inspectedPoint.summary.label} · ID ${inspectedPoint.summary.trackId}`} />
                <RailMeta label="时间" value={formatSeconds(inspectedPoint.point.timestamp_seconds) ?? "未知"} />
                <RailMeta label="帧号" value={`#${inspectedPoint.point.frame_index}`} />
                <RailMeta label="场地坐标" value={`x ${inspectedPoint.point.court_point.x.toFixed(2)} ft · y ${inspectedPoint.point.court_point.y.toFixed(2)} ft`} />
                <RailMeta label="置信度" value={formatPercent(inspectedPoint.point.confidence) ?? "未知"} />
              </dl>
            ) : (
              <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">点击场地图上的任意轨迹点，可查看它来自哪条轨迹、哪个时间和哪个标准场地坐标。</p>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function CourtTrackSvgLayer({
  dimmed,
  inspectedPointKey,
  onInspectPoint,
  selected,
  summary,
}: {
  dimmed: boolean;
  inspectedPointKey: string | null;
  onInspectPoint: (key: string) => void;
  selected: boolean;
  summary: CourtTrackSummary;
}) {
  const pathPoints = summary.sampledPoints.map((point) => `${point.court_point.x},${point.court_point.y}`).join(" ");
  const opacity = dimmed ? 0.24 : 0.9;

  return (
    <g opacity={opacity}>
      {pathPoints ? (
        <polyline
          fill="none"
          points={pathPoints}
          stroke={summary.color}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={selected ? 0.42 : 0.28}
        />
      ) : null}
      {summary.sampledPoints.map((point) => {
        const key = courtPointKey(summary.trackId, point);
        const inspected = inspectedPointKey === key;
        return (
          <circle
            aria-label={`${summary.label} ${formatSeconds(point.timestamp_seconds) ?? `#${point.frame_index}`}`}
            cx={point.court_point.x}
            cy={point.court_point.y}
            fill={inspected ? "#D9FF3F" : summary.color}
            key={key}
            onClick={() => onInspectPoint(key)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onInspectPoint(key);
              }
            }}
            r={inspected ? 0.36 : selected ? 0.24 : 0.2}
            role="button"
            stroke="#071008"
            strokeWidth={inspected ? 0.1 : 0.06}
            tabIndex={0}
          />
        );
      })}
      <circle cx={summary.startPoint.court_point.x} cy={summary.startPoint.court_point.y} fill="#F5FAF1" r="0.38" stroke={summary.color} strokeWidth="0.16" />
      <circle cx={summary.latestPoint.court_point.x} cy={summary.latestPoint.court_point.y} fill={summary.color} r="0.42" stroke="#071008" strokeWidth="0.08" />
    </g>
  );
}

function courtPointKey(trackId: string, point: AnalysisPipelineResult["tracks"][number]) {
  return `${trackId}-${point.frame_index}-${point.timestamp_seconds}`;
}

function formatTrackTimeRange(summary: CourtTrackSummary) {
  const start = formatSeconds(summary.startTimeSeconds);
  const end = formatSeconds(summary.endTimeSeconds);

  if (start && end) {
    return `${start} - ${end}`;
  }
  if (start) {
    return `${start} 起`;
  }
  return "时间未知";
}

function cameraAngleLabel(angle: AnalysisUploadMetadata["cameraAngle"]) {
  const labels: Record<AnalysisUploadMetadata["cameraAngle"], string> = {
    baseline: "底线视角",
    sideline: "边线视角",
    elevated: "高位俯拍",
    unknown: "未知",
  };

  return labels[angle];
}

type OverlayLoadState = "idle" | "loading" | "available" | "unavailable" | "failed";

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

function useAnalysisResultReport(jobId?: string) {
  const [loadedResult, setLoadedResult] = useState<{
    error: DiagnosticNotice | null;
    job: AnalysisJobSummary | null;
    jobId: string;
    report: AnalysisReport | null;
    result: AnalysisPipelineResult | null;
    videoSrc?: string;
  } | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let alive = true;

    const load = async () => {
      try {
        const [nextJob, nextReport, nextResult] = await Promise.all([getAnalysisJob(jobId), getAnalysisReport(jobId), getAnalysisResult(jobId)]);
        const pipelineResult = isPipelineResult(nextResult) ? nextResult : null;
        const adaptedReport = nextReport ?? (nextJob && pipelineResult ? adaptPipelineResultToReport(nextJob, pipelineResult) : null);

        if (alive) {
          setLoadedResult({
            error: null,
            job: nextJob,
            jobId,
            report: adaptedReport,
            result: pipelineResult,
            videoSrc: getVideoStreamUrl(pipelineResult?.video_id ?? nextJob?.videoId),
          });
        }
      } catch (error) {
        if (alive) {
          setLoadedResult({
            error: errorToNotice("读取分析结果失败", "无法读取该任务生成的报告或算法结果，请检查后端服务和任务产物。", error),
            job: null,
            jobId,
            report: null,
            result: null,
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
    return { error: null, job: null, report: demoReport, result: null, videoSrc: undefined };
  }

  if (loadedResult?.jobId !== jobId) {
    return {
      error: null,
      job: undefined,
      report: undefined,
      result: undefined,
      videoSrc: undefined,
    };
  }

  return {
    error: loadedResult.error,
    job: loadedResult.job,
    report: loadedResult.report,
    result: loadedResult.result,
    videoSrc: loadedResult.videoSrc,
  };
}

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
        const adaptedReport = nextReport ?? (nextJob && pipelineResult ? adaptPipelineResultToReport(nextJob, pipelineResult) : null);
        const shouldLoadTracking = Boolean(pipelineResult?.artifacts.tracking_overlay_url);
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
    videoSrc: loadedResult.videoSrc,
  };
}

/**
 * 视觉分析工作台页组件
 */
function VisionPage({ jobId, onNavigate, recentJob }: { jobId?: string; onNavigate: NavigateFn; recentJob?: AnalysisJobSummary | null }) {
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
    videoSrc,
  } = useVisualAnalysisReport(jobId);

  if (jobId && (job === undefined || report === undefined)) {
    return <StatusState title="正在加载视觉分析" body="正在读取该任务生成的分析报告。" onNavigate={onNavigate} />;
  }

  if (jobId && error) {
    return <StatusState title={error.title} body={error.body} notice={error} onNavigate={onNavigate} />;
  }

  if (jobId && !job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，无法打开视觉分析。`} onNavigate={onNavigate} />;
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
      />
    );
  }

  if (jobId && !report) {
    return (
      <StatusState
        title="报告尚未生成"
        body="该任务记录已读取，但还没有可用的轻量报告数据。请返回任务管理查看任务状态或稍后重试。"
        onNavigate={onNavigate}
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
  const reportPath = (type: ReportType) =>
    (analysis.jobId ? `/analysis/${analysis.jobId}/reports/${type}` : `/reports/${type}`) as AppPath;
  const supportedActions = analysis.reportActions.filter((action) => supportedReportTypes.includes(action.type));

  if (jobId) {
    return (
      <PageFrame>
        <section className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <button
              className="mb-5 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
              onClick={() => onNavigate("/analysis/tasks")}
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
        </section>

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
              videoSrc={analysis.source === "job" ? overlayVideoSrc ?? videoSrc : undefined}
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
                onClick={() => onNavigate(`/analysis/${recentJob.id}/vision`)}
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
            videoSrc={analysis.source === "job" ? overlayVideoSrc ?? videoSrc : undefined}
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
}: {
  heatmapsManifest: VisualizationManifest | null;
  heatmapsLoadState: OverlayLoadState;
  heatmapsStatus?: string;
  heatmapsDetail?: string;
  scatterManifest: VisualizationManifest | null;
  scatterLoadState: OverlayLoadState;
  scatterStatus?: string;
  scatterDetail?: string;
}) {
  const groups = [
    { title: "位置热力图", manifest: heatmapsManifest, loadState: heatmapsLoadState, status: heatmapsStatus, detail: heatmapsDetail },
    { title: "位置散点图", manifest: scatterManifest, loadState: scatterLoadState, status: scatterStatus, detail: scatterDetail },
  ];
  const hasAnyItems = groups.some((group) => (group.manifest?.items.length ?? 0) > 0);
  if (!hasAnyItems && groups.every((group) => group.loadState === "unavailable" || group.status === "skipped" || !group.status)) {
    return null;
  }

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
  poseOverlay: PoseOverlayArtifact | null;
  poseOverlayLoadState: OverlayLoadState;
  reportPath: (type: ReportType) => AppPath;
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
              onClick={() => onNavigate(`/analysis/${job.id}/details`)}
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
              onClick={() => onNavigate(reportPath(action.type))}
              type="button"
            >
              {action.title}
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          ))}
        </div>
        <button className="quiet-button mt-4 w-full px-4 py-2.5" onClick={() => onNavigate("/analysis/tasks")} type="button">
          返回任务管理
        </button>
      </section>
    </aside>
  );
}

function RailMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[#F5FAF1] p-3">
      <dt className="text-xs font-black uppercase tracking-[0.12em] text-slate-500">{label}</dt>
      <dd className="mt-1 break-words font-semibold text-[#14241B]">{value}</dd>
    </div>
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
  reportPath: (type: ReportType) => AppPath;
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

/**
 * 详细分析报告页组件
 */
function ReportPage({
  jobId,
  onNavigate,
  reportType,
}: {
  jobId?: string;
  onNavigate: NavigateFn;
  reportType: ReportType;
}) {
  const { error, job, report } = useJobReport(jobId);

  if (jobId && (job === undefined || report === undefined)) {
    return <StatusState title="正在加载分析报告" body="正在读取该任务生成的轻量报告数据。" onNavigate={onNavigate} />;
  }

  if (jobId && error) {
    return <StatusState title={error.title} body={error.body} notice={error} onNavigate={onNavigate} />;
  }

  if (jobId && !job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，无法打开报告。`} onNavigate={onNavigate} />;
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
      />
    );
  }

  if (jobId && !report) {
    return (
      <StatusState
        title="报告尚未生成"
        body="该任务记录已读取，但还没有可用的轻量报告数据。请返回任务管理查看任务状态或稍后重试。"
        onNavigate={onNavigate}
      />
    );
  }

  const analysis = report ?? demoReport;
  const supportedDefinitions = analysis.reportDefinitions.filter((item) => supportedReportTypes.includes(item.type));
  const definition =
    supportedDefinitions.find((item) => item.type === reportType) ??
    supportedDefinitions[0] ??
    analysis.reportDefinitions[0];
  const backPath = (analysis.jobId ? `/analysis/${analysis.jobId}/vision` : "/vision") as AppPath;

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

function RecommendedDrills({
  drills = drillRecommendations,
  onNavigate,
}: {
  drills?: DrillRecommendation[];
  onNavigate: NavigateFn;
}) {
  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">推荐训练</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">数据变成训练任务</h2>
        </div>
        <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/training")} type="button">
          查看完整计划
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
      <DrillGrid drills={drills} onNavigate={onNavigate} />
    </section>
  );
}

function DrillGrid({
  drills,
  onNavigate,
}: {
  drills: DrillRecommendation[];
  onNavigate: NavigateFn;
}) {
  return (
    <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {drills.map((drill) => (
        <article
          className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4 transition hover:-translate-y-1 hover:border-[#22C55E]/35 hover:bg-[#F9FFF6]"
          key={drill.id}
        >
          <div className="flex items-start justify-between gap-3">
            <span className="rounded-full border border-[#22C55E]/30 bg-[#22C55E]/12 px-2.5 py-1 text-xs font-black text-[#168A34]">
              {drill.difficulty}
            </span>
            <span className="text-xs font-bold text-slate-500">{drill.duration}</span>
          </div>
          <h3 className="mt-4 text-lg font-black text-[#14241B]">{drill.title}</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">{drill.goal}</p>
          <p className="mt-4 rounded-2xl bg-[#F0F6EA] p-3 text-xs leading-5 text-slate-600">{drill.evidence}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="green-button px-3 py-2 text-xs" onClick={() => onNavigate("/training")} type="button">
              加入训练计划
            </button>
            <button
              className="quiet-button px-3 py-2 text-xs"
              onClick={() => onNavigate(`/reports/${supportedReportTypes.includes(drill.linkedReport) ? drill.linkedReport : "movement"}`)}
              type="button"
            >
              查看依据
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

/**
 * 球场采集管理页组件
 */
function CameraHubPage({ onNavigate }: { onNavigate: NavigateFn }) {
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [sessions, setSessions] = useState<RecordingSession[]>([]);
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResult>>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [newCamera, setNewCamera] = useState<CameraCreateRequest>({
    camera_id: "",
    name: "",
    stream_url: "",
    protocol: "rtsp",
    username: "",
    password: "",
  });

  const [recordingForm, setRecordingForm] = useState<RecordingStartRequest>({
    camera_id: "",
    court_name: "",
    match_format: "doubles",
    camera_angle: "baseline_high",
    fps: 30,
    resolution: "1920x1080",
    auto_analyze_after_stop: true,
  });

  const activeSession = sessions.find((s) => s.status === "recording");
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [cam, rec] = await Promise.all([listCameras(), listRecordings()]);
      setCameras(cam);
      setSessions(rec);
    } catch {
      // backend not available, keep empty
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData, refreshKey]);

  const handleRegisterCamera = async () => {
    if (!newCamera.camera_id || !newCamera.name || !newCamera.stream_url) {
      setError("请填写摄像头 ID、名称和流地址");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await createCamera(newCamera);
      setNewCamera({ camera_id: "", name: "", stream_url: "", protocol: "rtsp", username: "", password: "" });
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  const handleProbe = async (cameraId: string) => {
    try {
      const result = await probeCamera(cameraId);
      setProbeResults((prev) => ({ ...prev, [cameraId]: result }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "探测失败");
    }
  };

  const handleStartRecording = async () => {
    if (!recordingForm.camera_id) {
      setError("请选择摄像头");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await startRecording(recordingForm);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "开始录制失败");
    } finally {
      setLoading(false);
    }
  };

  const handleStopRecording = async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      await stopRecording(sessionId);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "停止录制失败");
    } finally {
      setLoading(false);
    }
  };

  const handleCancelRecording = async (sessionId: string) => {
    if (!window.confirm("确定要取消录制吗？已录制的视频将被丢弃。")) return;
    setLoading(true);
    setError(null);
    try {
      await cancelRecording(sessionId);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "取消录制失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveCamera = async (cameraId: string) => {
    if (!window.confirm(`确定要删除摄像头 ${cameraId} 吗？`)) return;
    try {
      await deleteCamera(cameraId);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const statusLabel = (status: string) => {
    const map: Record<string, string> = { recording: "录制中", completed: "已完成", failed: "失败", canceled: "已取消" };
    return map[status] ?? status;
  };

  const statusColor = (status: string) => {
    const map: Record<string, string> = { recording: "text-red-500 bg-red-50", completed: "text-green-600 bg-green-50", failed: "text-orange-500 bg-orange-50", canceled: "text-gray-400 bg-gray-50" };
    return map[status] ?? "text-gray-500 bg-gray-50";
  };

  return (
    <PageFrame>
      <div className="mb-8">
        <h2 className="text-2xl font-black tracking-tight">球场采集管理</h2>
        <p className="mt-1 text-sm text-slate-500">管理网络摄像头并控制录制会话</p>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-[#FF4D4F]/25 bg-[#FF4D4F]/8 px-5 py-4 text-sm text-[#C92A2A]">
          {error}
          <button className="ml-3 underline" onClick={() => setError(null)} type="button">关闭</button>
        </div>
      )}

      {activeSession && (
        <div className="mb-6 rounded-2xl border border-[#22C55E]/30 bg-[#22C55E]/8 p-5">
          <div className="flex items-center gap-3">
            <span className="flex size-3 animate-pulse rounded-full bg-[#22C55E]" />
            <span className="font-bold text-[#168A34]">正在录制</span>
            <span className="text-sm text-slate-500">{activeSession.camera_id} · {activeSession.court_name}</span>
            <span className="text-sm text-slate-400">{activeSession.started_at}</span>
          </div>
          <div className="mt-3 flex gap-3">
            <button className="green-button px-6 py-2" disabled={loading} onClick={() => handleStopRecording(activeSession.session_id)} type="button">
              停止录制
            </button>
            <button className="quiet-button px-6 py-2" disabled={loading} onClick={() => handleCancelRecording(activeSession.session_id)} type="button">
              取消录制
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        {/* 左侧：摄像头管理 */}
        <section className="space-y-6">
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-6">
            <h3 className="mb-4 flex items-center gap-2 text-lg font-bold">
              <span className="grid size-8 place-items-center rounded-lg bg-[#19B84C]/12 text-[#168A34]">
                <Camera size={16} />
              </span>
              摄像头列表
            </h3>
            {cameras.length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-400">暂无注册摄像头</p>
            ) : (
              <div className="space-y-3">
                {cameras.map((cam) => {
                  const probe = probeResults[cam.camera_id];
                  return (
                    <div key={cam.camera_id} className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-bold text-[#17231D]">{cam.name}</span>
                          <span className="ml-2 text-xs text-slate-400">({cam.camera_id})</span>
                        </div>
                        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${probe?.online ? "text-[#168A34] bg-[#22C55E]/12" : "text-slate-400 bg-slate-100"}`}>
                          <span className={`size-2 rounded-full ${probe?.online ? "bg-[#22C55E]" : "bg-slate-300"}`} />
                          {probe?.online ? "在线" : probe ? "离线" : "未检测"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{cam.stream_url}</p>
                      {probe?.online && probe.resolution && (
                        <p className="mt-1 text-xs text-slate-400">分辨率: {probe.resolution} · 延迟: {probe.latency_ms}ms</p>
                      )}
                      {probe && !probe.online && probe.error_message && (
                        <p className="mt-1 text-xs text-[#C92A2A]">{probe.error_message}</p>
                      )}
                      <div className="mt-3 flex gap-2">
                        <button className="quiet-button px-3 py-1.5 text-xs" onClick={() => handleProbe(cam.camera_id)} type="button">
                          探测
                        </button>
                        <button
                          className="quiet-button px-3 py-1.5 text-xs"
                          disabled={!!activeSession}
                          onClick={() => {
                            setRecordingForm((f) => ({ ...f, camera_id: cam.camera_id }));
                          }}
                          type="button"
                        >
                          录制
                        </button>
                        <button className="quiet-button px-3 py-1.5 text-xs text-[#C92A2A]" onClick={() => handleRemoveCamera(cam.camera_id)} disabled={!!activeSession} type="button">
                          删除
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 注册摄像头表单 */}
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-6">
            <h3 className="mb-4 text-lg font-bold">注册新摄像头</h3>
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <input
                  className="field-input col-span-2"
                  placeholder="摄像头 ID (例: baseline-cam)"
                  value={newCamera.camera_id}
                  onChange={(e) => setNewCamera((c) => ({ ...c, camera_id: e.target.value }))}
                />
                <select
                  className="field-input"
                  value={newCamera.protocol}
                  onChange={(e) => setNewCamera((c) => ({ ...c, protocol: e.target.value as "rtsp" | "rtmp" | "http" }))}
                >
                  <option value="rtsp">RTSP</option>
                  <option value="rtmp">RTMP</option>
                  <option value="http">HTTP</option>
                </select>
              </div>
              <input
                className="field-input"
                placeholder="摄像头名称"
                value={newCamera.name}
                onChange={(e) => setNewCamera((c) => ({ ...c, name: e.target.value }))}
              />
              <input
                className="field-input"
                placeholder="流地址 (rtsp://...)"
                value={newCamera.stream_url}
                onChange={(e) => setNewCamera((c) => ({ ...c, stream_url: e.target.value }))}
              />
              <div className="grid grid-cols-2 gap-3">
                <input
                  className="field-input"
                  placeholder="用户名 (可选)"
                  value={newCamera.username ?? ""}
                  onChange={(e) => setNewCamera((c) => ({ ...c, username: e.target.value || undefined }))}
                />
                <input
                  className="field-input"
                  type="password"
                  placeholder="密码 (可选)"
                  value={newCamera.password ?? ""}
                  onChange={(e) => setNewCamera((c) => ({ ...c, password: e.target.value || undefined }))}
                />
              </div>
              <button className="green-button w-full py-2.5" disabled={loading} onClick={handleRegisterCamera} type="button">
                {loading ? "注册中..." : "注册摄像头"}
              </button>
            </div>
          </div>
        </section>

        {/* 右侧：录制控制 + 历史 */}
        <section className="space-y-6">
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-6">
            <h3 className="mb-4 text-lg font-bold">开始录制</h3>
            <div className="space-y-3">
              <select
                className="field-input"
                value={recordingForm.camera_id}
                onChange={(e) => setRecordingForm((f) => ({ ...f, camera_id: e.target.value }))}
              >
                <option value="">选择摄像头...</option>
                {cameras.map((cam) => (
                  <option key={cam.camera_id} value={cam.camera_id}>{cam.name} ({cam.camera_id})</option>
                ))}
              </select>
              <input
                className="field-input"
                placeholder="球场名称"
                value={recordingForm.court_name ?? ""}
                onChange={(e) => setRecordingForm((f) => ({ ...f, court_name: e.target.value }))}
              />
              <div className="grid grid-cols-2 gap-3">
                <select
                  className="field-input"
                  value={recordingForm.match_format ?? "doubles"}
                  onChange={(e) => setRecordingForm((f) => ({ ...f, match_format: e.target.value as "singles" | "doubles" }))}
                >
                  <option value="doubles">双打</option>
                  <option value="singles">单打</option>
                </select>
                <select
                  className="field-input"
                  value={recordingForm.camera_angle ?? "baseline_high"}
                  onChange={(e) => setRecordingForm((f) => ({ ...f, camera_angle: e.target.value }))}
                >
                  <option value="baseline_high">底线高角度</option>
                  <option value="sideline">侧边</option>
                  <option value="overhead">俯视</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  className="size-4 accent-[#22C55E]"
                  checked={recordingForm.auto_analyze_after_stop ?? true}
                  onChange={(e) => setRecordingForm((f) => ({ ...f, auto_analyze_after_stop: e.target.checked }))}
                />
                停止后自动创建分析任务
              </label>
              <button className="green-button w-full py-2.5" disabled={loading || !!activeSession} onClick={handleStartRecording} type="button">
                {activeSession ? "已有录制进行中" : loading ? "开始中..." : "开始录制"}
              </button>
            </div>
          </div>

          {/* 录制历史 */}
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-6">
            <h3 className="mb-4 text-lg font-bold">录制历史</h3>
            {sessions.length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-400">暂无录制记录</p>
            ) : (
              <div className="space-y-3 max-h-[500px] overflow-y-auto">
                {sessions.map((session) => (
                  <div key={session.session_id} className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-4">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm text-[#17231D]">{session.session_id}</span>
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusColor(session.status)}`}>
                        {statusLabel(session.status)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">
                      {session.camera_id} · {session.court_name} · {session.duration_sec ? `${session.duration_sec.toFixed(0)}秒` : ""}
                    </p>
                    {session.auto_analysis_job_id && (
                      <button
                        className="mt-2 text-xs font-semibold text-[#2F80ED] hover:underline"
                        onClick={() => onNavigate(`/analysis/${session.auto_analysis_job_id}`)}
                        type="button"
                      >
                        查看分析任务 →
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </PageFrame>
  );
}

/**
 * 训练建议页组件
 */
function TrainingPage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Dumbbell size={16} aria-hidden="true" />
            训练与进展
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">训练建议页</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            每个建议都绑定报告证据，让球员知道为什么练、怎么练、下一次如何验证。
          </p>
        </div>
        <div className="sport-card p-5">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="text-[#168A34]" size={24} aria-hidden="true" />
            <div>
              <strong className="text-xl font-black text-[#14241B]">学习 · 练习 · 复测</strong>
              <p className="mt-1 text-sm text-slate-600">报告问题 → 教学内容 → 训练任务 → 下次复测目标</p>
            </div>
          </div>
          <div className="mt-5 grid gap-3">
            {trainingRecommendations.map((item) => (
              <article className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4" key={item.id}>
                <strong className="text-[#14241B]">{item.title}</strong>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.practiceTask}</p>
                <div className="mt-3 h-2 rounded-full bg-[#DFEADA]">
                  <span
                    className="block h-full rounded-full bg-[#22C55E]"
                    style={{
                      width: `${Math.min(
                        (Math.abs(item.progress.current - item.progress.previous) /
                          Math.abs(item.progress.target - item.progress.previous || 1)) *
                          100,
                        100
                      )}%`,
                    }}
                  />
                </div>
                <p className="mt-2 text-xs font-semibold text-[#168A34]">{item.nextTarget}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6">
        <RecommendedDrills onNavigate={onNavigate} />
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-[0.75fr_1.25fr]">
        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">教学内容</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">教学视频与动作对标占位</h2>
          <div className="mt-5 aspect-video rounded-3xl border border-[#DDE9D6] bg-[#F0F7EA] p-5">
            <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-[#BFD5B8] bg-white/70">
              <div className="text-center">
                <span className="mx-auto grid size-14 place-items-center rounded-full bg-[#22C55E]/15 text-[#168A34]">
                  <Play size={26} fill="currentColor" aria-hidden="true" />
                </span>
                <strong className="mt-4 block text-[#14241B]">反手轻吊动作对标</strong>
                <p className="mt-2 text-sm text-slate-500">真实内容接入前的产品级占位</p>
              </div>
            </div>
          </div>
        </article>
        <ProgressChart points={progressPoints} />
      </section>
    </PageFrame>
  );
}

/**
 * 硬件融合预览页组件（二期规划）
 */
function HardwarePage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Cpu size={16} aria-hidden="true" />
            二期硬件融合
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">{hardwarePreview.phaseLabel}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">{hardwarePreview.disclaimer}</p>
          <button className="mt-7 quiet-button" onClick={() => onNavigate("/vision")} type="button">
            返回视频分析
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="sport-card p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">TENG 阵列</p>
              <h2 className="mt-2 text-2xl font-black text-[#14241B]">3x3 甜区触点分布</h2>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-[#22C55E]/30 bg-[#22C55E]/12 px-3 py-2 text-xs font-black text-[#168A34]">
              <ShieldCheck size={14} aria-hidden="true" />
              模拟数据
            </span>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-3 rounded-[2rem] border border-[#DDE9D6] bg-[#F0F7EA] p-4">
            {hardwarePreview.sweetZone.map((cell) => (
              <span
                className={`aspect-square rounded-2xl border ${
                  cell.id === hardwarePreview.highlightedCellId
                    ? "border-[#22C55E] bg-[#22C55E]"
                    : "border-[#DDE9D6] bg-[#22C55E]/10"
                }`}
                key={cell.id}
                style={{ opacity: Math.max(cell.intensity, 0.22) }}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {hardwarePreview.metrics.map((metric) => (
          <article className="sport-card p-5 transition hover:-translate-y-1 hover:border-[#22C55E]/35" key={metric.id}>
            <Gauge className="text-[#168A34]" size={20} aria-hidden="true" />
            <span className="mt-4 block text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{metric.label}</span>
            <strong className="mt-2 block text-3xl font-black text-[#14241B]">{metric.value}</strong>
            <p className="mt-3 text-sm leading-6 text-slate-600">{metric.detail}</p>
          </article>
        ))}
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-2">
        {hardwarePreview.fusionPoints.map((point) => (
          <article className="sport-card p-5 sm:p-6" key={point.insight}>
            <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-center">
              <FusionBlock icon={<Camera size={18} aria-hidden="true" />} label="视觉" value={point.visual} />
              <Zap className="hidden text-[#D9FF3F] md:block" size={22} aria-hidden="true" />
              <FusionBlock icon={<Radar size={18} aria-hidden="true" />} label="球拍" value={point.sensor} />
            </div>
            <p className="mt-5 rounded-2xl border border-[#22C55E]/25 bg-[#22C55E]/12 p-4 text-sm font-semibold leading-6 text-[#168A34]">
              {point.insight}
            </p>
          </article>
        ))}
      </section>

      <section className="mt-6 sport-card p-5 sm:p-6">
        <div className="flex items-start gap-4">
          <BadgeCheck className="mt-1 text-[#168A34]" size={23} aria-hidden="true" />
          <div>
            <h2 className="text-2xl font-black text-[#14241B]">未来数据替换路径</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              当前页面数值全部来自本地模拟数据。未来真实 TENG 与 IMU 数据可以替换硬件模拟数据对象，
              视觉报告数据仍保持独立，便于做视觉 + 体感融合。
            </p>
          </div>
        </div>
      </section>
    </PageFrame>
  );
}

function FusionBlock({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4">
      <span className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-[#168A34]">
        {icon}
        {label}
      </span>
      <strong className="mt-3 block text-base leading-6 text-[#14241B]">{value}</strong>
    </div>
  );
}

export default App;
