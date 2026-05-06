export type TrendDirection = "up" | "down" | "steady";

export type CourtMode = "heat" | "routes" | "movement";

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
