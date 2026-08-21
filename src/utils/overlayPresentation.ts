import type {
  FusedPlayerEvidenceType,
  FusedPlayerOverlayEntity,
} from "../types/report";
import { canonicalPlayerNumber, playerColor } from "./analysisHelpers";

/**
 * 展示解析纯函数（stabilize-multiview-overlay-temporal-continuity D2b）。
 *
 * 三层职责正交：
 * - `player_id`          → identity hue（跨 evidence 恒定）     resolvePlayerIdentityHue
 * - `display_state`      → geometry topology（BOX/POINT/HIDDEN）resolveDisplayGeometry
 * - `evidence_type`      → provenance style（实/虚/透明度/badge）resolveEvidencePresentation
 *
 * renderer 只消费这些 resolver 的结果，不在 JSX 里散落条件。
 */

export interface EvidencePresentation {
  /** true = 实线（真实检测），false = 虚线/淡化（合成/投影/预测） */
  solid: boolean;
  opacity: number;
  label: string;
}

const EVIDENCE_PRESENTATION: Record<FusedPlayerEvidenceType, EvidencePresentation> = {
  base_observed: { solid: true, opacity: 1, label: "检测" },
  guided_observed: { solid: true, opacity: 1, label: "协同恢复" },
  refined_observed: { solid: true, opacity: 1, label: "离线精修" },
  // 合成证据诚实降级：不伪装为实线真实检测，identity hue 保持不变
  cross_view_projected: { solid: false, opacity: 0.85, label: "双摄补全" },
  predicted_only: { solid: false, opacity: 0.55, label: "预测" },
  bootstrap_backfill: { solid: true, opacity: 0.85, label: "启动回填" },
};

/** 非 canonical / non-legacy ID 的确定性 hash 调色板（避免全部落到默认灰/绿撞色）。 */
const EXTRA_HUES = [
  "#2DD4BF",
  "#F472B6",
  "#A3E635",
  "#FACC15",
  "#FB7185",
  "#60A5FA",
  "#FBBF24",
  "#A78BFA",
] as const;

/** 兼容旧 ID 形态：P1 / p1 / player_1 / global_player_1 → 数字 1..4。 */
const LEGACY_PLAYER_RE = /^(?:P|p|player_|global_player_)([1-4])$/;

function parseLegacyPlayerNumber(id: string): number | null {
  const m = LEGACY_PLAYER_RE.exec(id.trim());
  return m ? Number(m[1]) : null;
}

/** 确定性 hash 槽位：同一 unknown ID 恒取同一 hue（跨 evidence 稳定）。 */
function unknownHue(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0;
  }
  return EXTRA_HUES[h % EXTRA_HUES.length];
}

/**
 * identity hue 唯一 authority：
 * canonical Player_N → 固定 palette；legacy ID（P1/player_1/...）normalise 后进 palette；
 * 其余 unknown → deterministic hash palette。均满足"同一 ID 跨 evidence hue 恒定"。
 */
export function resolvePlayerIdentityHue(playerId?: string | null): string {
  if (!playerId) {
    return playerColor(null);
  }
  const id = playerId.trim();
  if (canonicalPlayerNumber(id) !== null) {
    return playerColor(id);
  }
  const legacy = parseLegacyPlayerNumber(id);
  if (legacy !== null) {
    return playerColor(`Player_${legacy}`);
  }
  return unknownHue(id);
}

/** provenance style：evidence 决定实/虚/透明度/badge，MUST NOT 影响 identity hue。 */
export function resolveEvidencePresentation(evidence: FusedPlayerEvidenceType): EvidencePresentation {
  return EVIDENCE_PRESENTATION[evidence] ?? { solid: false, opacity: 0.6, label: "" };
}

/** geometry topology：display_state → BOX/POINT/HIDDEN；未知（旧产物缺失）返回 undefined（由 evidence 兜底推导）。 */
export type DisplayGeometry = "box" | "point" | "hidden";

export function resolveDisplayGeometry(displayState?: string | null): DisplayGeometry | undefined {
  switch (displayState) {
    case "REAL_BOX":
    case "ASSISTED_BOX":
    case "PROJECTED_BOX":
      return "box";
    case "PROJECTED_POINT":
    case "PREDICTED_POINT":
      return "point";
    case "HIDDEN":
      return "hidden";
    default:
      return undefined;
  }
}

/**
 * 有效 display_state：新产物取 direct authority；旧产物（缺失字段）由 evidence + bbox 推导 legacy state。
 */
export function resolveEffectiveDisplayState(entity: FusedPlayerOverlayEntity): string {
  if (entity.display_state) {
    return entity.display_state;
  }
  const ev = entity.evidence_type;
  if (ev === "predicted_only") {
    return "PREDICTED_POINT";
  }
  if (ev === "cross_view_projected") {
    return entity.bbox ? "PROJECTED_BOX" : "PROJECTED_POINT";
  }
  if (ev === "guided_observed" || ev === "refined_observed" || ev === "bootstrap_backfill") {
    return "ASSISTED_BOX";
  }
  return "REAL_BOX";
}