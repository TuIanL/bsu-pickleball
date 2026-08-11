export type ReportType = "movement" | "diagnosis";

export type AppShellMode = "landing" | "standard" | "capture";

export type NavigationSection =
  | "capture"
  | "videos"
  | "analysis"
  | "reports"
  | "devices"
  | "settings";

export type TaskListSource = "upload" | "recorded" | "sync_recording";

export type TaskCameraSlot = "cam_1" | "cam_2";

export interface TaskListContext {
  source: TaskListSource;
  sessionId?: string;
  cameraSlot?: TaskCameraSlot;
}

export interface NavigateOptions {
  replace?: boolean;
}

export type AppPath =
  | "/"
  | "/upload"
  | "/workspace"
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
  | `/analysis/${string}/trajectory`
  | `/analysis/${string}/reports/${ReportType}`
  | "/training"
  | "/hardware"
  | `/reports/${ReportType}`
  | `/recording/${string}`
  | `/capture/${string}/analyze`
  | `/capture/takes/${string}/analyze`
  | `/showcase/${string}`;

export type NavigatePath = AppPath | `${string}?${string}`;

export type RouteState =
  | { name: "landing"; path: "/"; shellMode: "landing"; navigationSection: null }
  | { name: "upload"; path: "/upload"; videoId?: string; source?: string; shellMode: "landing"; navigationSection: null }
  | { name: "workspace"; path: "/workspace"; shellMode: "standard"; navigationSection: "capture" }
  | { name: "captureHome"; path: "/capture"; shellMode: "standard"; navigationSection: "videos" }
  | { name: "captureNew"; path: "/capture/new"; shellMode: "standard"; navigationSection: "capture" }
  | { name: "captureConsole"; path: `/capture/${string}`; sessionId: string; shellMode: "capture"; navigationSection: "capture" }
  | { name: "segmentManager"; path: `/capture/${string}/takes/${string}/segments`; fieldSessionId: string; takeId: string; shellMode: "standard"; navigationSection: "capture" }
  | { name: "tasks"; path: "/tasks"; taskSource?: TaskListSource; taskSessionId?: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "new-analysis"; path: "/analysis/new"; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "analysis-tasks"; path: "/analysis/tasks"; taskSource?: TaskListSource; taskSessionId?: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "analysis-job"; path: `/analysis/${string}`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "analysis-details"; path: `/analysis/${string}/details`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "vision"; path: "/vision"; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "vision"; path: `/analysis/${string}/vision`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "ball-trajectory"; path: `/analysis/${string}/trajectory`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "report"; path: `/reports/${ReportType}`; reportType: ReportType; shellMode: "standard"; navigationSection: "reports" }
  | { name: "report"; path: `/analysis/${string}/reports/${ReportType}`; reportType: ReportType; jobId: string; shellMode: "standard"; navigationSection: "reports" }
  | { name: "camera-hub"; path: "/camera"; shellMode: "standard"; navigationSection: "devices" }
  | { name: "training"; path: "/training"; shellMode: "standard"; navigationSection: "settings" }
  | { name: "hardware"; path: "/hardware"; shellMode: "standard"; navigationSection: "settings" }
  | { name: "recordingWorkspace"; path: `/recording/${string}`; sessionId: string; shellMode: "standard"; navigationSection: "videos" }
  | { name: "recording-analyze"; path: `/capture/${string}/analyze`; sessionId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "multiview-setup"; path: `/capture/takes/${string}/analyze`; captureTakeId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "showcase"; path: `/showcase/${string}`; runtimeId: string; shellMode: "landing"; navigationSection: null };

export type NavigateFn = (path: NavigatePath, options?: NavigateOptions) => void;
