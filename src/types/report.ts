export type TrendDirection = "up" | "down" | "steady";

export type CourtMode = "movement";

export type ReportType = "movement" | "diagnosis";

export type AnalysisJobStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "failed"
  | "completed"
  | "canceled";

export type AnalysisCanonicalStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "canceled";

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

export type CameraAngle =
  | "baseline"
  | "sideline"
  | "elevated"
  | "unknown";

export type MatchFormat = "singles" | "doubles";

export type AppPath =
  | "/"
  | "/vision"
  | "/analysis/new"
  | "/analysis/tasks"
  | `/analysis/${string}`
  | `/analysis/${string}/details`
  | `/analysis/${string}/vision`
  | `/analysis/${string}/reports/${ReportType}`
  | "/training"
  | "/hardware"
  | `/reports/${ReportType}`;

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

export type QualityBand = "high" | "medium" | "low";

export interface Metric {
  id: string;
  label: string;
  value: string;
  detail: string;
  trend: string;
  direction: TrendDirection;
}

export interface CourtPoint {
  id: string;
  x: number;
  y: number;
  intensity: number;
  label: string;
}

export interface CourtRoute {
  id: string;
  from: CourtPoint;
  to: CourtPoint;
  label: string;
  result: "得分" | "受迫回球" | "失误" | "相持";
}

export interface MovementPoint {
  x: number;
  y: number;
}

export interface Rally {
  id: string;
  title: string;
  duration: string;
  shots: number;
  pattern: string;
  result: string;
  observation: string;
}

export interface ReportSession {
  athlete: string;
  venue: string;
  date: string;
  level: string;
  reportId: string;
  summary: string;
  metrics: Metric[];
  landingPoints: CourtPoint[];
  routes: CourtRoute[];
  movementPath: MovementPoint[];
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

export interface NavigationItem {
  id: string;
  label: string;
  shortLabel: string;
  path: AppPath;
}

export interface AnalysisUploadMetadata {
  fileName: string;
  fileSize?: number;
  matchTitle: string;
  venue: string;
  matchDate: string;
  matchFormat: MatchFormat;
  cameraAngle: CameraAngle;
  athleteLabel: string;
  level: string;
}

export interface AnalysisStage {
  id: AnalysisStageId;
  label: string;
  status: "pending" | "active" | "done" | "failed" | "skipped" | "canceled";
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
}

export interface PipelineStageResult {
  id: string;
  label: string;
  status: "pending" | "active" | "done" | "failed" | "skipped" | "canceled";
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
  };
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
    source_video_url?: string;
    tracking_overlay_status?: string;
    tracking_overlay_detail?: string;
    pose_overlay_status?: string;
    pose_overlay_detail?: string;
    serve_events_status?: string;
    serve_events_detail?: string;
    serve_debug_artifacts_status?: string;
    serve_debug_artifacts_detail?: string;
    overlay_video_path?: string;
  };
  message: string;
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
