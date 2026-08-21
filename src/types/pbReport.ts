// =============================================================
// PB Vision 风格报告页 - 统一类型声明
// =============================================================
import type { ShotType } from "./report";

// ── 6 个能力维度键 ──────────────────────────────────────────
export type PbDimensionKey =
  | "kitchen"
  | "ballctrl"
  | "defense"
  | "offense"
  | "courtiq"
  | "targeting";

export const PB_DIMENSION_META: Record<
  PbDimensionKey,
  { label: string; labelEn: string; cssColorVar: string; cssBgVar: string }
> = {
  kitchen: {
    label: "网前对抗",
    labelEn: "Kitchen Game",
    cssColorVar: "--pb-dim-kitchen",
    cssBgVar: "--pb-dim-kitchen-bg",
  },
  ballctrl: {
    label: "控球能力",
    labelEn: "Ball Control",
    cssColorVar: "--pb-dim-ballctrl",
    cssBgVar: "--pb-dim-ballctrl-bg",
  },
  defense: {
    label: "防守",
    labelEn: "Defense",
    cssColorVar: "--pb-dim-defense",
    cssBgVar: "--pb-dim-defense-bg",
  },
  offense: {
    label: "进攻",
    labelEn: "Offense",
    cssColorVar: "--pb-dim-offense",
    cssBgVar: "--pb-dim-offense-bg",
  },
  courtiq: {
    label: "球场智商",
    labelEn: "Court IQ",
    cssColorVar: "--pb-dim-courtiq",
    cssBgVar: "--pb-dim-courtiq-bg",
  },
  targeting: {
    label: "落点精准",
    labelEn: "Targeting",
    cssColorVar: "--pb-dim-targeting",
    cssBgVar: "--pb-dim-targeting-bg",
  },
};

export const PB_DIMENSION_ORDER: PbDimensionKey[] = [
  "kitchen",
  "ballctrl",
  "defense",
  "offense",
  "courtiq",
  "targeting",
];

// ── 击球阶段过滤器 ──────────────────────────────────────────
export type PbStageFilter =
  | "all"
  | "serves"
  | "third"
  | "fifth_plus";

export const PB_STAGE_OPTIONS: { value: PbStageFilter; label: string }[] = [
  { value: "third", label: "第三拍" },
  { value: "all", label: "全部击球" },
  { value: "serves", label: "发球" },
  { value: "fifth_plus", label: "第五拍及以上" },
];

// ── 击球类型过滤器 ──────────────────────────────────────────
export type PbShotTypeFilter = "all" | ShotType;

export const PB_SHOT_TYPE_OPTIONS: { value: PbShotTypeFilter; label: string }[] = [
  { value: "all", label: "全部击球类型" },
  { value: "发球", label: "发球" },
  { value: "接发", label: "接发" },
  { value: "第三拍", label: "第三拍" },
  { value: "轻吊", label: "轻吊" },
  { value: "抽击", label: "抽击" },
  { value: "重置", label: "重置" },
  { value: "截击", label: "截击" },
  { value: "扣杀", label: "扣杀" },
  { value: "失误", label: "失误" },
];

// ── pbMockData 相关的返回结构 ────────────────────────────────
export interface PbSpeedPercentileResult {
  percentile: number; // 60~90 整数
  label: string; // 第60百分位 / 第84百分位 等
}

export interface PbServeReturnStat {
  total: number; // 总数，默认 9
  in: number; // 合法数
  out: number; // 出界数
  net: number; // 擦网（Returns 专有）
}

export interface PbServeReturnStats {
  serves: PbServeReturnStat;
  returns: PbServeReturnStat;
}

/** 深度分布：Deep / Medium / Shallow 百分比，和为 100 */
export interface PbDepthDistribution {
  deep: number;
  medium: number;
  shallow: number;
}

export interface PbServeReturnDepth {
  serve: PbDepthDistribution;
  return_: PbDepthDistribution;
}

// ── PbReportContext 数据结构 ────────────────────────────────
import type { AnalysisReport } from "./report";

export interface PbReportContextValue {
  // --- 原始数据 ---
  report: AnalysisReport;

  // --- 用户交互状态 ---
  selectedPlayerId: string;
  setSelectedPlayerId: (id: string) => void;

  stageFilter: PbStageFilter;
  setStageFilter: (s: PbStageFilter) => void;

  typeFilter: PbShotTypeFilter;
  setTypeFilter: (t: PbShotTypeFilter) => void;

  qualityThreshold: number; // 0~100
  setQualityThreshold: (q: number) => void;

  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
  toggleDrawer: () => void;

  // --- 派生：当前选中球员 ---
  selectedSubject?: { id: string; name: string; role?: string };

  // --- 证据层（设计 D2）：Player-only、playerId 关联后的证据 ---
  evidence?: import("../evidence/evidenceTypes").PlayerReportEvidence;
}
