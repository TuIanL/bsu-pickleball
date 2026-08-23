export type ReportType = "movement" | "diagnosis" | "performance";

export type AppShellMode = "landing" | "standard" | "capture";

export type NavigationSection =
  | "capture"
  | "videos"
  | "analysis"
  | "reports"
  | "devices"
  | "settings"
  | "library";

export type TaskListSource = "upload" | "recorded" | "sync_recording";

export type TaskCameraSlot = "cam_1" | "cam_2";

export interface TaskListContext {
  source: TaskListSource;
  sessionId?: string;
  cameraSlot?: TaskCameraSlot;
}

/**
 * transient analysis flow 的导航来源（只读视图，由 `return` 参数推导，非独立可变状态）。
 * - `library`：从 LibraryItem 发起，return 指向 `/library/:kind/:sourceId`。
 * - `task-console`：无 Library return，回退到工程任务控制台语义。
 * - `capture`：从采集控制台发起，return 指向 `/capture/:session`。
 */
export type AnalysisFlowOrigin =
  | {
      kind: "library";
      itemKind: "upload" | "recording" | "sync_recording";
      sourceId: string;
      /** 完整 `/library/...` 返回路径 */
      returnPath: string;
    }
  | { kind: "task-console"; taskContext: TaskListContext }
  | { kind: "capture"; returnPath: string };

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
  | `/analysis/${string}/multiview`
  | `/analysis/${string}/reports/${ReportType}`
  | "/library"
  | `/library/${string}/${string}`
  | "/training"
  | "/hardware"
  | `/reports/${ReportType}`
  | `/recording/${string}`
  | `/capture/${string}/analyze`
  | `/capture/takes/${string}/analyze`
  | "/sync-calibration"
  | `/showcase/${string}`;

export type NavigatePath = AppPath | `${string}?${string}`;

export type RouteState =
  | { name: "landing"; path: "/"; shellMode: "landing"; navigationSection: null }
  | { name: "upload"; path: "/upload"; videoId?: string; source?: string; shellMode: "landing"; navigationSection: null }
  | { name: "workspace"; path: "/workspace"; shellMode: "standard"; navigationSection: "capture" }
  | { name: "captureHome"; path: "/capture"; shellMode: "standard"; navigationSection: "capture" }
  | { name: "captureNew"; path: "/capture/new"; shellMode: "standard"; navigationSection: "capture" }
  | { name: "captureConsole"; path: `/capture/${string}`; sessionId: string; shellMode: "capture"; navigationSection: "capture" }
  | { name: "segmentManager"; path: `/capture/${string}/takes/${string}/segments`; fieldSessionId: string; takeId: string; shellMode: "standard"; navigationSection: "capture" }
  | { name: "tasks"; path: "/tasks"; taskSource?: TaskListSource; taskSessionId?: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "new-analysis"; path: "/analysis/new"; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "analysis-tasks"; path: "/analysis/tasks"; taskSource?: TaskListSource; taskSessionId?: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "analysis-job"; path: `/analysis/${string}`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "analysis-details"; path: `/analysis/${string}/details`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "vision"; path: "/vision"; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "vision"; path: `/analysis/${string}/vision`; jobId: string; seekToMs?: number; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "ball-trajectory"; path: `/analysis/${string}/trajectory`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "multiview-observability"; path: `/analysis/${string}/multiview`; jobId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "report"; path: `/reports/${ReportType}`; reportType: ReportType; shellMode: "standard"; navigationSection: "reports" }
  | { name: "report"; path: `/analysis/${string}/reports/${ReportType}`; reportType: ReportType; jobId: string; shellMode: "standard"; navigationSection: "reports" }
  | { name: "camera-hub"; path: "/camera"; shellMode: "standard"; navigationSection: "devices" }
  | { name: "training"; path: "/training"; shellMode: "standard"; navigationSection: "settings" }
  | { name: "hardware"; path: "/hardware"; shellMode: "standard"; navigationSection: "settings" }
  | { name: "recordingWorkspace"; path: `/recording/${string}`; sessionId: string; shellMode: "standard"; navigationSection: "videos" }
  | { name: "recording-analyze"; path: `/capture/${string}/analyze`; sessionId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "multiview-setup"; path: `/capture/takes/${string}/analyze`; captureTakeId: string; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "sync-calibration"; path: "/sync-calibration"; captureTakeId: string; returnPath?: NavigatePath; shellMode: "standard"; navigationSection: "analysis" }
  | { name: "showcase"; path: `/showcase/${string}`; runtimeId: string; shellMode: "landing"; navigationSection: null }
  | { name: "library"; path: "/library"; shellMode: "standard"; navigationSection: "library" }
  | { name: "library-item"; path: `/library/${string}/${string}`; kind: "upload" | "recording" | "sync_recording"; sourceId: string; view: string; shellMode: "standard"; navigationSection: "library" };

export type NavigateFn = (path: NavigatePath, options?: NavigateOptions) => void;
