/** 统一前端录制类型 —— CaptureRuntime State、Session、Intent、Result */

/** 录制模式：单摄 / 双摄 */
export type CaptureMode = "single" | "dual";

/** 每条视频轨道的运行时配置 */
export type CaptureTrackRuntime = {
  trackId?: string;                                              // 轨道 ID
  slot: "single" | "cam_1" | "cam_2";                           // 轨道槽位
  cameraId: string;                                              // 关联摄像头 ID
  analysisRole: "default" | "supplementary" | "disabled";        // 分析角色
};

/** 统一的前端录制会话（融合单摄 / 双摄） */
export type UnifiedCaptureSession = {
  sourceType: "recording" | "sync_recording";  // 后端会话类型
  sourceSessionId: string;                      // 后端会话 ID
  captureTakeId: string;                        // 关联的 CaptureTake ID
  mode: CaptureMode;                            // 单摄 / 双摄
  startedAt: string;                            // 开始时间
  fps: number;
  status: "starting" | "recording" | "stopping" | "completed" | "partial" | "failed" | "canceled";
  tracks: CaptureTrackRuntime[];                // 轨道列表
  cameraDisplayNames: Record<string, string>;   // 摄像头显示名称映射
  autoAnalysisJobId?: string;                   // 自动分析任务 ID
  storageRoot?: string;                         // 存储根目录
  sessionDir?: string;                          // 会话目录
  storageStatus?: string;                       // 存储状态
  displayMode?: "standard" | "showcase";
  showcaseRuntimeId?: string;
};

/** 录制启动意图：单摄一键启动，双摄指定双摄像头 */
export type CaptureStartIntent =
  | { mode: "single"; cameraId: string; fps: number; autoAnalyze: boolean; storageRoot?: string }
  | { mode: "dual"; slots: { cam_1: string; cam_2: string }; fps: number; autoAnalyze: boolean; storageRoot?: string };

/** 归一化的单条轨道停止结果 */
export type NormalizedTrackStopResult = {
  trackId: string;          // 轨道 ID
  slot: string;             // 槽位
  cameraId: string;         // 摄像头 ID
  analysisRole: string;     // 分析角色
  status: string;           // 状态
  videoId?: string;         // 视频 ID
  durationMs?: number;      // 时长（毫秒）
  fragmentCount: number;    // 片段数
  restartCount: number;     // 重启次数
};

/** 归一化的整体录制停止结果 */
export type NormalizedCaptureStopResult = {
  captureTakeId: string;                    // CaptureTake ID
  fieldSessionId: string;                   // 场次 ID
  status: string;                           // 总体状态
  tracks: NormalizedTrackStopResult[];      // 各轨道结果
  analysisAvailable: boolean;               // 分析是否可用
  defaultAnalysisTrackId?: string;          // 默认分析轨道
  defaultAnalysisVideoId?: string;          // 默认分析视频
  analysisBlockedReason?: string;           // 分析不可用原因
  warnings: string[];                       // 警告列表
};

/** 录制运行时状态机 */
export type CaptureRuntimeState =
  | { phase: "idle" }                                                                  // 空闲
  | { phase: "hydrating" }                                                             // 恢复中
  | { phase: "hydration_failed"; error: string }                                       // 恢复失败
  | { phase: "starting"; intent: CaptureStartIntent }                                  // 启动中
  | { phase: "recording"; session: UnifiedCaptureSession }                             // 录制中
  | { phase: "stopping"; session: UnifiedCaptureSession; operationError?: string }     // 停止中
  | { phase: "recovering"; session: UnifiedCaptureSession; operationError: string }    // 恢复中
  | { phase: "completed"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }   // 完成
  | { phase: "partial"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }      // 部分完成
  | { phase: "failed"; session: UnifiedCaptureSession | null; result: NormalizedCaptureStopResult | null; error: string }  // 失败
  | { phase: "canceled"; session: UnifiedCaptureSession };                             // 已取消
