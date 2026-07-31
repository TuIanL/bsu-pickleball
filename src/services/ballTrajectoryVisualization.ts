import type { BallTrajectoryArtifact, BallTrajectorySample, BounceEventsArtifact } from "../types/report";

export const PICKLEBALL_COURT_WIDTH_FT = 20;
export const PICKLEBALL_COURT_LENGTH_FT = 44;

export type TrajectoryDirection = "near-to-far" | "far-to-near";

export interface EstimatedTrajectoryPoint {
  frameIndex: number;
  timestampSeconds: number;
  courtXFt: number;
  courtYFt: number;
  estimatedHeightFt: number;
  confidence: number | null;
  interpolated: boolean;
  heightSource: "estimated";
}

export interface EstimatedBallTrajectory {
  id: string;
  sequence: number;
  direction: TrajectoryDirection;
  startTimeSeconds: number;
  endTimeSeconds: number;
  durationSeconds: number;
  pointCount: number;
  averageConfidence: number | null;
  interpolatedRatio: number;
  highConfidence: boolean;
  peakEstimatedHeightFt: number;
  points: EstimatedTrajectoryPoint[];
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
        heightSource: "estimated" as const,
      };
    }),
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
  };
}

