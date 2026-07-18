export type MetricValue<T> =
  | { state: "ready"; value: T; label: string }
  | { state: "loading" }
  | { state: "unsupported" }
  | { state: "error"; message?: string };

export interface CameraPreviewViewModel {
  slot: string;
  cameraId: string;
  label: string;
  previewUrl: string;
  resolution?: string;
  fps?: number;
  status: "idle" | "connecting" | "ready" | "failed";
}

export interface RecordingControlViewModel {
  phase: string;
  elapsedMs: number;
  fileSize: MetricValue<number>;
  fps: MetricValue<number>;
  bitrate: MetricValue<number>;
}

export interface CaptureHealthViewModel {
  encoding: MetricValue<"ok" | "error">;
  storage: MetricValue<{ used: number; total: number }>;
  network: MetricValue<"connected" | "disconnected">;
  sync: MetricValue<"synced" | "pending" | "failed">;
}

export interface CaptureHeaderViewModel {
  title: string;
  statusLabel: string;
  storageSpace: string;
  isRecording: boolean;
}

export interface CompletionViewModel {
  phase: string;
  sessionDir?: string;
  tracks: { slot: string; status: string; durationMs?: number; fragmentCount: number }[];
  analysisAvailable: boolean;
  analysisVideoId?: string;
  analysisBlockedReason?: string;
  warnings: string[];
  outboxPending: boolean;
}

export interface QuickAction {
  id: string;
  label: string;
  icon: string;
  action: () => void;
  disabled?: boolean;
}

export interface TimelineMarker {
  id: string;
  timestampMs: number;
  track: "highlight" | "side_change" | "timeout";
  label?: string;
  pending?: boolean;
  failed?: boolean;
}
