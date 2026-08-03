import type {
  RawPlayerRenderTrajectoryV1,
  RawPlayerRenderTrajectoryV2,
  RawPlayerRenderFrame,
  RenderPlayerMetadata,
  RenderSegmentMetadata,
  NormalizedPlayerRenderTrajectory,
  NormalizedRenderFrame,
  CourtVisualizationStyleProfile,
} from "../types/report";
import { DEFAULT_COURT_VISUAL_THEME_V1 } from "../types/report";

function isV2(raw: { schema_version?: string }): raw is RawPlayerRenderTrajectoryV2 {
  return raw.schema_version === "player-render-trajectory.v2";
}

function naturalSortKey(id: string): [number, string] {
  const parts = id.split("_");
  const last = parts[parts.length - 1];
  const num = Number(last);
  return [Number.isFinite(num) ? num : 0, id];
}

export function normalizePlayerRenderTrajectory(
  raw: RawPlayerRenderTrajectoryV1 | RawPlayerRenderTrajectoryV2,
): NormalizedPlayerRenderTrajectory {
  if (isV2(raw)) {
    return normalizeV2(raw);
  }
  return normalizeV1(raw);
}

function normalizeV2(raw: RawPlayerRenderTrajectoryV2): NormalizedPlayerRenderTrajectory {
  const samples: NormalizedRenderFrame[] = (raw.samples ?? []).map((s, i) => ({
    sequence_index: s.sequence_index ?? i,
    frame_index: s.frame_index,
    timestamp_seconds: s.timestamp_seconds,
    x_ft: s.x_ft,
    y_ft: s.y_ft,
    source: s.source,
    confidence: s.confidence ?? null,
    player_id: s.player_id,
    render_slot: s.render_slot ?? "",
    side: (s.side as "near" | "far" | "unknown") ?? "unknown",
    segment_id: s.segment_id ?? "",
    identity_epoch: s.identity_epoch ?? 0,
    source_track_id: s.source_track_id ?? null,
    projection_status: s.projection_status ?? null,
    projection_confidence: s.projection_confidence ?? null,
    footpoint_method: s.footpoint_method ?? null,
  }));

  samples.sort((a, b) => a.timestamp_seconds - b.timestamp_seconds || a.frame_index - b.frame_index || a.player_id.localeCompare(b.player_id));

  const style_profile: CourtVisualizationStyleProfile = raw.style_profile ?? DEFAULT_COURT_VISUAL_THEME_V1;
  const segmentation_profile = raw.segmentation_profile ?? null;

  return buildIndexed(samples, raw.players ?? [], raw.segments ?? [], style_profile, segmentation_profile);
}

function normalizeV1(raw: RawPlayerRenderTrajectoryV1): NormalizedPlayerRenderTrajectory {
  const rawSamples = raw.samples ?? flattenV1Players(raw.players);
  if (rawSamples.length === 0) {
    return buildIndexed([], [], [], DEFAULT_COURT_VISUAL_THEME_V1, null);
  }

  rawSamples.sort((a, b) => a.timestamp_seconds - b.timestamp_seconds || a.frame_index - b.frame_index || a.player_id.localeCompare(b.player_id));

  const playerIds = [...new Set(rawSamples.map((s) => s.player_id))].sort((a, b) => {
    const [na, sa] = naturalSortKey(a);
    const [nb, sb] = naturalSortKey(b);
    return na - nb || sa.localeCompare(sb);
  });

  const slotMap = new Map<string, string>();
  playerIds.forEach((pid, i) => slotMap.set(pid, `slot_${i + 1}`));

  const players: RenderPlayerMetadata[] = playerIds.map((pid) => {
    const pts = rawSamples.filter((s) => s.player_id === pid);
    const detected = pts.filter((s) => s.source === "detected");
    const first = detected[0] ?? pts[0];
    const sides = detected.map((s) => classifySide(s.y_ft));
    const nearCount = sides.filter((s) => s === "near").length;
    const farCount = sides.filter((s) => s === "far").length;
    let dominant = "unknown";
    if (nearCount > farCount) dominant = "near";
    else if (farCount > nearCount) dominant = "far";
    else if (sides.length > 0) dominant = "mixed";
    return {
      player_id: pid,
      render_slot: slotMap.get(pid) ?? "",
      initial_side: first ? classifySide(first.y_ft) : "unknown",
      dominant_side: dominant,
      first_frame_index: first?.frame_index ?? 0,
      source_track_ids: [...new Set(pts.map((s) => s.source_track_id).filter((id): id is number => id != null))],
    };
  });

  const segments = buildV1Segments(rawSamples);
  const samples = buildV1Samples(rawSamples, segments, slotMap);

  return buildIndexed(samples, players, segments, DEFAULT_COURT_VISUAL_THEME_V1, null);
}

function flattenV1Players(players?: Record<string, RawPlayerRenderFrame[]>): RawPlayerRenderFrame[] {
  if (!players) return [];
  const result: RawPlayerRenderFrame[] = [];
  for (const [pid, samples] of Object.entries(players)) {
    for (const s of samples) {
      result.push({ ...s, player_id: pid });
    }
  }
  return result;
}

function classifySide(yFt: number): "near" | "far" | "unknown" {
  return yFt > 22 ? "far" : "near";
}

const MAX_VISIBLE_GAP_SECONDS = 0.75;
const MAX_DISTANCE_JUMP_FT = 9.84;

function buildV1Segments(
  samples: RawPlayerRenderFrame[],
): RenderSegmentMetadata[] {
  const byPlayer = new Map<string, RawPlayerRenderFrame[]>();
  for (const s of samples) {
    const list = byPlayer.get(s.player_id) ?? [];
    list.push(s);
    byPlayer.set(s.player_id, list);
  }

  const segments: RenderSegmentMetadata[] = [];
  for (const [pid, pts] of byPlayer) {
    pts.sort((a, b) => a.frame_index - b.frame_index);
    let segIndex = 0;
    let segStart = 0;
    for (let i = 1; i <= pts.length; i++) {
      const isGap = i < pts.length && (
        (pts[i].timestamp_seconds - pts[i - 1].timestamp_seconds > MAX_VISIBLE_GAP_SECONDS) ||
        (dist(pts[i - 1], pts[i]) > MAX_DISTANCE_JUMP_FT)
      );
      if (isGap || i === pts.length) {
        const segPts = pts.slice(segStart, i);
        const segId = `legacy:${pid}:e0:s${segIndex}`;
        segments.push({
          segment_id: segId,
          player_id: pid,
          identity_epoch: 0,
          start_frame_index: segPts[0].frame_index,
          end_frame_index: segPts[segPts.length - 1].frame_index,
          start_timestamp_seconds: segPts[0].timestamp_seconds,
          end_timestamp_seconds: segPts[segPts.length - 1].timestamp_seconds,
          break_before: segIndex === 0 ? "start" : "visible_gap",
          sample_count: segPts.length,
        });
        segIndex++;
        segStart = i;
      }
    }
  }
  return segments;
}

function buildV1Samples(
  samples: RawPlayerRenderFrame[],
  segments: RenderSegmentMetadata[],
  slotMap: Map<string, string>,
): NormalizedRenderFrame[] {
  const byPlayer = new Map<string, NormalizedRenderFrame[]>();
  for (const s of samples) {
    const ns: NormalizedRenderFrame = {
      sequence_index: 0,
      frame_index: s.frame_index,
      timestamp_seconds: s.timestamp_seconds,
      x_ft: s.x_ft,
      y_ft: s.y_ft,
      source: s.source,
      confidence: s.confidence ?? null,
      player_id: s.player_id,
      render_slot: slotMap.get(s.player_id) ?? "",
      side: classifySide(s.y_ft),
      segment_id: "",
      identity_epoch: s.identity_epoch ?? 0,
      source_track_id: s.source_track_id ?? null,
      projection_status: s.projection_status ?? null,
      projection_confidence: s.projection_confidence ?? null,
      footpoint_method: s.footpoint_method ?? null,
    };
    const list = byPlayer.get(s.player_id) ?? [];
    list.push(ns);
    byPlayer.set(s.player_id, list);
  }

  for (const seg of segments) {
    const pts = byPlayer.get(seg.player_id) ?? [];
    pts.forEach((p) => {
      if (p.timestamp_seconds >= seg.start_timestamp_seconds - 0.001 && p.timestamp_seconds <= seg.end_timestamp_seconds + 0.001) {
        p.segment_id = seg.segment_id;
      }
    });
  }

  const result = byPlayer.values().next().value ? [...byPlayer.values()].flat() : [];
  result.forEach((s, i) => { s.sequence_index = i; });
  return result;
}

function dist(a: { x_ft: number; y_ft: number }, b: { x_ft: number; y_ft: number }): number {
  return Math.sqrt((b.x_ft - a.x_ft) ** 2 + (b.y_ft - a.y_ft) ** 2);
}

function buildIndexed(
  samples: NormalizedRenderFrame[],
  players: RenderPlayerMetadata[],
  segments: RenderSegmentMetadata[],
  style_profile: CourtVisualizationStyleProfile,
  segmentation_profile: { version: string; jump_threshold_ft: number; max_visible_gap_seconds: number } | null,
): NormalizedPlayerRenderTrajectory {
  const byPlayer: Record<string, NormalizedRenderFrame[]> = {};
  const bySegment: Record<string, NormalizedRenderFrame[]> = {};
  for (const s of samples) {
    (byPlayer[s.player_id] ??= []).push(s);
    if (s.segment_id) {
      (bySegment[s.segment_id] ??= []).push(s);
    }
  }
  return { players, segments, samples, style_profile, segmentation_profile, byPlayer, bySegment };
}
