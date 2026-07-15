export type ReportType = "movement" | "diagnosis";

export type AppPath =
  | "/"
  | "/upload"
  | "/capture"
  | "/capture/new"
  | `/capture/${string}`
  | "/tasks"
  | "/vision"
  | "/analysis/new"
  | "/analysis/tasks"
  | "/camera"
  | `/analysis/${string}`
  | `/analysis/${string}/details`
  | `/analysis/${string}/vision`
  | `/analysis/${string}/reports/${ReportType}`
  | "/training"
  | "/hardware"
  | `/reports/${ReportType}`
  | `/recording/${string}`;

export type RouteState =
  | { name: "landing"; path: "/" }
  | { name: "upload"; path: "/upload"; videoId?: string; source?: string }
  | { name: "captureHome"; path: "/capture" }
  | { name: "captureNew"; path: "/capture/new" }
  | { name: "captureConsole"; path: `/capture/${string}`; sessionId: string }
  | { name: "segmentManager"; path: `/capture/${string}/takes/${string}/segments`; fieldSessionId: string; takeId: string }
  | { name: "tasks"; path: "/tasks" }
  | { name: "new-analysis"; path: "/analysis/new" }
  | { name: "analysis-tasks"; path: "/analysis/tasks" }
  | { name: "analysis-job"; path: `/analysis/${string}`; jobId: string }
  | { name: "analysis-details"; path: `/analysis/${string}/details`; jobId: string }
  | { name: "vision"; path: "/vision" }
  | { name: "vision"; path: `/analysis/${string}/vision`; jobId: string }
  | { name: "report"; path: `/reports/${ReportType}`; reportType: ReportType }
  | { name: "report"; path: `/analysis/${string}/reports/${ReportType}`; reportType: ReportType; jobId: string }
  | { name: "camera-hub"; path: "/camera" }
  | { name: "training"; path: "/training" }
  | { name: "hardware"; path: "/hardware" }
  | { name: "recordingWorkspace"; path: `/recording/${string}`; sessionId: string };

export type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;
