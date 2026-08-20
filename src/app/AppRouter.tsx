import { lazy, Suspense, useMemo } from "react";
import type { AnalysisJobSummary } from "../types/report";
import type { RouteState, NavigateFn } from "./navigationTypes";
import { LandingPage } from "../pages/LandingPage";
import { CaptureHomePage } from "../pages/CaptureHomePage";
import { CaptureWizardPage } from "../pages/CaptureWizardPage";
import CaptureConsolePage from "../pages/CaptureConsolePage";
import { SegmentManagerPage } from "../pages/SegmentManagerPage";
import { RecordingWorkspacePage } from "../pages/RecordingWorkspacePage";
import { RecordingAnalyzePage } from "../pages/RecordingAnalyzePage";
import { MultiViewAnalysisSetupPage } from "../pages/MultiViewAnalysisSetupPage";
import { SyncCalibrationWorkbenchPage } from "../pages/SyncCalibrationWorkbenchPage";
import { HardwarePage } from "../pages/HardwarePage";
import { TrainingPage } from "../pages/TrainingPage";
import { CameraHubPage } from "../pages/CameraHubPage";
import { AnalysisJobPage } from "../pages/AnalysisJobPage";
import { AnalysisDetailsPage } from "../pages/AnalysisDetailsPage";
import { VisionPage } from "../pages/VisionPage";
import { ReportPage } from "../pages/ReportPage";
import { NewAnalysisPage } from "../pages/NewAnalysisPage";
import { AnalysisTasksPage } from "../pages/AnalysisTasksPage";
import { LibraryPage } from "../pages/LibraryPage";
import { LibraryItemWorkspace } from "../components/library/LibraryItemWorkspace";
import { MultiviewObservabilityPage } from "../pages/MultiviewObservabilityPage";
import { ShowcaseDisplayPage } from "../pages/ShowcaseDisplayPage";

const BallTrajectoryPage = lazy(() =>
  import("../pages/BallTrajectoryPage").then((module) => ({ default: module.BallTrajectoryPage })),
);

interface AppRouterProps {
  route: RouteState;
  onNavigate: NavigateFn;
  recentJob: AnalysisJobSummary | null;
}

export function AppRouter({ route, onNavigate, recentJob }: AppRouterProps) {
  return useMemo(() => {
    switch (route.name) {
      case "upload":
        return <NewAnalysisPage onNavigate={onNavigate} />;
      case "captureHome":
        return <CaptureHomePage onNavigate={onNavigate} />;
      case "captureNew":
        return <CaptureWizardPage onNavigate={onNavigate} />;
      case "captureConsole":
        return <CaptureConsolePage sessionId={route.sessionId} onNavigate={onNavigate} />;
      case "segmentManager":
        return <SegmentManagerPage fieldSessionId={route.fieldSessionId} takeId={route.takeId} onNavigate={onNavigate} />;
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
          <Suspense fallback={<div className="grid min-h-[60vh] place-items-center text-sm text-[#667085]">正在加载球路视图…</div>}>
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
            view={route.view as "overview" | "video" | "analysis" | "trajectory" | "report" | "segments" | "technical"}
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
}
