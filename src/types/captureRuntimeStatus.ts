/**
 * CaptureTake 运行状态响应类型 —— 与后端 `/api/capture-takes/{id}/runtime-status` 对齐。
 *
 * 设计依据：openspec/changes/redesign-live-recording-workspace-runtime-status
 * 五个区域：storage / recording / tracks / sync / updated_at
 * 每个指标独立表达 ready/collecting/unavailable/error 可用性状态。
 */

/** 指标可用性状态：与后端 MetricAvailability 一致 */
export type RuntimeMetricAvailability = "ready" | "collecting" | "unavailable" | "error";

/** 通用指标值：每个指标独立表达可用性，避免单项失败掩盖整体。 */
export interface RuntimeMetricValue<T = number> {
  state: RuntimeMetricAvailability;
  value?: T | null;
  message?: string | null;
}

/** 存储容量快照，基于会话目录所在文件系统。 */
export interface StorageCapacity {
  state: RuntimeMetricAvailability;
  totalBytes?: number | null;
  usedBytes?: number | null;
  freeBytes?: number | null;
  message?: string | null;
}

/** 录制会话总体运行指标。target_* 是配置值，非实测；实测指标用 RuntimeMetricValue。 */
export interface RecordingMetrics {
  phase: string;
  startedAt?: string | null;
  elapsedMs?: number | null;
  durationMs?: number | null;
  targetFps?: number | null;
  targetWidth?: number | null;
  targetHeight?: number | null;
  fileSizeBytes: RuntimeMetricValue<number>;
  effectiveFps: RuntimeMetricValue<number>;
  avgBitrateBps: RuntimeMetricValue<number>;
}

/** 单轨运行状态。 */
export interface TrackRuntimeStatus {
  trackId: string;
  slot: "cam_1" | "cam_2";
  cameraId: string;
  phase: string;
  fileSizeBytes: RuntimeMetricValue<number>;
  effectiveFps: RuntimeMetricValue<number>;
  error?: string | null;
}

/** 双路同步与事件编码同步状态摘要（单摄时为 null）。 */
export interface SyncRuntimeStatus {
  dualSync: RuntimeMetricAvailability;
  dualSyncQuality?: "good" | "degraded" | "unknown" | null;
  eventSync: RuntimeMetricAvailability;
  message?: string | null;
}

/** CaptureTake 运行状态响应。 */
export interface CaptureTakeRuntimeStatus {
  captureTakeId: string;
  captureMode: "single" | "dual";
  storage: StorageCapacity;
  recording: RecordingMetrics;
  tracks: TrackRuntimeStatus[];
  sync?: SyncRuntimeStatus | null;
  updatedAt: string;
}

/** 运行状态轮询请求结果：首次请求 loading，失败时 error + 最后快照。 */
export interface CaptureRuntimeStatusState {
  /** 当前快照；首次请求未返回时为 null */
  snapshot: CaptureTakeRuntimeStatus | null;
  /** 首次请求尚未返回 */
  isLoading: boolean;
  /** 最近一次请求失败的可读错误；成功后清空 */
  error: string | null;
  /** 最后一次成功快照的时间戳（用于展示"状态更新失败，最后更新于..."） */
  lastSuccessAt: string | null;
}
