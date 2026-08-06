// ── 通用基础类型 ──

/** 趋势方向 */
export type TrendDirection = "up" | "down" | "steady";

/** 球场模式 */
export type CourtMode = "movement";

/** 报告类型 */
export type ReportType = "movement" | "diagnosis";

/** 分析任务状态 */
export type AnalysisJobStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "failed"
  | "completed"
  | "canceled";

/** 规范化分析状态 */
export type AnalysisCanonicalStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "canceled";

/** 分析阶段 ID */
export type AnalysisStageId =
  | "upload"
  | "queue"
  | "calibration"
  | "video-read"
  | "frame-sampling"
  | "detection"
  | "pose"
  | "tracking"
  | "projection"
  | "metrics"
  | "visualization"
  | "report"
  | string;

/** 摄像头角度 */
export type CameraAngle =
  | "baseline"
  | "sideline"
  | "elevated"
  | "unknown";

/** 比赛形式 */
export type MatchFormat = "singles" | "doubles";

/**
 * 应用路由路径。
 * 单一权威定义位于 `src/app/navigationTypes.ts`；此处仅再导出以保持遗留导入兼容，
 * 不得在此独立重复定义 `AppPath`，否则会与导航类型契约漂移。
 */
import type { AppPath, NavigateFn, RouteState } from "../app/navigationTypes";
export type { AppPath, NavigateFn, RouteState };

/** 洞察语气 */
export type InsightTone = "advantage" | "risk" | "error" | "training";

export type ShotType =
  | "发球"
  | "接发"
  | "第三拍"
  | "轻吊"
  | "抽击"
  | "重置"
  | "截击"
  | "扣杀"
  | "失误";

export type ShotResult =
  | "制胜分"
  | "受迫失误"
  | "非受迫失误"
  | "中性"
  | "建立优势";

// ── 报告/分析基础结构 ──

/** 质量等级 */
export type QualityBand = "high" | "medium" | "low";

/** 单项指标 */
export interface Metric {
  id: string;
  label: string;
  value: string;
  detail: string;
  trend: string;
  direction: TrendDirection;
}

/** 球场落点 */
export interface CourtPoint {
  id: string;
  x: number;           // X 坐标
  y: number;           // Y 坐标
  intensity: number;   // 密度强度
  label: string;
}

/** 球场路线 */
export interface CourtRoute {
  id: string;
  from: CourtPoint;  // 起点
  to: CourtPoint;    // 终点
  label: string;
  result: "得分" | "受迫回球" | "失误" | "相持";
}

/** 移动点 */
export interface MovementPoint {
  x: number;
  y: number;
}

/** 回合 */
export interface Rally {
  id: string;
  title: string;
  duration: string;
  shots: number;          // 拍数
  pattern: string;        // 模式
  result: string;         // 结果
  observation: string;    // 观察说明
}

/** 报告会话 */
export interface ReportSession {
  athlete: string;
  venue: string;
  date: string;
  level: string;
  reportId: string;
  summary: string;
  metrics: Metric[];
  landingPoints: CourtPoint[];   // 落点
  routes: CourtRoute[];          // 路线
  movementPath: MovementPoint[]; // 移动轨迹
  rallies: Rally[];
}

export interface Diagnosis {
  id: string;
  issue: string;
  severity: "高" | "中" | "低";
  evidence: string;
  suggestion: string;
  expectedOutcome: string;
  priority: string;
}

export interface TrainingRecommendation {
  id: string;
  issueId: string;
  title: string;
  learningContent: string;
  practiceTask: string;
  nextTarget: string;
  progress: {
    previous: number;
    current: number;
    target: number;
    unit: string;
  };
}

export interface HardwareMetric {
  id: string;
  label: string;
  value: string;
  detail: string;
}

export interface SweetZoneCell {
  id: string;
  row: number;
  col: number;
  intensity: number;
}

export interface HardwarePreview {
  phaseLabel: string;
  disclaimer: string;
  metrics: HardwareMetric[];
  sweetZone: SweetZoneCell[];
  highlightedCellId: string;
  fusionPoints: Array<{
    visual: string;
    sensor: string;
    insight: string;
  }>;
}

export interface CameraInfo {
  camera_id: string;
  name: string;
  stream_url: string;
  protocol: "rtsp" | "rtmp" | "http";
  username?: string;
  password?: string;
  created_at: string;
}

export interface CameraCreateRequest {
  camera_id: string;
  name: string;
  stream_url: string;
  protocol: "rtsp" | "rtmp" | "http";
  username?: string;
  password?: string;
}

export interface CameraUpdateRequest {
  camera_id: string;
  name: string;
}

export interface ProbeResult {
  camera_id: string;
  online: boolean;
  latency_ms?: number;
  resolution?: string;
  detected_at: string;
  error_message?: string;
}

// ── 单摄录制相关 ──

/** 单摄录制会话状态 */
export type RecordingSessionStatus = "recording" | "completed" | "failed" | "canceled";

/** 单摄录制启动请求 */
export interface RecordingStartRequest {
  camera_id: string;
  field_session_id?: string;
  court_name?: string;
  match_format?: "singles" | "doubles";
  camera_angle?: string;
  fps?: number;
  resolution?: string;
  auto_analyze_after_stop?: boolean;
  storage_root?: string;
}

/** 单摄录制会话 */
export interface RecordingSession {
  session_id: string;
  camera_id: string;
  field_session_id?: string;
  court_name: string;
  match_format: string;
  camera_angle: string;
  fps: number;
  resolution: string;
  auto_analyze_after_stop: boolean;
  status: RecordingSessionStatus;
  started_at: string;
  stopped_at?: string;
  duration_sec?: number;
  video_path?: string;
  video_id?: string;
  auto_analysis_job_id?: string;
  error_message?: string;
  capture_take_id?: string;
  storage_root?: string;
  session_dir?: string;
  storage_status?: string;
}

// ── 双摄同步录制相关 ──

/** 双摄同步录制状态 */
export type SyncRecordingStatus = "recording" | "completed" | "failed" | "canceled";
export type SyncMergeStatus = "pending" | "running" | "completed" | "failed";

/** 同步片段状态 */
export type SyncSegmentStatus = "recording" | "completed" | "failed";

/** 摄像头槽位角色 */
export type CameraSlotRole = "cam_1" | "cam_2";

/** 摄像头槽位配置 */
export interface CameraSlotConfig {
  role: CameraSlotRole;
  camera_id: string;
  camera_angle: string;
  stream_url_snapshot: string;
}

export interface SyncSegmentFile {
  camera_id: string;
  role: CameraSlotRole;
  file_path: string;
  file_size: number;
  started_at?: string;
  ended_at?: string;
  error_message?: string;
}

export interface SyncSegment {
  segment_index: number;
  status: SyncSegmentStatus;
  files: SyncSegmentFile[];
  started_at?: string;
  ended_at?: string;
  restart_count: number;
  error_message?: string;
}

export interface SyncStartRequest {
  cam_1_id: string;
  cam_2_id: string;
  field_session_id?: string;
  court_name?: string;
  match_format?: "singles" | "doubles";
  cam_1_angle?: string;
  cam_2_angle?: string;
  fps?: number;
  resolution?: string;
  auto_analyze_after_stop?: boolean;
  storage_root?: string;
}

export interface SyncTestRequest {
  cam_1_id: string;
  cam_2_id: string;
  duration: number;
}

export interface SyncTestResult {
  success: boolean;
  cam_1_id: string;
  cam_2_id: string;
  duration_sec: number;
  cam_1_online: boolean;
  cam_2_online: boolean;
  cam_1_first_frame_url?: string | null;
  cam_2_first_frame_url?: string | null;
  cam_1_first_frame_exists: boolean;
  cam_2_first_frame_exists: boolean;
  cam_1_file_size: number;
  cam_2_file_size: number;
  cam_1_error?: string;
  cam_2_error?: string;
  test_completed_at?: string;
}

/** 双摄同步录制会话（后端格式） */
export interface SyncRecordingSession {
  session_id: string;
  field_session_id?: string;
  status: SyncRecordingStatus;
  camera_slots: Record<string, CameraSlotConfig>;  // 摄像头槽位配置
  segments: SyncSegment[];                          // 片段列表
  output_dir: string;                               // 输出目录
  default_analysis_video_id?: string;
  registered_video_ids?: Partial<Record<CameraSlotRole, string>>;
  associated_video_paths: string[];
  court_name: string;
  match_format: string;
  fps: number;
  resolution: string;
  auto_analyze_after_stop: boolean;
  started_at?: string;
  stopped_at?: string;
  duration_sec?: number;
  error_message?: string;
  total_restarts: number;                           // 总重启次数
  capture_take_id?: string;
  storage_root?: string;
  session_dir?: string;
  storage_status?: string;
  merge_status?: SyncMergeStatus;
  merge_error?: string;
  merge_started_at?: string;
  merge_completed_at?: string;
  merge_results?: Partial<Record<CameraSlotRole, {
    status: string;
    video_id?: string;
    output_path?: string;
    fragment_count?: number;
    error?: string | null;
  }>>;
}

export interface SyncStopResponse {
  session: SyncRecordingSession;
  default_analysis_video_id?: string;
  analysis_available: boolean;
  analysis_blocked_reason?: string;
}

/** CaptureTake 轨道停止结果（后端格式） */
export interface CaptureTrackStopResult {
  track_id: string;
  slot: string;
  camera_id: string;
  analysis_role: string;
  status: string;
  video_id?: string;
  duration_ms?: number;
  fragment_count: number;
  restart_count: number;
}

/** CaptureTake 停止结果（后端格式） */
export interface CaptureStopResult {
  capture_take?: {
    id: string;
    field_session_id: string;
    capture_mode: string;
    source_session_type: string;
    source_session_id: string;
    status: string;
    started_at: string;
    ended_at?: string;
    duration_ms?: number;
    revision: number;
  };
  tracks: CaptureTrackStopResult[];
  analysis_available: boolean;
  default_analysis_track_id?: string;
  default_analysis_video_id?: string;
  analysis_blocked_reason?: string;
  warnings: string[];
}

// ── 场次（FieldSession） ──

/** 采集场次 */
export interface FieldSession {
  id: string;
  title: string;
  venue: string;
  court_name: string;
  capture_mode: string;   // 采集模式
  match_format: string;
  camera_setup: string;   // 摄像头配置
  status: string;
  notes: string;
  started_at?: string;
  ended_at?: string;
  created_at: string;
  updated_at: string;
}

/** 创建场次请求 */
export interface FieldSessionCreate {
  title?: string;
  venue?: string;
  court_name?: string;
  capture_mode?: string;
  match_format?: string;
  camera_setup?: string;
  notes?: string;
}

/** 场次删除结果 */
export interface FieldSessionDeleteResult {
  id: string;
  status: "deleted" | "blocked" | "not_found";
  detail: string;
}

// —— Session Timeline Event 类型 ——

export type TimelineEventType =
  | "session_note"
  | "non_play_start"
  | "non_play_end"
  | "game_start"
  | "game_end"
  | "set_start"
  | "set_end"
  | "rally_start"
  | "rally_end"
  | "score_update"
  | "score_correction"
  | "side_change"
  | "timeout_start"
  | "timeout_end"
  | "drill_start"
  | "drill_end"
  | "custom_marker"
  | "add_note"
  | "score_correction";

export type TimelineEventSource = "manual" | "algorithm" | "corrected" | "vidat_import";
export type TimelineEventPayload = Record<string, unknown>;

export interface SessionTimelineEvent {
  id: string;
  field_session_id: string;
  recording_session_id?: string;
  capture_take_id?: string;
  is_undone?: boolean;
  timestamp_ms: number;
  occurred_at: string;
  event_type: TimelineEventType;
  source: TimelineEventSource;
  label: string;
  note: string;
  payload_json: TimelineEventPayload;
  annotation_package_id?: string;
  vidat_import_audit_id?: string;
  created_at: string;
  updated_at: string;
}

export interface TimelineEventCreate {
  recording_session_id?: string;
  capture_take_id?: string;
  timestamp_ms?: number;
  occurred_at?: string;
  event_type: TimelineEventType;
  source?: TimelineEventSource;
  label?: string;
  note?: string;
  payload_json?: TimelineEventPayload;
}

export interface TimelineEventUpdate {
  timestamp_ms?: number;
  event_type?: TimelineEventType;
  source?: TimelineEventSource;
  label?: string;
  note?: string;
  payload_json?: TimelineEventPayload;
}

export interface TimelineEventListParams {
  event_type?: TimelineEventType;
  source?: TimelineEventSource;
  recording_session_id?: string;
  capture_take_id?: string;
  from_ms?: number;
  to_ms?: number;
  include_undone?: boolean;
}

// ── CaptureTake & Coding Actions ──

/** 编码动作类型 */
export type CodingActionType =
  | "start_set" | "start_game" | "start_next_rally"
  | "end_rally" | "end_game" | "end_set"
  | "toggle_non_play" | "start_timeout" | "change_side" | "add_note" | "undo"
  | "rally_result_a" | "rally_result_b" | "rally_replay" | "correct_score";

/** 比赛阶段 */
export type MatchPhase = "idle" | "rally_active" | "intermission";
/** 间歇类型 */
export type IntermissionKind = "between_rallies" | "timeout" | "side_change";

/** 编码动作请求 */
export interface CodingActionRequest {
  action: CodingActionType;
  timestamp_ms?: number;
  client_occurred_at?: string;
  client_action_id: string;         // 客户端幂等 ID
  expected_revision: number;        // 期望修订号（冲突检测）
  payload?: Record<string, unknown>;
}

/** 实时编码状态（服务端返回） */
export interface LiveCodingState {
  revision: number;
  set_ordinal: number;              // 当前盘序号
  game_ordinal: number;             // 当前局序号
  rally_ordinal: number;            // 当前分序号
  non_play: boolean;                // 是否非比赛状态
  match_phase?: MatchPhase;
  intermission_kind?: IntermissionKind;
  current_set_segment_id?: string;  // 当前盘段 ID
  current_game_segment_id?: string; // 当前局段 ID
  current_rally_segment_id?: string;// 当前分段 ID
  server_team?: "A" | "B" | null;  // 当前发球方
  score_a: number;                  // A 方得分
  score_b: number;                  // B 方得分
  scoring_mode: string;             // 计分模式
  scoring_ruleset_version?: string; // 规则版本
  recent_results: Array<{ winner: string | null; validity: string }>;  // 最近 N 分
  games_won_a: number;
  games_won_b: number;
  scoring_phase: "rally" | "serve_only";
  serving_side?: "left" | "right" | null;
  match_status: "not_started" | "in_progress" | "completed";
  match_winner?: "A" | "B" | null;
}

/** 编码动作响应 */
export interface CodingActionResponse {
  revision: number;
  created_events: Record<string, unknown>[];
  updated_segments: Record<string, unknown>[];
  live_state: LiveCodingState;
  timeline_events?: SessionTimelineEvent[];
  segments?: CaptureSegmentSummary[];
  duplicate?: boolean;
}

export interface CaptureTakeSummary {
  id: string;
  field_session_id: string;
  capture_mode: string;
  source_session_type: string;
  source_session_id: string;
  status: string;
  started_at: string;
  ended_at?: string;
  duration_ms?: number;
  revision: number;
}

export interface CaptureSegmentSummary {
  id: string;
  capture_take_id?: string;
  segment_type: "set" | "game" | "rally" | "custom";
  ordinal: number;
  label: string;
  start_ms: number;
  end_ms?: number;
  corrected_start_ms?: number;
  corrected_end_ms?: number;
  effective_start_ms?: number;
  effective_end_ms?: number;
  edit_version: number;
  edit_status: "active" | "superseded" | "archived";
  status: "open" | "closed" | "inferred" | "corrected";
  source: string;
  is_highlight: boolean;
  parent_segment_id?: string;
}

// ── AnalysisBatch ──

export interface AnalysisBatchCreateResponse {
  batch_id: string;
  status: string;
  analysis_profile: string;
  items: AnalysisBatchItemSummary[];
}

export interface AnalysisBatchItemSummary {
  id: string;
  segment_id: string;
  segment_version: number;
  snapshot_start_ms: number;
  snapshot_end_ms: number;
  video_id: string;
  status: string;
  analysis_job_id?: string;
  error_message?: string;
}

export interface AnalysisBatchDetail {
  batch_id: string;
  status: string;
  analysis_profile: string;
  items: AnalysisBatchItemSummary[];
}

export interface NavigationItem {
  id: string;
  label: string;
  shortLabel: string;
  path: AppPath;
}

export interface AnalysisUploadMetadata {
  fileName: string;
  fileSize?: number;
  sourceFps?: number;
  matchTitle: string;
  venue: string;
  matchDate: string;
  matchFormat: MatchFormat;
  cameraAngle: CameraAngle;
  athleteLabel: string;
  level: string;
  camera_id?: string;
  recording_session_id?: string;
  capture_take_id?: string;
  session_dir?: string;
  camera_slot?: "cam_1" | "cam_2";
}

export interface AnalysisStage {
  id: AnalysisStageId;
  label: string;
  status: "pending" | "active" | "done" | "partial" | "failed" | "skipped" | "unavailable" | "canceled";
  detail: string;
  startedAt?: string;
  endedAt?: string;
  durationMs?: number;
  progress?: number;
  errorCode?: string;
  publicMessage?: string;
  internalMessage?: string;
  retryCount?: number;
  counters?: Record<string, unknown>;
}

export interface AnalysisJobSummary {
  id: string;
  status: AnalysisJobStatus;
  canonicalStatus?: AnalysisCanonicalStatus;
  displayStatus?: AnalysisJobStatus;
  stage: AnalysisStageId;
  progress: number;
  createdAt: string;
  updatedAt: string;
  queuedAt?: string;
  startedAt?: string;
  finishedAt?: string;
  cancelRequestedAt?: string;
  canceledAt?: string;
  workerId?: string;
  priority?: number;
  attempt?: number;
  inputSignature?: string;
  configSignature?: string;
  analysisVersion?: number;
  previousJobId?: string;
  frameStride?: number;
  metadata: AnalysisUploadMetadata;
  stages: AnalysisStage[];
  reportId?: string;
  errorMessage?: string;
  errorCode?: string;
  publicErrorMessage?: string;
  internalErrorMessage?: string;
  videoId?: string;
  calibrationId?: string;
  analysisMode?: "demo" | "real" | "limited";
  recordingSessionId?: string;
  cameraSlot?: "cam_1" | "cam_2";
  /** 任务实际使用的推理开关（YOLO 人体检测 / RTMPose 姿态识别），后端解析后固化 */
  enableModelInference?: boolean;
  enablePoseInference?: boolean;
}

export type AnalysisDeleteStatus = "deleted" | "blocked" | "not_found" | "failed";

export interface AnalysisDeleteResult {
  job_id: string;
  status: AnalysisDeleteStatus;
  detail: string;
}

export interface VideoMetadata {
  id: string;
  original_filename: string;
  content_type?: string;
  size_bytes: number;
  path: string;
  uploaded_at: string;
}

export interface VideoUploadResponse {
  video: VideoMetadata;
}

export interface CalibrationPoint {
  x: number;
  y: number;
}

export interface ManualCalibrationResponse {
  calibration_id: string;
  homography: number[][];
  inverse_homography: number[][];
  quality: {
    reprojection_error: number;
    status: "ok" | "warning";
  };
}

export type AutomaticCalibrationStatus = "available" | "accepted" | "rejected" | "unavailable" | "error";

export interface AutomaticCalibrationKeypoints {
  top_left: CalibrationPoint;
  top_right: CalibrationPoint;
  bottom_right: CalibrationPoint;
  bottom_left: CalibrationPoint;
}

export interface AutomaticCalibrationResponse {
  status: AutomaticCalibrationStatus;
  detail: string;
  suggestion_id?: string;
  selected_frame?: {
    video_id: string;
    frame_index: number;
    timestamp_seconds: number;
    width: number;
    height: number;
  };
  keypoints?: AutomaticCalibrationKeypoints;
  confidence?: number;
  quality?: {
    reprojection_error: number;
    status: "ok" | "warning";
  };
  mask: {
    model_configured: boolean;
    model_path?: string;
    confidence?: number;
    mask_area_ratio?: number;
    line_count: number;
    detail: string;
  };
  preview_image_url?: string;
  calibration_id?: string;
  reference?: ReferenceLineDiagnostics;
  confidence_breakdown?: ConfidenceBreakdown;
}

export interface ReferenceLineDiagnostics {
  reference_score: number;
  coverage: number;
  supported_lines: number;
  total_lines: number;
  tolerance_px: number;
  line_count_supported: number;
  passing_line_names: string[];
  rejection_reason?: string;
  summary: string;
}

export interface ConfidenceBreakdown {
  segmentation: number;
  geometry: number;
  reference: number;
  combined: number;
}

export interface PipelineStageResult {
  id: string;
  label: string;
  status: "pending" | "active" | "done" | "failed" | "skipped" | "unavailable" | "canceled";
  detail: string;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  progress?: number;
  error_code?: string;
  public_message?: string;
  internal_message?: string;
  retry_count?: number;
  counters?: Record<string, unknown>;
}

export interface PipelineTrackPoint {
  frame_index: number;
  timestamp_seconds: number;
  track_id: string;
  image_point: CalibrationPoint;
  confidence: number;
  side: "near" | "far" | "unknown";
  court_point: CalibrationPoint;
}

export interface FrameSourceSize {
  width: number;
  height: number;
}

export interface DetectionOverlayBox {
  frame_index: number;
  timestamp_seconds: number;
  bbox: [number, number, number, number] | number[];
  confidence: number;
  class_name: "person";
  track_id?: string;
  /** canonical 球员身份（Player_1..Player_4）；未关联时为空。原始 track_id 不作为展示身份。 */
  player_id?: string;
  /** 后端生成的 canonical 展示标签；前端在相同 track 的身份恢复时可补全。 */
  label?: string;
  source_width: number;
  source_height: number;
}

export interface DetectionOverlayFrame {
  frame_index: number;
  timestamp_seconds: number;
  detections: DetectionOverlayBox[];
}

export interface TrackingOverlayArtifact {
  job_id: string;
  video_id?: string;
  status: "available" | "no_detections" | "unavailable";
  detail: string;
  source: FrameSourceSize;
  fps: number;
  frame_count: number;
  processed_frame_count: number;
  frame_stride: number;
  frames: DetectionOverlayFrame[];
}

export interface PoseKeypoint {
  name: string;
  x: number;
  y: number;
  confidence: number;
  visible: boolean;
}

export interface SkeletonEdge {
  from_keypoint: string;
  to_keypoint: string;
}

export interface PoseSubject {
  track_id: string;
  bbox: [number, number, number, number] | number[];
  confidence: number;
  keypoints: PoseKeypoint[];
}

export interface PoseOverlayFrame {
  frame_index: number;
  timestamp_seconds: number;
  subjects: PoseSubject[];
}

export interface PoseOverlayArtifact {
  job_id: string;
  video_id?: string;
  status: "available" | "no_poses" | "unavailable";
  detail: string;
  keypoint_schema: string;
  source: FrameSourceSize;
  skeleton_edges: SkeletonEdge[];
  frames: PoseOverlayFrame[];
}

export interface BallTrajectorySample {
  frame_index: number;
  timestamp_sec: number;
  image_xy?: [number, number] | number[] | null;
  court_xy?: [number, number] | number[] | null;
  confidence?: number | null;
  visible?: boolean;
  accepted?: boolean;
  interpolated?: boolean;
  candidate_count?: number;
  source?: string;
  in_bounds?: boolean | null;
}

export interface BallTrajectoryArtifact {
  schema_version: string;
  job_id: string;
  status: "available" | "partial" | "no_candidates" | "no_detections" | "unavailable" | "skipped" | "failed";
  detail: string;
  coordinate_system?: {
    image?: string;
    court?: string;
    court_width?: number;
    court_length?: number;
  };
  filtering?: Record<string, unknown>;
  samples: BallTrajectorySample[];
}

export interface BounceEventCandidate {
  event_id: string;
  frame_index: number;
  timestamp_sec: number;
  image_xy: [number, number] | number[];
  court_xy?: [number, number] | number[] | null;
  confidence: number;
  detection_method: string;
  diagnostics?: Record<string, unknown>;
  rally_id?: string | null;
}

export interface BounceEventsArtifact {
  schema_version: string;
  job_id: string;
  status: "available" | "no_candidates" | "partial" | "unavailable" | "skipped" | "failed";
  detail: string;
  coordinate_system?: {
    image?: string;
    court?: string;
    court_width?: number;
    court_length?: number;
  };
  detection_method?: string;
  events: BounceEventCandidate[];
}

// ---- 事件切分重建球轨迹（第三套产物，前端按段直接渲染） ----

export type ReconstructedSampleSource = "detected" | "interpolated" | "model_predicted" | "anchor";

export interface ReconstructedBallTrajectorySample {
  frame_index: number;
  timestamp_sec: number;
  court_xy?: [number, number] | number[] | null;
  estimated_height_ft?: number | null;
  source: ReconstructedSampleSource;
  confidence?: number | null;
  height_source?: string | null;
  height_confidence?: number | null;
  height_uncertainty_ft?: number | null;
  gap_length_frames?: number | null;
  reprojection_error_px?: number | null;
}

export interface ReconstructedTrajectoryAnchor {
  anchor_id: string;
  anchor_type: "bounce" | "contact" | "raw_endpoint" | "loss";
  frame_index: number;
  court_xy?: [number, number] | number[] | null;
  height_ft?: number | null;
  confidence?: number;
  uncertainty_ft?: number;
}

export interface ReconstructedTrajectoryQuality {
  observation_coverage?: number;
  detection_score?: number;
  image_fit_rmse_px?: number | null;
  fit_score?: number;
  predicted_ratio?: number;
  continuity_score?: number;
  anchor_confidence?: number;
  event_confidence?: number;
  physical_plausibility?: number;
  net_crossing_status?: "not_expected" | "expected" | "estimated" | "implausible" | "unknown";
  height_confidence?: number;
  overall?: number;
  display_level?: "high" | "medium" | "low" | "none";
}

export interface ReconstructedBallTrajectorySegment {
  segment_id: string;
  reconstruction_mode: "dual_anchor_warp" | "single_anchor_warp" | "image_only" | "local_visual_arc";
  status: "reconstructed" | "insufficient_spatial_anchors";
  start_event_id?: string | null;
  end_event_id?: string | null;
  start_event_type?: string | null;
  end_event_type?: string | null;
  boundary_reason?: string;
  fit_space?: string;
  model?: string;
  anchors: ReconstructedTrajectoryAnchor[];
  quality?: ReconstructedTrajectoryQuality;
  samples: ReconstructedBallTrajectorySample[];
}

export interface ReconstructedBallTrajectoryEvent {
  event_id: string;
  event_type: "hit" | "bounce" | "loss" | "serve_reset" | "end_of_stream";
  frame_index: number;
  timestamp_sec: number;
  image_xy?: [number, number] | number[] | null;
  court_xy?: [number, number] | number[] | null;
  confidence?: number;
  source?: string;
  diagnostics?: Record<string, unknown>;
}

export interface ReconstructedBallTrajectoryArtifact {
  schema_version: string;
  job_id: string;
  status: "available" | "no_candidates" | "partial" | "unavailable" | "skipped" | "failed";
  detail: string;
  reconstruction_mode: "event_anchored_2_5d";
  coordinate_semantics?: {
    xy?: string;
    z?: string;
    metric_validity?: string;
  };
  events: ReconstructedBallTrajectoryEvent[];
  segments: ReconstructedBallTrajectorySegment[];
}

export interface ServeEventCandidate {
  id: string;
  timestamp_seconds: number;
  frame_index: number;
  confidence: number;
  seek_time_seconds: number;
  reason: string;
  source_signals: Array<"tracking" | "pose" | "trajectory" | "roi" | "video">;
  track_id?: string;
  player_id?: string;
  start_time_seconds?: number;
  end_time_seconds?: number;
  detection_mode?: "pose" | "roi" | "trajectory" | "tracking";
  context_state?: "ready_to_serve" | "candidate" | "rejected" | "unavailable";
  court_position?: [number, number] | number[];
  court_unit?: string;
  signals?: {
    baseline_position_score?: number;
    pre_stillness_score?: number;
    arm_motion_peak_score?: number;
    roi_motion_peak_score?: number;
    rally_after_score?: number;
    receiver_waiting_score?: number;
  };
}

export interface ServeEventsArtifact {
  job_id: string;
  video_id?: string;
  status: "available" | "no_candidates" | "partial" | "unavailable";
  detail: string;
  detector_version: string;
  duration_seconds?: number;
  fps: number;
  frame_count: number;
  processed_frame_count: number;
  frame_stride: number;
  detection_mode?: "pose" | "roi" | "trajectory" | "tracking";
  available_signals?: Array<"tracking" | "pose" | "trajectory" | "roi" | "video">;
  coverage?: {
    source_duration_seconds?: number;
    tracking_first_timestamp_seconds?: number;
    tracking_last_timestamp_seconds?: number;
    pose_first_timestamp_seconds?: number;
    pose_last_timestamp_seconds?: number;
    trajectory_first_timestamp_seconds?: number;
    trajectory_last_timestamp_seconds?: number;
    score_series_first_timestamp_seconds?: number;
    score_series_last_timestamp_seconds?: number;
    score_series_count?: number;
    candidate_first_timestamp_seconds?: number;
    candidate_last_timestamp_seconds?: number;
    candidate_count?: number;
    coverage_ratio?: number;
    warnings?: string[];
    gaps?: string[];
  };
  debug_artifacts?: {
    candidates_url?: string;
    score_series_url?: string;
    clips_manifest_url?: string;
    debug_overlay_url?: string;
    status?: string;
    detail?: string;
  };
  events: ServeEventCandidate[];
}

export interface AnalysisPipelineResult {
  job_id: string;
  video_id?: string;
  calibration_id?: string;
  status: "completed" | "failed";
  generated_at: string;
  stages: PipelineStageResult[];
  tracks: PipelineTrackPoint[];
  metrics: {
    distances: Array<{ track_id: string; distance_ft: number }>;
    speeds: Array<{
      track_id: string;
      average_speed_ft_per_s: number;
      max_speed_ft_per_s: number;
      segments: Array<{
        track_id: string;
        start_time: number;
        end_time: number;
        speed_ft_per_s: number;
      }>;
    }>;
    kitchen_dwell: Array<{ track_id: string; kitchen_frames: number; kitchen_seconds: number }>;
    doubles_spacing: Array<{
      pair: [string, string];
      average_spacing_ft: number;
      min_spacing_ft: number;
      max_spacing_ft: number;
      samples: Array<{
        timestamp_seconds: number;
        track_a: string;
        track_b: string;
        distance_ft: number;
      }>;
    }>;
    heatmap: {
      rows: number;
      cols: number;
      cells: Array<{ row: number; col: number; count: number }>;
    };
    metric_statuses?: Record<string, {
      status: "available" | "not_applicable" | "insufficient_players";
      reason?: string;
      expected_player_count?: number;
      observed_player_count?: number;
    }>;
  };
  match_context?: {
    schema_version: string;
    match_format: "singles" | "doubles";
    expected_player_count: 2 | 4;
    players_per_side: 1 | 2;
    near_side_quota: 1 | 2;
    far_side_quota: 1 | 2;
    enable_doubles_spacing: boolean;
  };
  observed_player_count?: number;
  artifacts: {
    result_json_path?: string;
    tracking_result_json_path?: string;
    tracking_overlay_json_path?: string;
    tracking_overlay_url?: string;
    pose_overlay_json_path?: string;
    pose_overlay_url?: string;
    serve_events_json_path?: string;
    serve_events_url?: string;
    serve_debug_candidates_json_path?: string;
    serve_debug_candidates_url?: string;
    serve_score_series_json_path?: string;
    serve_score_series_url?: string;
    serve_clips_manifest_json_path?: string;
    serve_clips_manifest_url?: string;
    serve_debug_overlay_path?: string;
    serve_debug_overlay_url?: string;
    court_view_roi_json_path?: string;
    court_view_roi_url?: string;
    source_video_url?: string;
    detections_jsonl_path?: string;
    detections_url?: string;
    detections_status?: string;
    detections_detail?: string;
    ball_overlay_json_path?: string;
    ball_overlay_url?: string;
    ball_overlay_status?: string;
    ball_overlay_detail?: string;
    ball_trajectory_json_path?: string;
    ball_trajectory_url?: string;
    ball_trajectory_status?: string;
    ball_trajectory_detail?: string;
    cleaned_ball_trajectory_json_path?: string;
    cleaned_ball_trajectory_url?: string;
    cleaned_ball_trajectory_status?: string;
    cleaned_ball_trajectory_detail?: string;
    bounce_events_json_path?: string;
    bounce_events_url?: string;
    bounce_events_status?: string;
    bounce_events_detail?: string;
    reconstructed_ball_trajectory_json_path?: string;
    reconstructed_ball_trajectory_url?: string;
    reconstructed_ball_trajectory_status?: string;
    reconstructed_ball_trajectory_detail?: string;
    analysis_overlay_video_path?: string;
    analysis_overlay_video_url?: string;
    analysis_overlay_video_status?: string;
    analysis_overlay_video_detail?: string;
    heatmaps_manifest_json_path?: string;
    heatmaps_url?: string;
    scatter_plots_manifest_json_path?: string;
    scatter_plots_url?: string;
    position_visualizations_status?: string;
    position_visualizations_detail?: string;
    tracking_overlay_status?: string;
    tracking_overlay_detail?: string;
    pose_overlay_status?: string;
    pose_overlay_detail?: string;
    serve_events_status?: string;
    serve_events_detail?: string;
    serve_debug_artifacts_status?: string;
    serve_debug_artifacts_detail?: string;
    court_view_roi_status?: string;
    court_view_roi_detail?: string;
    overlay_video_path?: string;
  };
  message: string;
}

export interface VisualizationManifestItem {
  id: string;
  kind: string;
  label: string;
  title: string;
  description: string;
  file_name: string;
  file_path?: string;
  url: string;
  artifact_url?: string;
  width: number;
  height: number;
  source_artifacts: string[];
}

export interface VisualizationManifest {
  schema_version: string;
  job_id: string;
  status: string;
  detail: string;
  items: VisualizationManifestItem[];
}

export interface AnalysisApiError {
  code: string;
  message: string;
  detail?: string;
}

export interface MatchSummary {
  title: string;
  subtitle: string;
  date: string;
  venue: string;
  teams: string;
  score: string;
  currentRally: string;
  currentTime: string;
  duration: string;
}

export interface PlayerMarker {
  id: string;
  label: string;
  team: "near" | "far";
  x: number;
  y: number;
  color: string;
}

export interface ShotTrajectory {
  id: string;
  path: string;
  color: string;
  label: string;
}

export interface VideoOverlayLabel {
  id: string;
  label: string;
  tone: InsightTone;
  x: number;
  y: number;
}

export interface TimelineMarker {
  id: string;
  time: string;
  position: number;
  label: string;
  tone: InsightTone;
}

export interface Highlight {
  id: string;
  title: string;
  time: string;
  result: string;
  tone: InsightTone;
  description: string;
}

export interface CoachNote {
  id: string;
  tone: InsightTone;
  title: string;
  body: string;
}

export interface ReportAction {
  type: ReportType;
  title: string;
  description: string;
  path: `/reports/${ReportType}`;
}

export interface DashboardMetric extends Metric {
  icon: string;
  progress: number;
  sparkline: number[];
}

export interface ShotRow {
  id: string;
  time: string;
  type: ShotType;
  player: string;
  placement: string;
  qualityScore: number;
  qualityBand: QualityBand;
  result: ShotResult;
}

export interface SkillRating {
  id: string;
  label: string;
  score: number;
  note: string;
}

// ── 球员六维雷达评分 ──────────────────────────────────────────────

export type PlayerScoreDimensionKey =
  | "serve"
  | "return_serve"
  | "offense"
  | "defense"
  | "agility"
  | "shot_consistency";

export interface PlayerScoreDimension {
  key: PlayerScoreDimensionKey;
  label: string;
}

/** 六维评分维度（顺序即雷达图轴序）：发球 / 接发球 / 进攻能力 / 防守能力 / 敏捷 / 击球稳定性。 */
export const PLAYER_SCORE_DIMENSIONS: readonly PlayerScoreDimension[] = [
  { key: "serve", label: "发球" },
  { key: "return_serve", label: "接发球" },
  { key: "offense", label: "进攻能力" },
  { key: "defense", label: "防守能力" },
  { key: "agility", label: "敏捷" },
  { key: "shot_consistency", label: "击球稳定性" },
];

/**
 * 单名球员的六维评分。
 * 键为 canonical player id（`Player_1`..`Player_4`），与视频叠加 HUD 的 P1..P4 对齐；
 * 分值 0–10、1 位小数。数据源当前为 mock，但键契约保持 canonical，为真实算法预留。
 */
export interface PlayerScore {
  player_id: string;
  serve: number;
  return_serve: number;
  offense: number;
  defense: number;
  agility: number;
  shot_consistency: number;
}

/** 球员评分聚合：按 canonical player id 索引，便于 O(1) 按球员取值。 */
export interface PlayerScoring {
  players: Record<string, PlayerScore>;
}

export interface DrillRecommendation {
  id: string;
  title: string;
  goal: string;
  duration: string;
  evidence: string;
  difficulty: "基础" | "进阶" | "高级";
  linkedReport: ReportType;
}

export interface ProgressPoint {
  match: string;
  performance: number;
  errors: number;
  thirdShot: number;
  kitchen: number;
}

export interface OverviewCard {
  id: string;
  title: string;
  body: string;
  path: AppPath;
  metric: string;
}

export interface ReportDefinition {
  type: ReportType;
  title: string;
  eyebrow: string;
  summary: string;
  heroMetric: string;
  heroMetricLabel: string;
  visualization: "movement" | "diagnosis";
  metrics: DashboardMetric[];
  insights: CoachNote[];
  trainingLink: string;
}

// ── 完整分析报告 ──

/** 分析报告（聚合所有可视化数据） */
export interface AnalysisReport {
  version: "analysis-report-v1";
  source: "demo" | "job";
  jobId?: string;
  reportId: string;
  generatedAt: string;
  metadata: AnalysisUploadMetadata;
  match: MatchSummary;
  session: ReportSession;
  dashboardMetrics: DashboardMetric[];
  reportDefinitions: ReportDefinition[];
  reportActions: ReportAction[];
  playerMarkers: PlayerMarker[];
  shotTrajectories: ShotTrajectory[];
  videoOverlayLabels: VideoOverlayLabel[];
  timelineMarkers: TimelineMarker[];
  highlights: Highlight[];
  coachNotes: CoachNote[];
  diagnoses: Diagnosis[];
  trainingRecommendations: TrainingRecommendation[];
  drillRecommendations: DrillRecommendation[];
  shotRows: ShotRow[];
  skillRatings: SkillRating[];
  progressPoints: ProgressPoint[];
}

// ── 结构化可视化数据（前端 SVG 渲染） ──────────────────────────────

export interface HeatmapCell {
  row: number;
  col: number;
  count: number;
}

export interface VisualGrid {
  rows: number;
  cols: number;
  max_count: number;
  cells: HeatmapCell[];
}

export interface HeatmapPlayerGrid {
  id: string;
  label: string;
  color: string;
  grid: VisualGrid;
}

export interface VisualHeatmaps {
  visual_grid?: VisualGrid;
  players: HeatmapPlayerGrid[];
}

export interface ZoneStat {
  zone: string;          // kitchen / transition / backcourt
  label: string;         // 网前区 / 过渡区 / 后场区
  seconds: number;
  occupancy: number;
}

export interface ZoneFeedback {
  level: string;         // excellent / good / insufficient
  summary: string;
}

export interface PlayerZoneStats {
  id: string;
  label: string;
  color: string;
  denominator_seconds: number;
  tracked_seconds: number;
  data_sufficiency: string;   // sufficient / insufficient
  kitchen_control_rate: number;
  avg_distance_to_kitchen_line_m: number;
  zones: ZoneStat[];
  feedback?: ZoneFeedback | null;
}

export interface ZoneStats {
  players: PlayerZoneStats[];
}

export interface ScatterPlayer {
  id: string;
  label: string;
  color: string;
  points: [number, number][];
}

export interface ScatterPlots {
  players: ScatterPlayer[];
  ball: [number, number][];
  bounces: [number, number][];
}

export interface PlayerTrajectory {
  id: string;
  label: string;
  path: [number, number][];
}

export interface CourtGeometry {
  court_width_ft: number;
  court_length_ft: number;
}

export interface StructuredVisualizationData {
  court: CourtGeometry;
  heatmaps?: VisualHeatmaps;
  scatter_plots: ScatterPlots;
  player_trajectories: PlayerTrajectory[];
  zone_stats?: ZoneStats;
}

// ── player-render-trajectory v2 types ──

export interface RawPlayerRenderFrame {
  sequence_index?: number;
  frame_index: number;
  timestamp_seconds: number;
  x_ft: number;
  y_ft: number;
  source: string;
  confidence?: number | null;
  player_id: string;
  render_slot?: string | null;
  side?: string | null;
  segment_id?: string | null;
  identity_epoch?: number | null;
  source_track_id?: number | null;
  projection_status?: string | null;
  projection_confidence?: number | null;
  footpoint_method?: string | null;
}

export interface RenderPlayerMetadata {
  player_id: string;
  render_slot: string;
  initial_side: string;
  dominant_side: string;
  first_frame_index: number;
  source_track_ids: number[];
}

export interface RenderSegmentMetadata {
  segment_id: string;
  player_id: string;
  identity_epoch: number;
  start_frame_index: number;
  end_frame_index: number;
  start_timestamp_seconds: number;
  end_timestamp_seconds: number;
  break_before: string;
  sample_count: number;
}

export interface CourtVisualizationStyleProfile {
  version: string;
  players: Record<string, string>;
  ball: string;
  bounce: string;
  outside_player: string;
  player_trail_seconds: number;
  ball_trail_seconds: number;
  bounce_display_seconds: number;
  radius_min_px: number;
  radius_max_px: number;
}

export interface RawPlayerRenderTrajectoryV1 {
  schema_version?: string;
  players?: Record<string, RawPlayerRenderFrame[]>;
  samples?: RawPlayerRenderFrame[];
}

export type RawPlayerRenderTrajectoryV2 = {
  schema_version: string;
  players: RenderPlayerMetadata[];
  segments: RenderSegmentMetadata[];
  samples: RawPlayerRenderFrame[];
  style_profile?: CourtVisualizationStyleProfile | null;
  segmentation_profile?: { version: string; jump_threshold_ft: number; max_visible_gap_seconds: number } | null;
};

export type RawPlayerRenderTrajectory = RawPlayerRenderTrajectoryV1 | RawPlayerRenderTrajectoryV2;

export interface NormalizedRenderFrame {
  sequence_index: number;
  frame_index: number;
  timestamp_seconds: number;
  x_ft: number;
  y_ft: number;
  source: string;
  confidence: number | null;
  player_id: string;
  render_slot: string;
  side: "near" | "far" | "unknown";
  segment_id: string;
  identity_epoch: number;
  source_track_id: number | null;
  projection_status: string | null;
  projection_confidence: number | null;
  footpoint_method: string | null;
}

export interface NormalizedPlayerRenderTrajectory {
  players: RenderPlayerMetadata[];
  segments: RenderSegmentMetadata[];
  samples: NormalizedRenderFrame[];
  style_profile: CourtVisualizationStyleProfile;
  segmentation_profile: { version: string; jump_threshold_ft: number; max_visible_gap_seconds: number } | null;
  /** samples indexed by player_id → samples[] */
  byPlayer: Record<string, NormalizedRenderFrame[]>;
  /** samples indexed by segment_id → samples[] */
  bySegment: Record<string, NormalizedRenderFrame[]>;
}

export const DEFAULT_COURT_VISUAL_THEME_V1: CourtVisualizationStyleProfile = {
  version: "court-visual-theme.v1",
  players: {
    slot_1: "#22D3EE",
    slot_2: "#FBBF24",
    slot_3: "#A78BFA",
    slot_4: "#F97316",
  },
  ball: "#67E8F9",
  bounce: "#FB923C",
  outside_player: "#94A3B8",
  player_trail_seconds: 2.5,
  ball_trail_seconds: 1.0,
  bounce_display_seconds: 0.8,
  radius_min_px: 2.0,
  radius_max_px: 6.0,
};
