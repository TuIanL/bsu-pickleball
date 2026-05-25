import type { PipelineTrackPoint } from "../types/report";

const DEFAULT_MAX_RENDERED_POINTS = 96;
const DEFAULT_MIN_PERSISTENT_POINTS = 12;
const DEFAULT_MIN_PERSISTENT_SECONDS = 1.2;

const TRACK_COLORS = ["#2F80ED", "#FF9500", "#168A34", "#E11D48", "#0891B2", "#7C3AED", "#B45309", "#0F766E"];

export interface CourtTrackBounds {
  maxX: number;
  maxY: number;
  minX: number;
  minY: number;
}

export interface CourtTrackSummary {
  averageConfidence: number | null;
  bounds: CourtTrackBounds;
  color: string;
  durationSeconds: number | null;
  endTimeSeconds: number | null;
  firstFrameIndex: number;
  isShortFragment: boolean;
  label: string;
  latestFrameIndex: number;
  latestPoint: PipelineTrackPoint;
  persistenceScore: number;
  pointCount: number;
  points: PipelineTrackPoint[];
  sampledPoints: PipelineTrackPoint[];
  startPoint: PipelineTrackPoint;
  startTimeSeconds: number | null;
  trackId: string;
}

interface BuildCourtTrackSummariesOptions {
  maxRenderedPointsPerTrack?: number;
  minPersistentPoints?: number;
  minPersistentSeconds?: number;
}

export function buildCourtTrackSummaries(points: PipelineTrackPoint[], options: BuildCourtTrackSummariesOptions = {}): CourtTrackSummary[] {
  const maxRenderedPointsPerTrack = options.maxRenderedPointsPerTrack ?? DEFAULT_MAX_RENDERED_POINTS;
  const minPersistentPoints = options.minPersistentPoints ?? DEFAULT_MIN_PERSISTENT_POINTS;
  const minPersistentSeconds = options.minPersistentSeconds ?? DEFAULT_MIN_PERSISTENT_SECONDS;
  const grouped = new Map<string, PipelineTrackPoint[]>();

  points.forEach((point) => {
    if (!hasRenderableCourtPoint(point)) {
      return;
    }

    const trackId = String(point.track_id);
    const bucket = grouped.get(trackId) ?? [];
    bucket.push(point);
    grouped.set(trackId, bucket);
  });

  return Array.from(grouped.entries())
    .map(([trackId, trackPoints]) =>
      summarizeTrack(trackId, trackPoints, {
        maxRenderedPointsPerTrack,
        minPersistentPoints,
        minPersistentSeconds,
      })
    )
    .sort((left, right) => {
      const scoreDelta = right.persistenceScore - left.persistenceScore;
      if (scoreDelta !== 0) {
        return scoreDelta;
      }
      return compareOptionalNumbers(left.startTimeSeconds, right.startTimeSeconds) || left.trackId.localeCompare(right.trackId);
    })
    .map((summary, index) => ({
      ...summary,
      color: TRACK_COLORS[index % TRACK_COLORS.length],
      label: `轨迹 ${index + 1}`,
    }));
}

export function sampleTrackPoints(points: PipelineTrackPoint[], maxPoints = DEFAULT_MAX_RENDERED_POINTS): PipelineTrackPoint[] {
  if (maxPoints <= 0 || points.length === 0) {
    return [];
  }

  const sorted = [...points].sort(compareTrackPoints);
  if (sorted.length <= maxPoints) {
    return sorted;
  }

  if (maxPoints === 1) {
    return [sorted[0]];
  }

  const lastIndex = sorted.length - 1;
  const step = lastIndex / (maxPoints - 1);
  const selectedIndices = new Set<number>([0, lastIndex]);

  for (let index = 1; index < maxPoints - 1; index += 1) {
    selectedIndices.add(Math.round(index * step));
  }

  return Array.from(selectedIndices)
    .sort((left, right) => left - right)
    .map((index) => sorted[index]);
}

function summarizeTrack(
  trackId: string,
  points: PipelineTrackPoint[],
  options: Required<BuildCourtTrackSummariesOptions>
): CourtTrackSummary {
  const sortedPoints = [...points].sort(compareTrackPoints);
  const startPoint = sortedPoints[0];
  const latestPoint = sortedPoints[sortedPoints.length - 1];
  const timestamps = sortedPoints.map((point) => point.timestamp_seconds).filter(isFiniteNumber);
  const confidences = sortedPoints.map((point) => point.confidence).filter(isFiniteNumber);
  const startTimeSeconds = timestamps.length > 0 ? Math.min(...timestamps) : null;
  const endTimeSeconds = timestamps.length > 0 ? Math.max(...timestamps) : null;
  const durationSeconds = startTimeSeconds !== null && endTimeSeconds !== null ? Math.max(0, endTimeSeconds - startTimeSeconds) : null;
  const averageConfidence = confidences.length > 0 ? confidences.reduce((total, value) => total + value, 0) / confidences.length : null;
  const bounds = getCourtBounds(sortedPoints);
  const durationScore = durationSeconds ?? 0;
  const confidenceScore = averageConfidence ?? 0;
  const persistenceScore = sortedPoints.length + durationScore * 5 + confidenceScore * 20;
  const isShortFragment =
    sortedPoints.length < options.minPersistentPoints || (durationSeconds !== null && durationSeconds < options.minPersistentSeconds);

  return {
    averageConfidence,
    bounds,
    color: TRACK_COLORS[0],
    durationSeconds,
    endTimeSeconds,
    firstFrameIndex: startPoint.frame_index,
    isShortFragment,
    label: trackId,
    latestFrameIndex: latestPoint.frame_index,
    latestPoint,
    persistenceScore,
    pointCount: sortedPoints.length,
    points: sortedPoints,
    sampledPoints: sampleTrackPoints(sortedPoints, options.maxRenderedPointsPerTrack),
    startPoint,
    startTimeSeconds,
    trackId,
  };
}

function getCourtBounds(points: PipelineTrackPoint[]): CourtTrackBounds {
  return points.reduce<CourtTrackBounds>(
    (bounds, point) => ({
      maxX: Math.max(bounds.maxX, point.court_point.x),
      maxY: Math.max(bounds.maxY, point.court_point.y),
      minX: Math.min(bounds.minX, point.court_point.x),
      minY: Math.min(bounds.minY, point.court_point.y),
    }),
    {
      maxX: Number.NEGATIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
      minX: Number.POSITIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
    }
  );
}

function compareTrackPoints(left: PipelineTrackPoint, right: PipelineTrackPoint) {
  return compareOptionalNumbers(left.timestamp_seconds, right.timestamp_seconds) || compareOptionalNumbers(left.frame_index, right.frame_index);
}

function compareOptionalNumbers(left: number | null | undefined, right: number | null | undefined) {
  const leftValid = isFiniteNumber(left);
  const rightValid = isFiniteNumber(right);

  if (leftValid && rightValid) {
    return left - right;
  }
  if (leftValid) {
    return -1;
  }
  if (rightValid) {
    return 1;
  }
  return 0;
}

function hasRenderableCourtPoint(point: PipelineTrackPoint) {
  return isFiniteNumber(point.court_point?.x) && isFiniteNumber(point.court_point?.y) && String(point.track_id).length > 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
