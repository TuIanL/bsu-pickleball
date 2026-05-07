export type TrendDirection = "up" | "down" | "steady";

export type CourtMode = "heat" | "routes" | "movement";

export type ReportType = "landing" | "movement" | "rally" | "diagnosis";

export type AnalysisJobStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "failed"
  | "completed";

export type AnalysisStageId =
  | "upload"
  | "queue"
  | "frame-sampling"
  | "detection"
  | "pose"
  | "tracking"
  | "court-calibration"
  | "event-analysis"
  | "report";

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
  | `/analysis/${string}`
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
  path: AppPath | "/reports/landing";
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
  status: "pending" | "active" | "done" | "failed";
  detail: string;
}

export interface AnalysisJobSummary {
  id: string;
  status: AnalysisJobStatus;
  stage: AnalysisStageId;
  progress: number;
  createdAt: string;
  updatedAt: string;
  metadata: AnalysisUploadMetadata;
  stages: AnalysisStage[];
  reportId?: string;
  errorMessage?: string;
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
  path: AppPath | "/reports/landing";
  metric: string;
}

export interface ReportDefinition {
  type: ReportType;
  title: string;
  eyebrow: string;
  summary: string;
  heroMetric: string;
  heroMetricLabel: string;
  visualization: "heat" | "movement" | "rally" | "diagnosis";
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
