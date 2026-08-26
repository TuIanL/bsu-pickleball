import type { AppShellMode, NavigatePath, NavigationSection, ReportType, RouteState } from "./navigationTypes";
import { parseTaskListContext } from "./navigationContext";

export const supportedReportTypes: ReportType[] = ["performance", "movement", "diagnosis"];

/** analysis 系列路由（transient 流程），按 `return` 推导导航段高亮 */
const ANALYSIS_NAV_ROUTES = new Set<RouteState["name"]>([
  "analysis-job",
  "analysis-details",
  "vision",
  "ball-trajectory",
  "multiview-observability",
  "report",
  "recording-analyze",
  "multiview-setup",
  "sync-calibration",
]);

type RouteMeta = {
  shellMode: AppShellMode;
  navigationSection: NavigationSection | null;
};

const routeMeta = {
  landing: { shellMode: "landing", navigationSection: null },
  upload: { shellMode: "landing", navigationSection: null },
  workspace: { shellMode: "standard", navigationSection: "capture" },
  library: { shellMode: "standard", navigationSection: "library" },
  "library-item": { shellMode: "standard", navigationSection: "library" },
  tasks: { shellMode: "standard", navigationSection: "analysis" },
  captureHome: { shellMode: "standard", navigationSection: "capture" },
  captureNew: { shellMode: "standard", navigationSection: "capture" },
  captureConsole: { shellMode: "capture", navigationSection: "capture" },
  segmentManager: { shellMode: "standard", navigationSection: "capture" },
  scoringCalibration: { shellMode: "standard", navigationSection: "capture" },
  recordingWorkspace: { shellMode: "standard", navigationSection: "videos" },
  "new-analysis": { shellMode: "standard", navigationSection: "analysis" },
  "analysis-tasks": { shellMode: "standard", navigationSection: "analysis" },
  "recording-analyze": { shellMode: "standard", navigationSection: "analysis" },
  "multiview-setup": { shellMode: "standard", navigationSection: "analysis" },
  "sync-calibration": { shellMode: "standard", navigationSection: "analysis" },
  showcase: { shellMode: "landing", navigationSection: null },
  "analysis-job": { shellMode: "standard", navigationSection: "analysis" },
  "analysis-details": { shellMode: "standard", navigationSection: "analysis" },
  vision: { shellMode: "standard", navigationSection: "analysis" },
  "ball-trajectory": { shellMode: "standard", navigationSection: "analysis" },
  "multiview-observability": { shellMode: "standard", navigationSection: "analysis" },
  report: { shellMode: "standard", navigationSection: "reports" },
  "camera-hub": { shellMode: "standard", navigationSection: "devices" },
  training: { shellMode: "standard", navigationSection: "settings" },
  hardware: { shellMode: "standard", navigationSection: "settings" },
} as const satisfies Record<string, RouteMeta>;

export function parsePath(pathname: string): RouteState {
  if (pathname === "/" || pathname === "") {
    return { name: "landing", path: "/", ...routeMeta.landing };
  }

  if (pathname === "/workspace") {
    // D10：工作台保留路由但 canonical redirect 到比赛库（App 层负责 replaceState）
    return { name: "library", path: "/library", ...routeMeta.library };
  }

  if (pathname === "/library") {
    return { name: "library", path: "/library", ...routeMeta.library };
  }

  const libraryItemMatch = pathname.match(/^\/library\/(upload|recording|sync_recording)\/(.+)$/);
  if (libraryItemMatch) {
    const [, kind, sourceId] = libraryItemMatch;
    return {
      name: "library-item",
      path: `/library/${kind}/${sourceId}`,
      kind: kind as "upload" | "recording" | "sync_recording",
      sourceId,
      view: "overview",
      ...routeMeta["library-item"],
    };
  }

  if (pathname === "/sync-calibration") {
    return { name: "sync-calibration", path: "/sync-calibration", captureTakeId: "", ...routeMeta["sync-calibration"] };
  }

  if (pathname === "/upload") {
    return { name: "upload", path: "/upload", ...routeMeta.upload };
  }

  if (pathname.startsWith("/upload?")) {
    const params = new URLSearchParams(pathname.slice("/upload?".length));
    return { name: "upload", path: "/upload", ...routeMeta.upload, videoId: params.get("videoId") ?? undefined, source: params.get("source") ?? undefined };
  }

  if (pathname === "/tasks") {
    return { name: "tasks", path: "/tasks", ...routeMeta.tasks };
  }

  if (pathname === "/capture/new") {
    return { name: "captureNew", path: "/capture/new", ...routeMeta.captureNew };
  }

  if (pathname === "/capture") {
    return { name: "captureHome", path: "/capture", ...routeMeta.captureHome };
  }

  const showcaseMatch = pathname.match(/^\/showcase\/([^/]+)$/);
  if (showcaseMatch) {
    const [, runtimeId] = showcaseMatch;
    return { name: "showcase", path: `/showcase/${runtimeId}`, runtimeId, ...routeMeta.showcase };
  }

  const captureConsoleMatch = pathname.match(/^\/capture\/(.+)$/);

  const segmentManagerMatch = captureConsoleMatch
    ? captureConsoleMatch[1].match(/^(.+)\/takes\/(.+)\/segments$/)
    : null;
  if (segmentManagerMatch) {
    const [, fieldSessionId, takeId] = segmentManagerMatch;
    return { name: "segmentManager", path: `/capture/${fieldSessionId}/takes/${takeId}/segments`, fieldSessionId, takeId, ...routeMeta.segmentManager };
  }

  const scoringCalibrationMatch = captureConsoleMatch
    ? captureConsoleMatch[1].match(/^(.+)\/takes\/(.+)\/scoring-calibration$/)
    : null;
  if (scoringCalibrationMatch) {
    const [, fieldSessionId, takeId] = scoringCalibrationMatch;
    return {
      name: "scoringCalibration",
      path: `/capture/${fieldSessionId}/takes/${takeId}/scoring-calibration`,
      fieldSessionId,
      takeId,
      ...routeMeta.scoringCalibration,
    };
  }

  const multiviewSetupMatch = captureConsoleMatch
    ? captureConsoleMatch[1].match(/^takes\/(.+)\/analyze$/)
    : null;
  if (multiviewSetupMatch) {
    const [, captureTakeId] = multiviewSetupMatch;
    return {
      name: "multiview-setup",
      path: `/capture/takes/${captureTakeId}/analyze`,
      captureTakeId,
      ...routeMeta["multiview-setup"],
    };
  }

  const recordingAnalyzeMatch = captureConsoleMatch
    ? captureConsoleMatch[1].match(/^(.+)\/analyze$/)
    : null;
  if (recordingAnalyzeMatch) {
    const [, sessionId] = recordingAnalyzeMatch;
    return { name: "recording-analyze", path: `/capture/${sessionId}/analyze`, sessionId, ...routeMeta["recording-analyze"] };
  }

  if (captureConsoleMatch) {
    const [, sessionId] = captureConsoleMatch;
    return { name: "captureConsole", path: `/capture/${sessionId}`, sessionId, ...routeMeta.captureConsole };
  }

  const recordingMatch = pathname.match(/^\/recording\/(.+)$/);
  if (recordingMatch) {
    const [, sessionId] = recordingMatch;
    return { name: "recordingWorkspace", path: `/recording/${sessionId}`, sessionId, ...routeMeta.recordingWorkspace };
  }

  if (pathname === "/analysis/new" || pathname === "/upload") {
    return { name: "new-analysis", path: "/analysis/new", ...routeMeta["new-analysis"] };
  }

  if (pathname === "/analysis/tasks") {
    return { name: "analysis-tasks", path: "/analysis/tasks", ...routeMeta["analysis-tasks"] };
  }

  const analysisDetailsMatch = pathname.match(/^\/analysis\/([^/]+)\/details$/);

  if (analysisDetailsMatch) {
    const [, jobId] = analysisDetailsMatch;
    return { name: "analysis-details", path: `/analysis/${jobId}/details`, jobId, ...routeMeta["analysis-details"] };
  }

  const analysisTrajectoryMatch = pathname.match(/^\/analysis\/([^/]+)\/trajectory$/);

  if (analysisTrajectoryMatch) {
    const [, jobId] = analysisTrajectoryMatch;
    return {
      name: "ball-trajectory",
      path: `/analysis/${jobId}/trajectory`,
      jobId,
      ...routeMeta["ball-trajectory"],
    };
  }

  const multiviewObservabilityMatch = pathname.match(/^\/analysis\/([^/]+)\/multiview$/);
  if (multiviewObservabilityMatch) {
    const [, jobId] = multiviewObservabilityMatch;
    return {
      name: "multiview-observability",
      path: `/analysis/${jobId}/multiview`,
      jobId,
      ...routeMeta["multiview-observability"],
    };
  }

  const analysisReportMatch = pathname.match(/^\/analysis\/([^/]+)\/reports\/([^/]+)$/);

  if (analysisReportMatch) {
    const [, jobId, reportType] = analysisReportMatch;

    if (supportedReportTypes.includes(reportType as ReportType)) {
      return {
        name: "report",
        path: `/analysis/${jobId}/reports/${reportType as ReportType}`,
        reportType: reportType as ReportType,
        jobId,
        ...routeMeta.report,
      };
    }

    return { name: "analysis-details", path: `/analysis/${jobId}/details`, jobId, ...routeMeta["analysis-details"] };
  }

  const analysisVisionMatch = pathname.match(/^\/analysis\/([^/]+)\/vision$/);

  if (analysisVisionMatch) {
    const [, jobId] = analysisVisionMatch;
    return { name: "vision", path: `/analysis/${jobId}/vision`, jobId, ...routeMeta.vision };
  }

  const analysisJobMatch = pathname.match(/^\/analysis\/([^/]+)$/);

  if (analysisJobMatch) {
    const [, jobId] = analysisJobMatch;
    if (jobId === "tasks") {
      return { name: "analysis-tasks", path: "/analysis/tasks", ...routeMeta["analysis-tasks"] };
    }
    return { name: "analysis-job", path: `/analysis/${jobId}`, jobId, ...routeMeta["analysis-job"] };
  }

  if (pathname === "/camera") {
    return { name: "camera-hub", path: "/camera", ...routeMeta["camera-hub"] };
  }

  if (pathname === "/vision") {
    return { name: "vision", path: "/vision", ...routeMeta.vision };
  }

  if (pathname === "/training") {
    return { name: "training", path: "/training", ...routeMeta.training };
  }

  if (pathname === "/hardware") {
    return { name: "hardware", path: "/hardware", ...routeMeta.hardware };
  }

  if (pathname.startsWith("/reports/")) {
    const reportType = pathname.replace("/reports/", "") as ReportType;

    if (supportedReportTypes.includes(reportType)) {
      return { name: "report", path: `/reports/${reportType}`, reportType, ...routeMeta.report };
    }

    return { name: "report", path: "/reports/movement", reportType: "movement", ...routeMeta.report };
  }

  return { name: "landing", path: "/", ...routeMeta.landing };
}

export function parseLocation(pathname: string, search: string): RouteState {
  let route = parsePath(pathname);

  // P0 6：analysis 系列路由按 `return` 覆盖导航段——Library origin 高亮「比赛库」，
  // capture origin 高亮「现场采集」；非法 return 安全忽略。
  const searchParams = new URLSearchParams(search);
  const rawReturn = searchParams.get("return");
  if (rawReturn && ANALYSIS_NAV_ROUTES.has(route.name)) {
    const section =
      rawReturn.startsWith("/library/") ? "library"
      : rawReturn.startsWith("/capture/") ? "capture"
      : null;
    if (section && section !== route.navigationSection) {
      route = { ...route, navigationSection: section } as RouteState;
    }
  }

  if (route.name === "sync-calibration") {
    const params = new URLSearchParams(search);
    const rawReturnPath = params.get("return");
    const returnPath = rawReturnPath && rawReturnPath.startsWith("/") && !rawReturnPath.startsWith("//")
      ? rawReturnPath as NavigatePath
      : undefined;
    return {
      ...route,
      captureTakeId: params.get("take") ?? params.get("captureTakeId") ?? "",
      returnPath,
    };
  }

  if (route.name === "tasks" || route.name === "analysis-tasks") {
    const params = new URLSearchParams(search);
    if (!params.has("source") && !params.has("taskSource") && !params.has("session") && !params.has("taskSession") && !params.has("cam") && !params.has("taskCam")) {
      return route;
    }
    const context = parseTaskListContext(search);
    return {
      ...route,
      taskSource: context.source,
      taskSessionId: context.sessionId,
    };
  }

  if (route.name === "upload" && search) {
    const params = new URLSearchParams(search);
    return {
      ...route,
      videoId: params.get("videoId") ?? undefined,
      source: params.get("source") ?? undefined,
    };
  }

  // vision 证据 seek 契约（performance finding → 视频证据跳转）：
  // 解析 t 查询参数（毫秒）；非法值（非数字/负数）忽略，由 VisionPage 在 metadata
  // loaded 后执行 currentTime = t/1000 并 clamp 到 [0, duration]。
  if (route.name === "vision" && "jobId" in route && route.jobId && search) {
    const params = new URLSearchParams(search);
    const raw = params.get("t");
    if (raw !== null) {
      const parsed = Number(raw);
      if (Number.isFinite(parsed) && parsed >= 0) {
        return { ...route, seekToMs: Math.round(parsed) };
      }
    }
    return route;
  }

  if (route.name === "library-item") {
    const params = new URLSearchParams(search);
    const rawView = params.get("view");
    const validViews = ["overview", "video", "analysis", "trajectory", "report", "segments", "technical"];
    const view = rawView && validViews.includes(rawView) ? rawView : "overview";
    return { ...route, view };
  }

  return route;
}
