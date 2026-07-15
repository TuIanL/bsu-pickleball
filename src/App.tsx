// 导入 Lucide 图标库
import {
  ArrowRight,
  BadgeCheck,
  Brain,
  Camera,
  CheckCircle2,
  ChevronRight,
  Clock,
  Cpu,
  Dumbbell,
  Edit3,
  Gauge,
  LayoutDashboard,
  LineChart,
  Play,
  PlusCircle,
  Radar,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Timer,
  Trash2,
  Upload,
  X,
  Zap,
} from "lucide-react";
// 导入 React 核心钩子和类型
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { LandingPage } from "./pages/LandingPage";
import { UploadModePage } from "./pages/UploadModePage";
import { CaptureHomePage } from "./pages/CaptureHomePage";
import { CaptureWizardPage } from "./pages/CaptureWizardPage";
import CaptureConsolePage from "./pages/CaptureConsolePage";
import { SegmentManagerPage } from "./pages/SegmentManagerPage";
import { RecordingWorkspacePage } from "./pages/RecordingWorkspacePage";
import { TasksPage } from "./pages/TasksPage";
import { AppShell } from "./components/platform/AppShell";
import { MetricCard } from "./components/platform/MetricCard";
import { Modal } from "./components/platform/Modal";
import { ProgressChart } from "./components/platform/ProgressChart";
import { ReportVisualization } from "./components/platform/ReportVisualization";
import { SkillRatings } from "./components/platform/SkillRatings";
import StructuredHeatmap from "./components/platform/StructuredHeatmap";
import StructuredScatterPlot from "./components/platform/StructuredScatterPlot";
import { VideoAnalysisCard } from "./components/platform/VideoAnalysisCard";
import { FieldSessionGroupCard } from "./components/platform/FieldSessionGroupCard";
import { groupRecordingsByFieldSession } from "./services/recordingGrouping";
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
import type { RouteState, NavigateFn } from "./app/navigationTypes";
import { parseLocation } from "./app/router";
import { AppRouter } from "./app/AppRouter";
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
  FieldSession,
  FieldSessionCreate,
  InsightTone,
  PoseOverlayArtifact,
  ProbeResult,
  RecordingSession,
  RecordingStartRequest,
  SyncRecordingSession,
  ReportType,
  ServeEventsArtifact,
  SessionTimelineEvent,
  StructuredVisualizationData,
  TimelineEventCreate,
  TimelineEventUpdate,
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
  getStructuredVizData,
  getAnalysisResult,
  getAnalysisReport,
  getRecentAnalysisJob,
  getTrackingOverlay,
  deleteAnalysisJob,
  deleteAnalysisJobs,
  getVideoStreamUrl,
  getCameraPreviewUrl,
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
  deleteRecording,
  listSyncRecordings,
  deleteSyncRecording,
  createFieldSession,
  listFieldSessions,
  startFieldSession,
  completeFieldSession,
  archiveFieldSession,
  deleteFieldSession,
  createTimelineEvent,
  listTimelineEvents,
  updateTimelineEvent,
  deleteTimelineEvent,
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
import { quickEventsForMode, ACTION_TO_EVENT_TYPE, type QuickEventDef } from "./services/timelineQuickEvents";


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


function App() {
  // 初始化路由状态
  const [route, setRoute] = useState<RouteState>(() => parseLocation(window.location.pathname, window.location.search));
  const [recentJob, setRecentJob] = useState<AnalysisJobSummary | null>(() => getRecentAnalysisJob());

  // 自定义导航函数，支持平滑滚动到顶部
  const navigate = useCallback((path: AppPath | `/upload` | `/upload?${string}`) => {
    const url = new URL(path, window.location.origin);
    const nextRoute = parseLocation(url.pathname, url.search);
    window.history.pushState({}, "", path);
    setRoute(nextRoute);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  // 监听浏览器前进/后退事件
  useEffect(() => {
    const handlePopState = () => setRoute(parseLocation(window.location.pathname, window.location.search));
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

  return (
    <AppShell activePath={route.path} onNavigate={navigate}>
      <AppRouter route={route} onNavigate={navigate} recentJob={recentJob} />
    </AppShell>
  );
}

export default App;
