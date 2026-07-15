import type { ReportType, RouteState } from "./navigationTypes";

export const supportedReportTypes: ReportType[] = ["movement", "diagnosis"];

export function parsePath(pathname: string): RouteState {
  if (pathname === "/" || pathname === "") {
    return { name: "landing", path: "/" };
  }

  if (pathname === "/upload") {
    return { name: "upload", path: "/upload" };
  }

  if (pathname.startsWith("/upload?")) {
    const params = new URLSearchParams(pathname.slice("/upload?".length));
    return { name: "upload", path: "/upload", videoId: params.get("videoId") ?? undefined, source: params.get("source") ?? undefined };
  }

  if (pathname === "/tasks") {
    return { name: "tasks", path: "/tasks" };
  }

  if (pathname === "/capture/new") {
    return { name: "captureNew", path: "/capture/new" };
  }

  if (pathname === "/capture") {
    return { name: "captureHome", path: "/capture" };
  }

  const captureConsoleMatch = pathname.match(/^\/capture\/(.+)$/);

  const segmentManagerMatch = captureConsoleMatch
    ? captureConsoleMatch[1].match(/^(.+)\/takes\/(.+)\/segments$/)
    : null;
  if (segmentManagerMatch) {
    const [, fieldSessionId, takeId] = segmentManagerMatch;
    return { name: "segmentManager", path: `/capture/${fieldSessionId}/takes/${takeId}/segments`, fieldSessionId, takeId };
  }

  if (captureConsoleMatch) {
    const [, sessionId] = captureConsoleMatch;
    return { name: "captureConsole", path: `/capture/${sessionId}`, sessionId };
  }

  const recordingMatch = pathname.match(/^\/recording\/(.+)$/);
  if (recordingMatch) {
    const [, sessionId] = recordingMatch;
    return { name: "recordingWorkspace", path: `/recording/${sessionId}`, sessionId };
  }

  if (pathname === "/analysis/new" || pathname === "/upload") {
    return { name: "new-analysis", path: "/analysis/new" };
  }

  if (pathname === "/analysis/tasks") {
    return { name: "analysis-tasks", path: "/analysis/tasks" };
  }

  const analysisDetailsMatch = pathname.match(/^\/analysis\/([^/]+)\/details$/);

  if (analysisDetailsMatch) {
    const [, jobId] = analysisDetailsMatch;
    return { name: "analysis-details", path: `/analysis/${jobId}/details`, jobId };
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
      };
    }

    return { name: "analysis-details", path: `/analysis/${jobId}/details`, jobId };
  }

  const analysisVisionMatch = pathname.match(/^\/analysis\/([^/]+)\/vision$/);

  if (analysisVisionMatch) {
    const [, jobId] = analysisVisionMatch;
    return { name: "vision", path: `/analysis/${jobId}/vision`, jobId };
  }

  const analysisJobMatch = pathname.match(/^\/analysis\/([^/]+)$/);

  if (analysisJobMatch) {
    const [, jobId] = analysisJobMatch;
    if (jobId === "tasks") {
      return { name: "analysis-tasks", path: "/analysis/tasks" };
    }
    return { name: "analysis-job", path: `/analysis/${jobId}`, jobId };
  }

  if (pathname === "/camera") {
    return { name: "camera-hub", path: "/camera" };
  }

  if (pathname === "/vision") {
    return { name: "vision", path: "/vision" };
  }

  if (pathname === "/training") {
    return { name: "training", path: "/training" };
  }

  if (pathname === "/hardware") {
    return { name: "hardware", path: "/hardware" };
  }

  if (pathname.startsWith("/reports/")) {
    const reportType = pathname.replace("/reports/", "") as ReportType;

    if (supportedReportTypes.includes(reportType)) {
      return { name: "report", path: `/reports/${reportType}`, reportType };
    }

    return { name: "report", path: "/reports/movement", reportType: "movement" };
  }

  return { name: "landing", path: "/" };
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
