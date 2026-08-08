import type { AppShellMode, NavigationSection, ReportType, RouteState } from "./navigationTypes";

export const supportedReportTypes: ReportType[] = ["movement", "diagnosis"];

type RouteMeta = {
  shellMode: AppShellMode;
  navigationSection: NavigationSection | null;
};

const routeMeta = {
  landing: { shellMode: "landing", navigationSection: null },
  upload: { shellMode: "landing", navigationSection: null },
  workspace: { shellMode: "standard", navigationSection: "capture" },
  tasks: { shellMode: "standard", navigationSection: "analysis" },
  captureHome: { shellMode: "standard", navigationSection: "videos" },
  captureNew: { shellMode: "standard", navigationSection: "capture" },
  captureConsole: { shellMode: "capture", navigationSection: "capture" },
  segmentManager: { shellMode: "standard", navigationSection: "capture" },
  recordingWorkspace: { shellMode: "standard", navigationSection: "videos" },
  "new-analysis": { shellMode: "standard", navigationSection: "analysis" },
  "analysis-tasks": { shellMode: "standard", navigationSection: "analysis" },
  "recording-analyze": { shellMode: "standard", navigationSection: "analysis" },
  "multiview-setup": { shellMode: "standard", navigationSection: "analysis" },
  "analysis-job": { shellMode: "standard", navigationSection: "analysis" },
  "analysis-details": { shellMode: "standard", navigationSection: "analysis" },
  vision: { shellMode: "standard", navigationSection: "analysis" },
  "ball-trajectory": { shellMode: "standard", navigationSection: "analysis" },
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
    return { name: "workspace", path: "/workspace", ...routeMeta.workspace };
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

  const captureConsoleMatch = pathname.match(/^\/capture\/(.+)$/);

  const segmentManagerMatch = captureConsoleMatch
    ? captureConsoleMatch[1].match(/^(.+)\/takes\/(.+)\/segments$/)
    : null;
  if (segmentManagerMatch) {
    const [, fieldSessionId, takeId] = segmentManagerMatch;
    return { name: "segmentManager", path: `/capture/${fieldSessionId}/takes/${takeId}/segments`, fieldSessionId, takeId, ...routeMeta.segmentManager };
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
  const route = parsePath(pathname);

  if (route.name === "upload" && search) {
    const params = new URLSearchParams(search);
    return {
      ...route,
      videoId: params.get("videoId") ?? undefined,
      source: params.get("source") ?? undefined,
    };
  }

  return route;
}
