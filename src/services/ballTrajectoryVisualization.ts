import type {
  BallTrajectoryArtifact,
  BallTrajectorySample,
  BounceEventsArtifact,
  PlayerRosterEntry,
  ReconstructedBallTrajectoryArtifact,
  ReconstructedBallTrajectorySample,
  ReconstructedBallTrajectorySegment,
  ShotOwnershipStatus,
} from "../types/report";

export const PICKLEBALL_COURT_WIDTH_FT = 20;
export const PICKLEBALL_COURT_LENGTH_FT = 44;

export type TrajectoryDirection = "near-to-far" | "far-to-near";

export type TrajectoryPointSource = "detected" | "interpolated" | "model_predicted" | "anchor";

export interface EstimatedTrajectoryPoint {
  frameIndex: number;
  timestampSeconds: number;
  courtXFt: number;
  courtYFt: number;
  estimatedHeightFt: number | null;
  confidence: number | null;
  interpolated: boolean;
  heightSource: string | null;
  source: TrajectoryPointSource;
}

export interface TrajectoryAnchorMarker {
  anchorType: "bounce" | "contact" | "raw_endpoint" | "loss";
  courtXFt: number;
  courtYFt: number;
  frameIndex: number;
  confidence: number;
  timestampSeconds?: number | null;
  outcomeClassification?: string | null;
  notice?: string | null;
}

export interface TrajectoryQualitySummary {
  overall: number | null;
  displayLevel: "high" | "medium" | "low" | "none" | null;
  netCrossingStatus: string | null;
  observationCoverage: number | null;
}

export interface EstimatedBallTrajectory {
  id: string;                       // 后端 segment_id（稳定标识）
  sequence: number;
  direction: TrajectoryDirection;
  startTimeSeconds: number;
  endTimeSeconds: number;
  durationSeconds: number;
  pointCount: number;
  averageConfidence: number | null;
  interpolatedRatio: number;
  highConfidence: boolean;
  peakEstimatedHeightFt: number | null;
  points: EstimatedTrajectoryPoint[];
  anchors?: TrajectoryAnchorMarker[];
  quality?: TrajectoryQualitySummary;
  reconstructionMode?: string;
  metricValidity?: string | null;
  metricEligibility?: {
    speed: boolean;
    peakHeight: boolean;
    authoritativeLanding: boolean;
    reason: string | null;
  };
  primaryViewId?: string | null;
  primaryViewReason?: string | null;
  endpointOutcome?: string | null;
  endpointNotice?: string | null;
  shotId: string | null;
  hitterPlayerId: string | null;
  hitterRenderSlot: string | null;
  ownershipStatus: ShotOwnershipStatus;
  ownershipConfidence: number | null;
}

export interface EstimatedBallShot {
  shotId: string;
  hitterPlayerId: string | null;
  hitterRenderSlot: string | null;
  ownershipStatus: ShotOwnershipStatus;
  ownershipConfidence: number | null;
  segmentIds: string[];
  segments: EstimatedBallTrajectory[];
  startTimeSeconds: number;
  endTimeSeconds: number;
  durationSeconds: number;
  pointCount: number;
  sequence: number;
}

export interface TrajectoryBounceMarker {
  id: string;
  timestampSeconds: number;
  courtXFt: number;
  courtYFt: number;
  confidence: number;
}

export interface BallTrajectoryVisualizationData {
  trajectories: EstimatedBallTrajectory[];
  bounces: TrajectoryBounceMarker[];
  discardedPointCount: number;
  shots: EstimatedBallShot[];
  playerRoster: PlayerRosterEntry[];
}

export interface TrajectoryBuildOptions {
  maxGapSeconds?: number;
  maxPlanarJumpFt?: number;
  maxPointsPerTrajectory?: number;
  minPointsPerTrajectory?: number;
  boundsPaddingFt?: number;
}

interface ValidPoint {
  frameIndex: number;
  timestampSeconds: number;
  courtXFt: number;
  courtYFt: number;
  confidence: number | null;
  interpolated: boolean;
}

const DEFAULT_OPTIONS: Required<TrajectoryBuildOptions> = {
  maxGapSeconds: 0.55,
  maxPlanarJumpFt: 12,
  maxPointsPerTrajectory: 96,
  minPointsPerTrajectory: 3,
  boundsPaddingFt: 4,
};

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function validCourtPoint(sample: BallTrajectorySample, boundsPaddingFt: number): ValidPoint | null {
  const timestampSeconds = finiteNumber(sample.timestamp_sec);
  const frameIndex = finiteNumber(sample.frame_index);
  const x = finiteNumber(sample.court_xy?.[0]);
  const y = finiteNumber(sample.court_xy?.[1]);
  if (timestampSeconds === null || frameIndex === null || x === null || y === null) return null;
  if (
    x < -boundsPaddingFt ||
    x > PICKLEBALL_COURT_WIDTH_FT + boundsPaddingFt ||
    y < -boundsPaddingFt ||
    y > PICKLEBALL_COURT_LENGTH_FT + boundsPaddingFt
  ) {
    return null;
  }

  return {
    frameIndex,
    timestampSeconds,
    courtXFt: x,
    courtYFt: y,
    confidence: finiteNumber(sample.confidence),
    interpolated: sample.interpolated === true,
  };
}

function planarDistance(a: ValidPoint, b: ValidPoint): number {
  return Math.hypot(b.courtXFt - a.courtXFt, b.courtYFt - a.courtYFt);
}

function sampleEvenly(points: ValidPoint[], maxPoints: number): ValidPoint[] {
  if (points.length <= maxPoints) return points;
  const sampled: ValidPoint[] = [];
  for (let index = 0; index < maxPoints; index += 1) {
    sampled.push(points[Math.round((index * (points.length - 1)) / (maxPoints - 1))]);
  }
  return sampled;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function estimatedPeakHeight(points: ValidPoint[]): number {
  const first = points[0];
  const last = points[points.length - 1];
  const duration = Math.max(0, last.timestampSeconds - first.timestampSeconds);
  return clamp(2.4 + planarDistance(first, last) * 0.12 + duration * 0.65, 2.4, 8.5);
}

function buildTrajectory(points: ValidPoint[], sequence: number, maxPoints: number): EstimatedBallTrajectory {
  const sampled = sampleEvenly(points, maxPoints);
  const first = sampled[0];
  const last = sampled[sampled.length - 1];
  const duration = Math.max(0, last.timestampSeconds - first.timestampSeconds);
  const peakEstimatedHeightFt = estimatedPeakHeight(sampled);
  const confidenceValues = sampled.flatMap((point) => point.confidence === null ? [] : [point.confidence]);
  const averageConfidence = confidenceValues.length
    ? confidenceValues.reduce((total, value) => total + value, 0) / confidenceValues.length
    : null;
  const interpolatedRatio = sampled.filter((point) => point.interpolated).length / sampled.length;
  const direction: TrajectoryDirection = last.courtYFt >= first.courtYFt ? "near-to-far" : "far-to-near";

  return {
    id: `trajectory-${sequence}`,
    sequence,
    direction,
    startTimeSeconds: first.timestampSeconds,
    endTimeSeconds: last.timestampSeconds,
    durationSeconds: duration,
    pointCount: points.length,
    averageConfidence,
    interpolatedRatio,
    highConfidence: averageConfidence !== null && averageConfidence >= 0.65 && interpolatedRatio <= 0.35,
    peakEstimatedHeightFt,
    points: sampled.map((point, index) => {
      const progress = duration > 0
        ? clamp((point.timestampSeconds - first.timestampSeconds) / duration, 0, 1)
        : index / Math.max(1, sampled.length - 1);
      return {
        ...point,
        estimatedHeightFt: 4 * peakEstimatedHeightFt * progress * (1 - progress),
        heightSource: "estimated",
        source: (point.interpolated ? "interpolated" : "detected") as TrajectoryPointSource,
      };
    }),
    shotId: null,
    hitterPlayerId: null,
    hitterRenderSlot: null,
    ownershipStatus: "not_applicable",
    ownershipConfidence: null,
  };
}

function buildBounceMarkers(artifact?: BounceEventsArtifact | null): TrajectoryBounceMarker[] {
  if (!artifact) return [];
  return artifact.events.flatMap((event) => {
    const x = finiteNumber(event.court_xy?.[0]);
    const y = finiteNumber(event.court_xy?.[1]);
    const timestampSeconds = finiteNumber(event.timestamp_sec);
    const confidence = finiteNumber(event.confidence);
    if (x === null || y === null || timestampSeconds === null || confidence === null) return [];
    if (x < 0 || x > PICKLEBALL_COURT_WIDTH_FT || y < 0 || y > PICKLEBALL_COURT_LENGTH_FT) return [];
    return [{
      id: event.event_id,
      timestampSeconds,
      courtXFt: x,
      courtYFt: y,
      confidence,
    }];
  });
}

/**
 * 遗留构建器：从原始/清洗球轨迹自行分段 + 估算高度弧线。
 *
 * 仅用于降级路径（任务没有重建产物时回退旧渲染），或已归档任务旧产物展示。
 * 正式渲染请使用 buildReconstructedBallTrajectoryVisualization —— 本函数
 * 保留的前端分段 / 方向 / 平均置信度 / 高度生成逻辑不再用于重建产物。
 */
export function buildBallTrajectoryVisualization(
  artifact?: BallTrajectoryArtifact | null,
  bounceArtifact?: BounceEventsArtifact | null,
  options: TrajectoryBuildOptions = {},
): BallTrajectoryVisualizationData {
  const resolved = { ...DEFAULT_OPTIONS, ...options };
  const samples = artifact?.samples ?? [];
  const validPoints = samples
    .map((sample) => validCourtPoint(sample, resolved.boundsPaddingFt))
    .filter((point): point is ValidPoint => point !== null)
    .sort((a, b) => a.timestampSeconds - b.timestampSeconds || a.frameIndex - b.frameIndex);

  const segments: ValidPoint[][] = [];
  let active: ValidPoint[] = [];
  for (const point of validPoints) {
    const previous = active.at(-1);
    const shouldSplit = previous !== undefined && (
      point.timestampSeconds - previous.timestampSeconds > resolved.maxGapSeconds ||
      planarDistance(previous, point) > resolved.maxPlanarJumpFt
    );
    if (shouldSplit) {
      if (active.length >= resolved.minPointsPerTrajectory) segments.push(active);
      active = [];
    }
    active.push(point);
  }
  if (active.length >= resolved.minPointsPerTrajectory) segments.push(active);

  return {
    trajectories: segments.map((segment, index) => buildTrajectory(segment, index + 1, resolved.maxPointsPerTrajectory)),
    bounces: buildBounceMarkers(bounceArtifact),
    discardedPointCount: samples.length - validPoints.length,
    shots: [],
    playerRoster: [],
  };
}

// ---- 事件切分重建球轨迹：主渲染路径（前端不自行分段 / 估高） ----

function isDisplayableSegment(segment: ReconstructedBallTrajectorySegment): boolean {
  if (segment.status === "insufficient_spatial_anchors") return false;
  if (segment.reconstruction_mode === "image_only" || segment.reconstruction_mode === "unavailable") return false;
  if (segment.status === "unavailable" || segment.status === "UNAVAILABLE") return false;
  const displayLevel = segment.display_level ?? segment.quality?.display_level;
  if (displayLevel === "none") return false;
  if (displayLevel === "low" && segment.reconstruction_mode !== "single_view_visual_arc") return false;
  // 环境离群证据仅保留给 diagnostics，不进入正式曲线。
  if (segment.end_endpoint?.outcome_classification === "environment_outlier") return false;
  return segment.samples.some((sample) => finiteNumber(sample.court_xy?.[0]) !== null && finiteNumber(sample.court_xy?.[1]) !== null);
}

function buildReconstructedTrajectory(
  segment: ReconstructedBallTrajectorySegment,
  sequence: number,
): EstimatedBallTrajectory {
  const points: EstimatedTrajectoryPoint[] = segment.samples.flatMap((sample, sampleIndex) => {
    const raw = sample as ReconstructedBallTrajectorySample & {
      x_ft?: number;
      y_ft?: number;
      z_ft?: number;
      t_sec?: number;
    };
    if (raw.validity === "invalid") return [];
    const x = finiteNumber(raw.court_xy?.[0] ?? raw.x_ft);
    const y = finiteNumber(raw.court_xy?.[1] ?? raw.y_ft);
    const timestamp = finiteNumber(raw.timestamp_sec ?? raw.t_sec);
    const frameIndex = finiteNumber(raw.frame_index ?? sampleIndex);
    if (x === null || y === null || timestamp === null || frameIndex === null) return [];
    const source = raw.source === "model_predicted" || raw.source === "predicted" || raw.provenance === "predicted"
      ? "model_predicted"
      : raw.source === "interpolated"
        ? "interpolated"
        : raw.source === "anchor"
          ? "anchor"
          : "detected";
    const estimatedHeight = finiteNumber(raw.estimated_height_ft ?? raw.z_ft);
    const interpolated = source === "interpolated" || source === "model_predicted";
    return [{
      frameIndex,
      timestampSeconds: timestamp,
      courtXFt: x,
      courtYFt: y,
      estimatedHeightFt: estimatedHeight,
      confidence: finiteNumber(raw.confidence),
      interpolated,
      heightSource: raw.height_source ?? null,
      source,
    }];
  });
  if (points.length === 0) {
    return emptyReconstructedTrajectory(segment, sequence);
  }

  const first = points[0];
  const last = points[points.length - 1];
  const duration = Math.max(0, last.timestampSeconds - first.timestampSeconds);
  const direction: TrajectoryDirection = last.courtYFt >= first.courtYFt ? "near-to-far" : "far-to-near";
  const heights = points.flatMap((point) => point.estimatedHeightFt === null ? [] : [point.estimatedHeightFt]);
  const peakEstimatedHeightFt = heights.length ? Math.max(...heights) : null;

  const quality = segment.quality;
  const displayLevel = quality?.display_level ?? null;
  const highConfidence = displayLevel === "high";

  const anchors: TrajectoryAnchorMarker[] = (segment.anchors ?? []).flatMap((anchor) => {
    const x = finiteNumber(anchor.court_xy?.[0]);
    const y = finiteNumber(anchor.court_xy?.[1]);
    if (x === null || y === null) return [];
    return [{
      anchorType: anchor.anchor_type,
      courtXFt: x,
      courtYFt: y,
      frameIndex: anchor.frame_index,
      confidence: anchor.confidence ?? 0,
    }];
  });
  for (const endpoint of [segment.start_endpoint, segment.end_endpoint]) {
    const x = finiteNumber(endpoint?.court_xy?.[0]);
    const y = finiteNumber(endpoint?.court_xy?.[1]);
    if (x === null || y === null || !endpoint) continue;
    const anchorType = endpoint.event_type === "bounce"
      ? "bounce"
      : endpoint.event_type === "hit" || endpoint.event_type === "serve_reset"
        ? "contact"
        : "loss";
    anchors.push({
      anchorType,
      courtXFt: x,
      courtYFt: y,
      frameIndex: 0,
      confidence: endpoint.confidence ?? 0,
      timestampSeconds: endpoint.timestamp_sec ?? null,
      outcomeClassification: endpoint.outcome_classification ?? null,
      notice: endpoint.non_adjudication_notice ?? null,
    });
  }

  return {
    id: segment.segment_id,
    sequence,
    direction,
    startTimeSeconds: first.timestampSeconds,
    endTimeSeconds: last.timestampSeconds,
    durationSeconds: duration,
    pointCount: points.length,
    averageConfidence: quality?.detection_score ?? null,
    interpolatedRatio: quality?.predicted_ratio ?? points.filter((point) => point.interpolated).length / points.length,
    highConfidence,
    peakEstimatedHeightFt,
    points,
    anchors,
    quality: {
      overall: finiteNumber(quality?.overall),
      displayLevel,
      netCrossingStatus: quality?.net_crossing_status ?? null,
      observationCoverage: finiteNumber(quality?.observation_coverage),
    },
    reconstructionMode: segment.reconstruction_mode,
    metricValidity: segment.metric_validity ?? segment.quality?.metric_validity ?? null,
    metricEligibility: {
      speed: segment.metric_eligibility?.speed === true,
      peakHeight: segment.metric_eligibility?.peak_height === true,
      authoritativeLanding: segment.metric_eligibility?.authoritative_landing === true,
      reason: segment.metric_eligibility?.reason ?? null,
    },
    primaryViewId: segment.primary_view_id ?? null,
    primaryViewReason: segment.primary_view_reason ?? null,
    endpointOutcome: segment.end_endpoint?.outcome_classification ?? null,
    endpointNotice: segment.end_endpoint?.non_adjudication_notice ?? null,
    shotId: segment.shot_id ?? null,
    hitterPlayerId: segment.hitter_player_id ?? null,
    hitterRenderSlot: segment.hitter_render_slot ?? null,
    ownershipStatus: segment.ownership_status ?? "not_applicable",
    ownershipConfidence: finiteNumber(segment.ownership_confidence),
  };
}

function emptyReconstructedTrajectory(segment: ReconstructedBallTrajectorySegment, sequence: number): EstimatedBallTrajectory {
  return {
    id: segment.segment_id,
    sequence,
    direction: "near-to-far",
    startTimeSeconds: 0,
    endTimeSeconds: 0,
    durationSeconds: 0,
    pointCount: 0,
    averageConfidence: null,
    interpolatedRatio: 0,
    highConfidence: false,
    peakEstimatedHeightFt: null,
    points: [],
    anchors: [],
    reconstructionMode: segment.reconstruction_mode,
    metricValidity: segment.metric_validity ?? null,
    primaryViewId: segment.primary_view_id ?? null,
    primaryViewReason: segment.primary_view_reason ?? null,
    endpointOutcome: segment.end_endpoint?.outcome_classification ?? null,
    endpointNotice: segment.end_endpoint?.non_adjudication_notice ?? null,
    shotId: segment.shot_id ?? null,
    hitterPlayerId: segment.hitter_player_id ?? null,
    hitterRenderSlot: segment.hitter_render_slot ?? null,
    ownershipStatus: segment.ownership_status ?? "not_applicable",
    ownershipConfidence: finiteNumber(segment.ownership_confidence),
  };
}

function buildReconstructedBounceMarkers(segments: ReconstructedBallTrajectorySegment[]): TrajectoryBounceMarker[] {
  const markers: TrajectoryBounceMarker[] = [];
  for (const segment of segments) {
    for (const anchor of segment.anchors ?? []) {
      if (anchor.anchor_type !== "bounce") continue;
      const x = finiteNumber(anchor.court_xy?.[0]);
      const y = finiteNumber(anchor.court_xy?.[1]);
      if (x === null || y === null) continue;
      markers.push({
        id: anchor.anchor_id,
        timestampSeconds: 0,
        courtXFt: x,
        courtYFt: y,
        confidence: anchor.confidence ?? 0,
      });
    }
    const endpoint = segment.end_endpoint;
    if (endpoint?.event_type === "bounce" && endpoint.outcome_classification !== "environment_outlier") {
      const x = finiteNumber(endpoint.court_xy?.[0]);
      const y = finiteNumber(endpoint.court_xy?.[1]);
      const timestampSeconds = finiteNumber(endpoint.timestamp_sec);
      if (x !== null && y !== null && timestampSeconds !== null) {
        markers.push({
          id: endpoint.event_id ?? `${segment.segment_id}-bounce`,
          timestampSeconds,
          courtXFt: x,
          courtYFt: y,
          confidence: endpoint.confidence ?? 0,
        });
      }
    }
  }
  return markers;
}

/**
 * 按后端 `shot_id` 聚合飞行段为 Shot 视图模型（I5：筛选、选中、统计以 shot 为单位）。
 * `shotId = null` 的段不进入任何 Shot（孤立段，单独归类）。
 */
export function buildShots(trajectories: EstimatedBallTrajectory[]): EstimatedBallShot[] {
  const byShot = new Map<string, EstimatedBallTrajectory[]>();
  for (const trajectory of trajectories) {
    if (trajectory.shotId === null) continue;
    const bucket = byShot.get(trajectory.shotId) ?? [];
    bucket.push(trajectory);
    byShot.set(trajectory.shotId, bucket);
  }
  const shots: EstimatedBallShot[] = [];
  for (const [shotId, segments] of byShot) {
    const sorted = [...segments].sort((a, b) => a.startTimeSeconds - b.startTimeSeconds);
    const first = sorted[0];
    const last = sorted[sorted.length - 1];
    const hitter = sorted.find((segment) => segment.hitterPlayerId !== null) ?? first;
    shots.push({
      shotId,
      hitterPlayerId: hitter.hitterPlayerId,
      hitterRenderSlot: hitter.hitterRenderSlot,
      ownershipStatus: hitter.ownershipStatus,
      ownershipConfidence: hitter.ownershipConfidence,
      segmentIds: sorted.map((segment) => segment.id),
      segments: sorted,
      startTimeSeconds: first.startTimeSeconds,
      endTimeSeconds: last.endTimeSeconds,
      durationSeconds: Math.max(0, last.endTimeSeconds - first.startTimeSeconds),
      pointCount: sorted.reduce((total, segment) => total + segment.pointCount, 0),
      sequence: 0,
    });
  }
  shots.sort((a, b) => a.startTimeSeconds - b.startTimeSeconds);
  shots.forEach((shot, index) => { shot.sequence = index + 1; });
  return shots;
}

export interface TrajectoryFilterOptions {
  playerFilter: "all" | "unassigned" | string;
  confidence: ConfidenceFilterLike;
  displayLimit: number | "all";
}

type ConfidenceFilterLike = "all" | "high";

function matchesPlayerFilter(trajectory: EstimatedBallTrajectory, playerFilter: TrajectoryFilterOptions["playerFilter"]): boolean {
  if (playerFilter === "all") return true;
  if (playerFilter === "unassigned") {
    return trajectory.shotId === null || trajectory.ownershipStatus === "ambiguous" || trajectory.ownershipStatus === "unassigned";
  }
  return trajectory.hitterPlayerId === playerFilter;
}

function shotMatchesPlayerFilter(shot: EstimatedBallShot, playerFilter: TrajectoryFilterOptions["playerFilter"]): boolean {
  if (playerFilter === "all") return true;
  if (playerFilter === "unassigned") {
    return shot.ownershipStatus === "ambiguous" || shot.ownershipStatus === "unassigned";
  }
  return shot.hitterPlayerId === playerFilter;
}

/**
 * 筛选顺序（不变量 I5）：球员归属 → 可信度 → 最近 N 条限制。
 */
export function filterTrajectories(
  trajectories: EstimatedBallTrajectory[],
  shots: EstimatedBallShot[],
  options: TrajectoryFilterOptions,
): { trajectories: EstimatedBallTrajectory[]; shots: EstimatedBallShot[] } {
  const playerFiltered = trajectories.filter((trajectory) => matchesPlayerFilter(trajectory, options.playerFilter));
  const confidenceFiltered = playerFiltered.filter((trajectory) => options.confidence === "all" || trajectory.highConfidence);
  const limited = options.displayLimit === "all" ? confidenceFiltered : confidenceFiltered.slice(-options.displayLimit);

  const shotFiltered = shots.filter((shot) => shotMatchesPlayerFilter(shot, options.playerFilter))
    .filter((shot) => options.confidence === "all" || shot.segments.some((segment) => segment.highConfidence));
  const shotLimited = options.displayLimit === "all" ? shotFiltered : shotFiltered.slice(-options.displayLimit);

  return { trajectories: limited, shots: shotLimited };
}

/**
 * 主渲染路径：直接消费后端重建产物，按段构造轨迹。
 * 不进行前端分段、方向生成、平均置信度合成或高度生成；
 * 高度与质量均来自后端重建结果。
 */
export function buildReconstructedBallTrajectoryVisualization(
  artifact?: ReconstructedBallTrajectoryArtifact | null,
): BallTrajectoryVisualizationData {
  const schemaMajor = Number(artifact?.schema_version.match(/\.v(\d+)$/)?.[1] ?? 0);
  const displayAvailable = schemaMajor >= 4
    ? artifact?.display_trajectory_status !== "unavailable"
    : artifact ? ["available", "partial"].includes(artifact.status) : false;
  if (!artifact || !displayAvailable || artifact.segments.length === 0) {
    return { trajectories: [], bounces: [], discardedPointCount: 0, shots: [], playerRoster: [] };
  }
  const segments = artifact.segments.filter(isDisplayableSegment);
  const trajectories = segments.map((segment, index) => buildReconstructedTrajectory(segment, index + 1))
    .filter((trajectory) => trajectory.pointCount > 0);
  return {
    trajectories,
    bounces: buildReconstructedBounceMarkers(segments),
    discardedPointCount: 0,
    shots: buildShots(trajectories),
    playerRoster: artifact.player_roster ?? [],
  };
}
