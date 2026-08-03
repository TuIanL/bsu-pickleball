import type {
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  PipelineTrackPoint,
} from "../types/report";
import { canonicalPlayerNumber, formatPlayerId } from "../utils/analysisHelpers";

export type CourtUnit = "ft" | "m" | "unknown";

export interface HudPoint {
  x: number;
  y: number;
  timestampSeconds: number;
  confidence: number | null;
  interpolated: boolean;
  inBounds: boolean;
}

export interface HudPlayer {
  id: string;
  label: string;
  segments: HudPoint[][];
  latest: HudPoint | null;
  direction: { x: number; y: number } | null;
  speedMetersPerSecond: number | null;
  /** 最新有效点是否已落后当前播放时间超过新鲜度阈值（视为停滞/丢失） */
  stale: boolean;
}

export interface HudBounce {
  id: string;
  point: HudPoint;
  active: boolean;
}

export interface VideoOverlayHudData {
  players: HudPlayer[];
  ballSegments: HudPoint[][];
  ballLatest: HudPoint | null;
  bounces: HudBounce[];
  visiblePlayerCount: number;
  ballPointCount: number;
}

export interface VideoOverlayHudOptions {
  ballTrailSeconds?: number;
  bounceWindowSeconds?: number;
  courtLength?: number;
  courtUnit?: CourtUnit;
  courtWidth?: number;
  maxBallPoints?: number;
  maxGapSeconds?: number;
  maxPlayerPoints?: number;
  playerTrailSeconds?: number;
  /** 球员最新点落后当前播放时间超过该阈值即标记为停滞（秒） */
  staleThresholdSeconds?: number;
}

const DEFAULT_OPTIONS: Required<VideoOverlayHudOptions> = {
  ballTrailSeconds: 1.2,
  bounceWindowSeconds: 0.75,
  courtLength: 44,
  courtUnit: "ft",
  courtWidth: 20,
  maxBallPoints: 96,
  maxGapSeconds: 0.7,
  maxPlayerPoints: 120,
  playerTrailSeconds: 3,
  staleThresholdSeconds: 0.5,
};

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function validPoint(
  x: unknown,
  y: unknown,
  timestampSeconds: unknown,
  confidence: unknown,
  interpolated: boolean,
  courtWidth: number,
  courtLength: number,
): HudPoint | null {
  const validX = finiteNumber(x);
  const validY = finiteNumber(y);
  const validTimestamp = finiteNumber(timestampSeconds);
  if (validX === null || validY === null || validTimestamp === null) return null;

  return {
    x: validX,
    y: validY,
    timestampSeconds: validTimestamp,
    confidence: finiteNumber(confidence),
    interpolated,
    inBounds: validX >= 0 && validX <= courtWidth && validY >= 0 && validY <= courtLength,
  };
}

function sampleEvenly<T>(points: T[], maxPoints: number): T[] {
  if (points.length <= maxPoints || maxPoints < 2) return points.slice(0, Math.max(1, maxPoints));
  return Array.from({ length: maxPoints }, (_, index) => points[Math.round((index * (points.length - 1)) / (maxPoints - 1))]);
}

function splitAtGaps(points: HudPoint[], maxGapSeconds: number, maxPoints: number): HudPoint[][] {
  const segments: HudPoint[][] = [];
  let active: HudPoint[] = [];

  for (const point of points) {
    const previous = active.at(-1);
    if (previous && point.timestampSeconds - previous.timestampSeconds > maxGapSeconds) {
      if (active.length) segments.push(sampleEvenly(active, maxPoints));
      active = [];
    }
    active.push(point);
  }

  if (active.length) segments.push(sampleEvenly(active, maxPoints));
  return segments;
}

function latestSegmentPoint(segments: HudPoint[][]): HudPoint | null {
  return segments.at(-1)?.at(-1) ?? null;
}

function resolveMotion(
  segments: HudPoint[][],
  courtUnit: CourtUnit,
): Pick<HudPlayer, "direction" | "speedMetersPerSecond"> {
  const latestSegment = segments.at(-1) ?? [];
  if (latestSegment.length < 2) return { direction: null, speedMetersPerSecond: null };

  const latest = latestSegment.at(-1)!;
  const previous = latestSegment.at(-2)!;
  const duration = latest.timestampSeconds - previous.timestampSeconds;
  if (duration <= 0) return { direction: null, speedMetersPerSecond: null };

  const deltaX = latest.x - previous.x;
  const deltaY = latest.y - previous.y;
  const distance = Math.hypot(deltaX, deltaY);
  if (distance <= 0.01) return { direction: null, speedMetersPerSecond: 0 };

  const metersPerUnit = courtUnit === "ft" ? 0.3048 : courtUnit === "m" ? 1 : null;
  return {
    direction: { x: deltaX / distance, y: deltaY / distance },
    speedMetersPerSecond: metersPerUnit === null ? null : (distance / duration) * metersPerUnit,
  };
}

function playerKey(track: PipelineTrackPoint): string {
  return canonicalPlayerNumber(track.track_id)?.toString() ?? track.track_id ?? "unknown";
}

export function buildVideoOverlayHud(
  tracks: PipelineTrackPoint[] | null | undefined,
  ballTrajectory: BallTrajectoryArtifact | null | undefined,
  bounceEvents: BounceEventsArtifact | null | undefined,
  currentTimeSeconds: number,
  options: VideoOverlayHudOptions = {},
): VideoOverlayHudData {
  const config = { ...DEFAULT_OPTIONS, ...options };
  const currentTime = Number.isFinite(currentTimeSeconds) ? currentTimeSeconds : 0;
  const playerCutoff = currentTime - config.playerTrailSeconds;
  const ballCutoff = currentTime - config.ballTrailSeconds;
  const groupedPlayers = new Map<string, PipelineTrackPoint[]>();

  for (const track of tracks ?? []) {
    if (!track || !Number.isFinite(track.timestamp_seconds) || track.timestamp_seconds > currentTime || track.timestamp_seconds < playerCutoff) continue;
    const point = validPoint(
      track.court_point?.x,
      track.court_point?.y,
      track.timestamp_seconds,
      track.confidence,
      false,
      config.courtWidth,
      config.courtLength,
    );
    if (!point) continue;
    const key = playerKey(track);
    const values = groupedPlayers.get(key) ?? [];
    values.push(track);
    groupedPlayers.set(key, values);
  }

  const players = Array.from(groupedPlayers.entries())
    .map(([id, playerTracks]) => {
      const points = playerTracks
        .map((track) => validPoint(
          track.court_point?.x,
          track.court_point?.y,
          track.timestamp_seconds,
          track.confidence,
          false,
          config.courtWidth,
          config.courtLength,
        ))
        .filter((point): point is HudPoint => point !== null)
        .sort((left, right) => left.timestampSeconds - right.timestampSeconds);
      const segments = splitAtGaps(points, config.maxGapSeconds, config.maxPlayerPoints);
      const sourceId = playerTracks[0]?.track_id ?? id;
      const latest = latestSegmentPoint(segments);
      return {
        id,
        label: formatPlayerId(sourceId) || "球员",
        segments,
        latest,
        stale: latest !== null && latest.timestampSeconds < currentTime - config.staleThresholdSeconds,
        ...resolveMotion(segments, config.courtUnit),
      };
    })
    .filter((player) => player.latest !== null)
    .sort((left, right) => left.label.localeCompare(right.label, "en"));

  const ballPoints = (ballTrajectory?.samples ?? [])
    .filter((sample) => sample.image_xy && (sample.accepted ?? true))
    .map((sample) => validPoint(
      sample.court_xy?.[0],
      sample.court_xy?.[1],
      sample.timestamp_sec,
      sample.confidence,
      sample.interpolated === true,
      config.courtWidth,
      config.courtLength,
    ))
    .filter((point): point is HudPoint => point !== null)
    .filter((point) => point.timestampSeconds <= currentTime && point.timestampSeconds >= ballCutoff)
    .sort((left, right) => left.timestampSeconds - right.timestampSeconds);
  const ballSegments = splitAtGaps(ballPoints, config.maxGapSeconds, config.maxBallPoints);

  const bounces = (bounceEvents?.events ?? [])
    .map((event) => {
      const point = validPoint(
        event.court_xy?.[0],
        event.court_xy?.[1],
        event.timestamp_sec,
        event.confidence,
        false,
        config.courtWidth,
        config.courtLength,
      );
      if (!point) return null;
      return {
        id: event.event_id,
        point,
        active: Math.abs(point.timestampSeconds - currentTime) <= config.bounceWindowSeconds,
      };
    })
    .filter((bounce): bounce is HudBounce => bounce !== null)
    .filter((bounce) => bounce.point.timestampSeconds <= currentTime && bounce.point.timestampSeconds >= ballCutoff - config.bounceWindowSeconds);

  return {
    players,
    ballSegments,
    ballLatest: latestSegmentPoint(ballSegments),
    bounces,
    visiblePlayerCount: players.length,
    ballPointCount: ballPoints.length,
  };
}
