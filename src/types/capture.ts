/** 统一前端录制类型 —— CaptureRuntime State、Session、Intent、Result */

export type CaptureMode = "single" | "dual";

export type CaptureTrackRuntime = {
  trackId?: string;
  slot: "single" | "cam_1" | "cam_2";
  cameraId: string;
  analysisRole: "default" | "supplementary" | "disabled";
};

export type UnifiedCaptureSession = {
  sourceType: "recording" | "sync_recording";
  sourceSessionId: string;
  captureTakeId: string;
  mode: CaptureMode;
  startedAt: string;
  fps: number;
  status: "starting" | "recording" | "stopping" | "completed" | "partial" | "failed" | "canceled";
  tracks: CaptureTrackRuntime[];
  cameraDisplayNames: Record<string, string>;
  autoAnalysisJobId?: string;
};

export type CaptureStartIntent =
  | { mode: "single"; cameraId: string; fps: number; autoAnalyze: boolean }
  | { mode: "dual"; slots: { cam_1: string; cam_2: string }; fps: number; autoAnalyze: boolean };

export type NormalizedTrackStopResult = {
  trackId: string;
  slot: string;
  cameraId: string;
  analysisRole: string;
  status: string;
  videoId?: string;
  durationMs?: number;
  fragmentCount: number;
  restartCount: number;
};

export type NormalizedCaptureStopResult = {
  captureTakeId: string;
  fieldSessionId: string;
  status: string;
  tracks: NormalizedTrackStopResult[];
  analysisAvailable: boolean;
  defaultAnalysisTrackId?: string;
  defaultAnalysisVideoId?: string;
  analysisBlockedReason?: string;
  warnings: string[];
};

export type CaptureRuntimeState =
  | { phase: "idle" }
  | { phase: "starting"; intent: CaptureStartIntent }
  | { phase: "recording"; session: UnifiedCaptureSession }
  | { phase: "stopping"; session: UnifiedCaptureSession; operationError?: string }
  | { phase: "recovering"; session: UnifiedCaptureSession; operationError: string }
  | { phase: "completed"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }
  | { phase: "partial"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }
  | { phase: "failed"; session: UnifiedCaptureSession | null; result: NormalizedCaptureStopResult | null; error: string }
  | { phase: "canceled"; session: UnifiedCaptureSession };
