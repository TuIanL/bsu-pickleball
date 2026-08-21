// =============================================================
// 报告证据层 —— 强类型契约
// -------------------------------------------------------------
// 让"缺数据"与"来源/原因"成为机器可验证的契约（设计 D2）。
// 任何可展示指标都应是 EvidenceValue<T>，禁止裸 number|null。
// =============================================================
import type { EstimatedBallTrajectory } from "../services/ballTrajectoryVisualization";
import type {
  AnalysisReport,
  HeatmapPlayerGrid,
  ProjectedFinding,
  ProjectedRecommendation,
  TrainingRecommendation,
} from "../types/report";

/** EvidenceValue 状态 */
export type EvidenceState = "available" | "unavailable" | "not_applicable" | "failed";

/** 指标来源（用于 invariant #5 可追溯） */
export interface EvidenceRef {
  kind:
    | "report"
    | "serve_events"
    | "ball_trajectory"
    | "reconstructed_trajectory"
    | "heatmap"
    | "performance_insight"
    | "roster";
  artifactId?: string;
  eventId?: string;
  field?: string;
}

/** 强类型指标值：available 带 value+provenance，否则带 reason */
export type EvidenceValue<T> =
  | { status: "available"; value: T; provenance: EvidenceRef[]; confidence?: number }
  | {
      status: "unavailable" | "not_applicable" | "failed";
      value: null;
      reason: string;
      provenance?: EvidenceRef[];
    };

/** 一次击球证据（含 rally 内拍序，语义见设计 D3） */
export interface ShotEvidence {
  id: string;
  rallyId: string | null;
  ordinalInRally: number | null;
  playerId: string | null;
  type: string;
  qualityScore: number;
  provenance: EvidenceRef[];
}

/** 阶段筛选（1=发球 2=接发 3=第三拍 4=第四拍 5+=后段） */
export type PbStageOrdinalFilter = "all" | "serves" | "third" | "fifth_plus";

/** 报告证据层的原材料（IO hook 组装，纯转换只消费它） */
export interface PlayerReportEvidenceSources {
  report: AnalysisReport;
  roster?: RosterMapping | null;
  serveEvents?: ServeEventsSource | null;
  trajectories?: EstimatedBallTrajectory[] | null; // 已由真实 artifact 组装好的轨迹（IO 层负责）
  visualization?: unknown; // StructuredVisualizationData，待接入
}

/** roster 映射的最小形态（可由 global-player-roster.v1 提取，或 report 内嵌） */
export type RosterMapping = Record<string, string>;

/** 发球事件最小契约（仅证明发球开始/发球者/发球起点，设计 D7） */
export interface ServeEventsSource {
  events: Array<{
    eventId: string;
    playerId: string | null;
    timestampSec: number | null;
    courtXFt?: number | null;
    courtYFt?: number | null;
  }>;
}

/** 第三拍统计（有分子/分母才显示"率"） */
export interface ThirdShotStats {
  numerator: number;
  denominator: number;
}

/** 发球/接发深度分布（权威未建立时 unavailable） */
export interface DepthDistribution {
  deep: number;
  medium: number;
  shallow: number;
}

/** 球员报告证据聚合 */
export interface PlayerReportEvidence {
  playerId: string;
  summary: {
    totalShots: EvidenceValue<number>;
    inRatePct: EvidenceValue<number>;
    ballSpeedMph: EvidenceValue<number>;
    paddleSpeedMph: EvidenceValue<number>;
  };
  courtCoverage: {
    distanceFt: EvidenceValue<number>;
    heatmap: EvidenceValue<HeatmapPlayerGrid>;
  };
  serveReturn: {
    serveCount: EvidenceValue<number>;
    serveInRatePct: EvidenceValue<number>;
    serveDepth: EvidenceValue<DepthDistribution>;
    returnCount: EvidenceValue<number>;
    returnDepth: EvidenceValue<DepthDistribution>;
  };
  shotExploration: ShotEvidence[];
  trajectories: EvidenceValue<EstimatedBallTrajectory[]>;
  insights: {
    findings: EvidenceValue<ProjectedFinding[]>;
    recommendations: EvidenceValue<ProjectedRecommendation[]>;
    coachNotes: EvidenceValue<TrainingRecommendation[]>;
    thirdShot: EvidenceValue<ThirdShotStats>;
  };
  isDemo: boolean;
}

export type { ProjectedFinding, ProjectedRecommendation, AnalysisReport };