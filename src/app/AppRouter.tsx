import { Component, lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import type { AnalysisJobSummary } from "../types/report";
import type { RouteState, NavigateFn } from "./navigationTypes";
import { buildLibraryWorkspacePath } from "../services/libraryAnalysisVersion";
const LandingPage = lazy(() => import("../pages/LandingPage").then((m) => ({ default: m.LandingPage })));
const CaptureHomePage = lazy(() => import("../pages/CaptureHomePage").then((m) => ({ default: m.CaptureHomePage })));
const CaptureWizardPage = lazy(() => import("../pages/CaptureWizardPage").then((m) => ({ default: m.CaptureWizardPage })));
const CaptureConsolePage = lazy(() => import("../pages/CaptureConsolePage"));
const ScoringCalibrationWorkbenchPage = lazy(() => import("../pages/ScoringCalibrationWorkbenchPage").then((m) => ({ default: m.ScoringCalibrationWorkbenchPage })));
const RecordingWorkspacePage = lazy(() => import("../pages/RecordingWorkspacePage").then((m) => ({ default: m.RecordingWorkspacePage })));
const RecordingAnalyzePage = lazy(() => import("../pages/RecordingAnalyzePage").then((m) => ({ default: m.RecordingAnalyzePage })));
const MultiViewAnalysisSetupPage = lazy(() => import("../pages/MultiViewAnalysisSetupPage").then((m) => ({ default: m.MultiViewAnalysisSetupPage })));
const SyncCalibrationWorkbenchPage = lazy(() => import("../pages/SyncCalibrationWorkbenchPage").then((m) => ({ default: m.SyncCalibrationWorkbenchPage })));
const HardwarePage = lazy(() => import("../pages/HardwarePage").then((m) => ({ default: m.HardwarePage })));
const TrainingPage = lazy(() => import("../pages/TrainingPage").then((m) => ({ default: m.TrainingPage })));
const CameraHubPage = lazy(() => import("../pages/CameraHubPage").then((m) => ({ default: m.CameraHubPage })));
const AnalysisJobPage = lazy(() => import("../pages/AnalysisJobPage").then((m) => ({ default: m.AnalysisJobPage })));
const AnalysisDetailsPage = lazy(() => import("../pages/AnalysisDetailsPage").then((m) => ({ default: m.AnalysisDetailsPage })));
const VisionPage = lazy(() => import("../pages/VisionPage").then((m) => ({ default: m.VisionPage })));
const ReportPage = lazy(() => import("../pages/ReportPage").then((m) => ({ default: m.ReportPage })));
const NewAnalysisPage = lazy(() => import("../pages/NewAnalysisPage").then((m) => ({ default: m.NewAnalysisPage })));
const AnalysisTasksPage = lazy(() => import("../pages/AnalysisTasksPage").then((m) => ({ default: m.AnalysisTasksPage })));
const LibraryPage = lazy(() => import("../pages/LibraryPage").then((m) => ({ default: m.LibraryPage })));
const LibraryItemWorkspace = lazy(() => import("../components/library/LibraryItemWorkspace").then((m) => ({ default: m.LibraryItemWorkspace })));
const MultiviewObservabilityPage = lazy(() => import("../pages/MultiviewObservabilityPage").then((m) => ({ default: m.MultiviewObservabilityPage })));
const ShowcaseDisplayPage = lazy(() => import("../pages/ShowcaseDisplayPage").then((m) => ({ default: m.ShowcaseDisplayPage })));

const BallTrajectoryPage = lazy(() =>
  import("../pages/BallTrajectoryPage").then((module) => ({ default: module.BallTrajectoryPage })),
);

class RouteChunkBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="grid min-h-[60vh] place-items-center px-6 text-center text-sm text-[var(--ui-text-secondary-alt)]">
          <div>
            <p className="font-bold text-[var(--ui-ink)]">页面加载失败</p>
            <p className="mt-2">请重试；当前地址和查询参数会保留。</p>
            <button
              type="button"
              className="mt-4 rounded-lg bg-[#14241B] px-4 py-2 text-xs font-bold text-white"
              onClick={() => window.location.reload()}
            >
              重试或刷新
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

interface AppRouterProps {
  route: RouteState;
  onNavigate: NavigateFn;
  recentJob: AnalysisJobSummary | null;
}

export function AppRouter({ route, onNavigate, recentJob }: AppRouterProps) {
  const page = useMemo(() => {
    switch (route.name) {
      case "upload":
        return <NewAnalysisPage onNavigate={onNavigate} />;
      case "captureHome":
        return <CaptureHomePage onNavigate={onNavigate} />;
      case "captureNew":
        return <CaptureWizardPage onNavigate={onNavigate} />;
      case "captureConsole":
        return <CaptureConsolePage sessionId={route.sessionId} onNavigate={onNavigate} />;
      case "legacy-segments-redirect":
        return <LegacySegmentsRedirect takeId={route.takeId} onNavigate={onNavigate} />;
      case "scoringCalibration":
        return <ScoringCalibrationWorkbenchPage fieldSessionId={route.fieldSessionId} takeId={route.takeId} onNavigate={onNavigate} />;
      case "tasks":
        return <AnalysisTasksPage onNavigate={onNavigate} recentJob={recentJob} taskSource={route.taskSource} taskSessionId={route.taskSessionId} />;
      case "new-analysis":
        return <NewAnalysisPage onNavigate={onNavigate} />;
      case "analysis-tasks":
        return <AnalysisTasksPage onNavigate={onNavigate} recentJob={recentJob} taskSource={route.taskSource} taskSessionId={route.taskSessionId} />;
      case "analysis-job":
        return <AnalysisJobPage jobId={route.jobId} onNavigate={onNavigate} />;
      case "analysis-details":
        return <AnalysisDetailsPage jobId={route.jobId} onNavigate={onNavigate} />;
      case "vision":
        return <VisionPage jobId={"jobId" in route ? route.jobId : undefined} onNavigate={onNavigate} recentJob={recentJob} seekToMs={"seekToMs" in route ? route.seekToMs : undefined} />;
      case "ball-trajectory":
        return (
          <Suspense fallback={<div className="grid min-h-[60vh] place-items-center text-sm text-[var(--ui-text-secondary-alt)]">正在加载球路视图…</div>}>
            <BallTrajectoryPage key={route.jobId} jobId={route.jobId} onNavigate={onNavigate} />
          </Suspense>
        );
      case "multiview-observability":
        return <MultiviewObservabilityPage jobId={route.jobId} onNavigate={onNavigate} />;
      case "report":
        return <ReportPage jobId={"jobId" in route ? route.jobId : undefined} reportType={route.reportType} onNavigate={onNavigate} />;
      case "camera-hub":
        return <CameraHubPage onNavigate={onNavigate} />;
      case "training":
        return <TrainingPage onNavigate={onNavigate} />;
      case "hardware":
        return <HardwarePage onNavigate={onNavigate} />;
      case "recordingWorkspace":
        return <RecordingWorkspacePage sessionId={route.sessionId} onNavigate={onNavigate} />;
      case "recording-analyze": {
        const cam = new URLSearchParams(window.location.search).get("cam") as "cam_1" | "cam_2" | null;
        return <RecordingAnalyzePage sessionId={route.sessionId} cam={cam} onNavigate={onNavigate} />;
      }
      case "multiview-setup":
        return <MultiViewAnalysisSetupPage captureTakeId={route.captureTakeId} onNavigate={onNavigate} />;
      case "sync-calibration":
        return <SyncCalibrationWorkbenchPage captureTakeId={route.captureTakeId} onNavigate={onNavigate} returnPath={route.returnPath} />;
      case "showcase":
        return <ShowcaseDisplayPage runtimeId={route.runtimeId} onNavigate={onNavigate} />;
      case "library":
        return <LibraryPage onNavigate={onNavigate} />;
      case "library-item":
        return (
          <LibraryItemWorkspace
            kind={route.kind}
            sourceId={route.sourceId}
            view={route.view as "overview" | "video" | "analysis" | "trajectory" | "landing" | "report" | "technical"}
            onNavigate={onNavigate}
          />
        );
      case "workspace":
        return <LibraryPage onNavigate={onNavigate} />;
      case "landing":
      default:
        return <LandingPage onNavigate={onNavigate} />;
    }
  }, [onNavigate, route, recentJob]);
  return (
    <RouteChunkBoundary key={`${route.name}:${"jobId" in route ? route.jobId : ""}`}>
      <Suspense fallback={<div className="grid min-h-[60vh] place-items-center text-sm text-[var(--ui-text-secondary-alt)]">正在加载页面…</div>}>
        {page}
      </Suspense>
    </RouteChunkBoundary>
  );
}

function LegacySegmentsRedirect({ takeId, onNavigate }: { takeId: string; onNavigate: NavigateFn }) {
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    void import("../services/analysisClient").then(({ getCaptureTake }) => getCaptureTake(takeId)).then((take) => {
      if (!alive) return;
      const kind = take.source_session_type === "sync_recording" ? "sync_recording" : "recording";
      onNavigate(buildLibraryWorkspacePath({ kind, sourceId: take.source_session_id }, { view: "analysis" }), { replace: true });
    }).catch(() => {
      if (alive) setError(true);
    });
    return () => { alive = false; };
  }, [takeId, onNavigate]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 text-center">
        <p className="text-sm font-bold text-[var(--ui-ink)]">无法定位这个采集素材</p>
        <button className="quiet-button mt-4 px-4 py-2" onClick={() => onNavigate("/library", { replace: true })} type="button">返回比赛库</button>
      </div>
    );
  }
  return <div className="grid min-h-[60vh] place-items-center text-sm text-slate-500">正在打开素材分析视图…</div>;
}
