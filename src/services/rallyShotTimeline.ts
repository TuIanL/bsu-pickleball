import type { CanonicalShotEvent, ShotRallyEventsArtifact } from "../types/shotRallyEvents";
import { formatPlayerId, playerColor } from "../utils/analysisHelpers";

export type RallyShotTimelineMode = "rallies" | "chronological" | "empty";
export type RallyShotStageKey = "serve" | "return" | "third" | "rally_shot" | "unknown";
export type RallyShotQualityBand = CanonicalShotEvent["quality"]["band"];

export const RALLY_SHOT_STAGE_LABELS: Record<RallyShotStageKey, string> = {
  serve: "发球",
  return: "接发",
  third: "第三拍",
  rally_shot: "后续击球",
  unknown: "未分类",
};

export const RALLY_SHOT_QUALITY_LABELS: Record<RallyShotQualityBand, string> = {
  high: "高质量",
  medium: "中质量",
  low: "低质量",
  none: "质量未知",
};

export interface RallyShotTimelineEvent {
  shotId: string;
  rallyId: string | null;
  ordinalInRally: number | null;
  timestampMs: number | null;
  startMs: number | null;
  endMs: number | null;
  stage: RallyShotStageKey;
  stageLabel: string;
  playerId: string | null;
  playerLabel: string;
  playerColor: string;
  ownershipStatus: CanonicalShotEvent["ownership_status"];
  ownershipLabel: string;
  qualityBand: RallyShotQualityBand;
  qualityLabel: string;
  evidenceStartMs: number | null;
  evidenceEndMs: number | null;
  canSeek: boolean;
  pathDistanceFt: number | null;
  shotType: string | null;
  strokeType: string | null;
  result: string | null;
  errorType: string | null;
}

export interface RallyShotTimelineRow {
  id: string;
  label: string;
  ordinal: number | null;
  startMs: number | null;
  endMs: number | null;
  isUnassigned: boolean;
  events: RallyShotTimelineEvent[];
}

export interface RallyShotTimelineSummary {
  shotCount: number;
  rallyCount: number;
  averageShotsPerRally: number | null;
  stageCounts: Record<RallyShotStageKey, number>;
  unassignedCount: number;
}

export interface RallyShotTimelineModel {
  mode: RallyShotTimelineMode;
  hasAuthoritativeRallyBoundary: boolean;
  rows: RallyShotTimelineRow[];
  events: RallyShotTimelineEvent[];
  summary: RallyShotTimelineSummary;
  detail: string;
}

const EMPTY_STAGE_COUNTS = (): Record<RallyShotStageKey, number> => ({
  serve: 0,
  return: 0,
  third: 0,
  rally_shot: 0,
  unknown: 0,
});

function finiteMs(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function firstEvidenceWindow(shot: CanonicalShotEvent): { startMs: number; endMs: number } | null {
  const window = shot.evidence_windows.find((candidate) => {
    const start = finiteMs(candidate.start_ms);
    const end = finiteMs(candidate.end_ms);
    return start !== null && end !== null && end >= start;
  });
  if (!window) return null;
  return { startMs: window.start_ms, endMs: window.end_ms };
}

export function shotTimelineTimestampMs(shot: Pick<CanonicalShotEvent, "contact_ms" | "start_ms" | "end_ms">): number | null {
  return finiteMs(shot.contact_ms) ?? finiteMs(shot.start_ms) ?? finiteMs(shot.end_ms);
}

function stageKey(stage: CanonicalShotEvent["stage"]): RallyShotStageKey {
  return stage && stage in RALLY_SHOT_STAGE_LABELS ? stage : "unknown";
}

function ownershipLabel(shot: CanonicalShotEvent, playerLabel: string): string {
  if (shot.ownership_status === "confirmed" && playerLabel) return playerLabel;
  if (shot.ownership_status === "not_applicable") return "不适用";
  return "击球者不明";
}

function toTimelineEvent(shot: CanonicalShotEvent): RallyShotTimelineEvent {
  const stage = stageKey(shot.stage);
  const playerId = shot.ownership_status === "confirmed" ? shot.hitter_player_id ?? null : null;
  const playerLabel = formatPlayerId(playerId) || "击球者不明";
  const evidence = firstEvidenceWindow(shot);
  return {
    shotId: shot.shot_id,
    rallyId: shot.rally_id ?? null,
    ordinalInRally: typeof shot.ordinal_in_rally === "number" && Number.isFinite(shot.ordinal_in_rally)
      ? shot.ordinal_in_rally
      : null,
    timestampMs: shotTimelineTimestampMs(shot),
    startMs: finiteMs(shot.start_ms),
    endMs: finiteMs(shot.end_ms),
    stage,
    stageLabel: RALLY_SHOT_STAGE_LABELS[stage],
    playerId,
    playerLabel,
    playerColor: playerColor(playerId),
    ownershipStatus: shot.ownership_status,
    ownershipLabel: ownershipLabel(shot, playerLabel),
    qualityBand: shot.quality.band,
    qualityLabel: RALLY_SHOT_QUALITY_LABELS[shot.quality.band],
    evidenceStartMs: evidence?.startMs ?? null,
    evidenceEndMs: evidence?.endMs ?? null,
    canSeek: evidence !== null,
    pathDistanceFt: typeof shot.trajectory.path_distance_ft === "number" && Number.isFinite(shot.trajectory.path_distance_ft)
      ? shot.trajectory.path_distance_ft
      : null,
    shotType: shot.shot_type ?? null,
    strokeType: shot.stroke_type ?? null,
    result: shot.result ?? null,
    errorType: shot.error_type ?? null,
  };
}

function eventOrder(left: RallyShotTimelineEvent, right: RallyShotTimelineEvent): number {
  const leftOrdinal = left.ordinalInRally ?? Number.MAX_SAFE_INTEGER;
  const rightOrdinal = right.ordinalInRally ?? Number.MAX_SAFE_INTEGER;
  return leftOrdinal - rightOrdinal
    || (left.timestampMs ?? Number.MAX_SAFE_INTEGER) - (right.timestampMs ?? Number.MAX_SAFE_INTEGER)
    || left.shotId.localeCompare(right.shotId);
}

function chronologicalOrder(left: RallyShotTimelineEvent, right: RallyShotTimelineEvent): number {
  return (left.timestampMs ?? Number.MAX_SAFE_INTEGER) - (right.timestampMs ?? Number.MAX_SAFE_INTEGER)
    || left.shotId.localeCompare(right.shotId);
}

function emptySummary(): RallyShotTimelineSummary {
  return {
    shotCount: 0,
    rallyCount: 0,
    averageShotsPerRally: null,
    stageCounts: EMPTY_STAGE_COUNTS(),
    unassignedCount: 0,
  };
}

export function buildRallyShotTimelineModel(artifact: ShotRallyEventsArtifact): RallyShotTimelineModel {
  if (artifact.status !== "available") {
    return {
      mode: "empty",
      hasAuthoritativeRallyBoundary: false,
      rows: [],
      events: [],
      summary: emptySummary(),
      detail: artifact.detail,
    };
  }

  const uniqueShots = new Map<string, CanonicalShotEvent>();
  for (const shot of artifact.shots) {
    if (!shot.shot_id || !uniqueShots.has(shot.shot_id)) uniqueShots.set(shot.shot_id, shot);
  }
  const events = [...uniqueShots.values()].map(toTimelineEvent).sort(chronologicalOrder);
  const hasAuthoritativeRallyBoundary = artifact.diagnostics.rally_boundary_status === "available" && artifact.rallies.length > 0;
  const stageCounts = EMPTY_STAGE_COUNTS();
  let unassignedCount = 0;
  for (const event of events) {
    stageCounts[event.stage] += 1;
    if (event.ownershipStatus !== "confirmed" || !event.playerId) unassignedCount += 1;
  }

  const rallyIds = new Set(artifact.rallies.map((rally) => rally.rally_id));
  const associatedEvents = events.filter((event) => event.rallyId !== null && rallyIds.has(event.rallyId));
  const summary: RallyShotTimelineSummary = {
    shotCount: events.length,
    rallyCount: hasAuthoritativeRallyBoundary ? artifact.rallies.length : 0,
    averageShotsPerRally: hasAuthoritativeRallyBoundary && artifact.rallies.length > 0
      ? associatedEvents.length / artifact.rallies.length
      : null,
    stageCounts,
    unassignedCount,
  };

  if (events.length === 0) {
    return {
      mode: "empty",
      hasAuthoritativeRallyBoundary,
      rows: [],
      events,
      summary,
      detail: artifact.detail,
    };
  }

  if (!hasAuthoritativeRallyBoundary) {
    return {
      mode: "chronological",
      hasAuthoritativeRallyBoundary: false,
      rows: [{ id: "chronological", label: "按时间排序", ordinal: null, startMs: null, endMs: null, isUnassigned: false, events }],
      events,
      summary,
      detail: artifact.detail,
    };
  }

  const rows: RallyShotTimelineRow[] = artifact.rallies
    .slice()
    .sort((left, right) => left.ordinal - right.ordinal || left.rally_id.localeCompare(right.rally_id))
    .map((rally) => ({
      id: rally.rally_id,
      label: `第 ${rally.ordinal} 回合`,
      ordinal: rally.ordinal,
      startMs: finiteMs(rally.start_ms),
      endMs: finiteMs(rally.end_ms),
      isUnassigned: false,
      events: events.filter((event) => event.rallyId === rally.rally_id).sort(eventOrder),
    }));
  const orphanEvents = events.filter((event) => event.rallyId === null || !rallyIds.has(event.rallyId));
  if (orphanEvents.length > 0) {
    rows.push({ id: "unassigned-rally", label: "未关联回合", ordinal: null, startMs: null, endMs: null, isUnassigned: true, events: orphanEvents });
  }

  return {
    mode: "rallies",
    hasAuthoritativeRallyBoundary: true,
    rows,
    events,
    summary,
    detail: artifact.detail,
  };
}
