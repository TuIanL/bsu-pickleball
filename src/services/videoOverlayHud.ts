import type {
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  FusedPlayerOverlayFrame,
  PipelineTrackPoint,
  ReconstructedBallTrajectoryArtifact,
  ReconstructedBallTrajectorySegment,
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
  /** 用于跨视频框/小地图一致着色的稳定身份 ID。 */
  playerId: string;
  label: string;
  segments: HudPoint[][];
  latest: HudPoint | null;
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
  /** 球员轨迹连续两点位移超过该值（英尺）即断开 segment，避免身份跳变产生虚假连线 */
  maxTrailJumpFt?: number;
  /** 球员最新点落后当前播放时间超过该阈值即标记为停滞（秒） */
  staleThresholdSeconds?: number;
  /**
   * joint 模式展示权威：fused overlay 逐帧实体。其 `canonical_court_position_ft` 携带
   * 启动 bootstrap 回填的真实观测，并入 minimap 后可消除「前 1~2 秒小地图为空」。
   * 单摄模式（frames 为空）时忽略，回退到 pipelineTracks。
   */
  overlayFrames?: FusedPlayerOverlayFrame[];
  /** 优先用于小地图的分段重建球路（canonical court-space）。 */
  reconstructedBallTrajectory?: ReconstructedBallTrajectoryArtifact | null;
  /** 完整分段结束后在 HUD 中保留的秒数，与视频叠加层一致。 */
  reconstructedBallRetentionSeconds?: number;
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
  maxTrailJumpFt: 6,
  staleThresholdSeconds: 0.5,
  overlayFrames: [],
  reconstructedBallTrajectory: null,
  reconstructedBallRetentionSeconds: 0.8,
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

function splitAtGaps(
  points: HudPoint[],
  maxGapSeconds: number,
  maxPoints: number,
  maxDisplacementFt = Infinity,
): HudPoint[][] {
  const segments: HudPoint[][] = [];
  let active: HudPoint[] = [];

  for (const point of points) {
    const previous = active.at(-1);
    const timeGapTooLarge = previous !== undefined && point.timestampSeconds - previous.timestampSeconds > maxGapSeconds;
    const jumpTooLarge = previous !== undefined && Math.hypot(point.x - previous.x, point.y - previous.y) > maxDisplacementFt;
    if (previous && (timeGapTooLarge || jumpTooLarge)) {
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

function resolveSpeed(
  segments: HudPoint[][],
  courtUnit: CourtUnit,
): { speedMetersPerSecond: number | null } {
  const latestSegment = segments.at(-1) ?? [];
  if (latestSegment.length < 2) return { speedMetersPerSecond: null };

  const latest = latestSegment.at(-1)!;
  const previous = latestSegment.at(-2)!;
  const duration = latest.timestampSeconds - previous.timestampSeconds;
  if (duration <= 0) return { speedMetersPerSecond: null };

  const deltaX = latest.x - previous.x;
  const deltaY = latest.y - previous.y;
  const distance = Math.hypot(deltaX, deltaY);
  if (distance <= 0.01) return { speedMetersPerSecond: 0 };

  const metersPerUnit = courtUnit === "ft" ? 0.3048 : courtUnit === "m" ? 1 : null;
  return {
    speedMetersPerSecond: metersPerUnit === null ? null : (distance / duration) * metersPerUnit,
  };
}

function playerKey(track: PipelineTrackPoint): string {
  return canonicalPlayerNumber(track.track_id)?.toString() ?? track.track_id ?? "unknown";
}

function isDisplayableReconstructedSegment(segment: ReconstructedBallTrajectorySegment): boolean {
  if (segment.status === "unavailable" || segment.status === "UNAVAILABLE" || segment.status === "insufficient_spatial_anchors") return false;
  if (segment.reconstruction_mode === "unavailable" || segment.reconstruction_mode === "image_only") return false;
  if (segment.display_eligible === false || segment.display_level === "none" || segment.quality?.display_level === "none") return false;
  return segment.end_endpoint?.outcome_classification !== "environment_outlier";
}

function reconstructedBallSegments(
  artifact: ReconstructedBallTrajectoryArtifact | null | undefined,
  currentTime: number,
  config: Required<VideoOverlayHudOptions>,
): HudPoint[][] {
  if (!artifact || artifact.status === "unavailable" || artifact.display_trajectory_status === "unavailable") return [];
  const candidates = (artifact.segments ?? []).flatMap((segment, segmentIndex) => {
    if (!isDisplayableReconstructedSegment(segment)) return [];
    const points = segment.samples
      .filter((sample) => sample.validity !== "invalid")
      .map((sample) => validPoint(sample.court_xy?.[0], sample.court_xy?.[1], sample.timestamp_sec, sample.confidence, sample.source === "interpolated", config.courtWidth, config.courtLength))
      .filter((point): point is HudPoint => point !== null)
      .sort((left, right) => left.timestampSeconds - right.timestampSeconds);
    if (!points.length) return [];
    const start = points[0].timestampSeconds;
    const end = points.at(-1)!.timestampSeconds;
    const retained = currentTime >= end && currentTime <= end + config.reconstructedBallRetentionSeconds;
    if (!(currentTime >= start && currentTime < end) && !retained) return [];
    const visible = points.filter((point) => point.timestampSeconds >= (retained ? start : currentTime - config.ballTrailSeconds) && point.timestampSeconds <= currentTime);
    return visible.length ? [{ points: splitAtGaps(visible, config.maxGapSeconds, config.maxBallPoints), start, end, retained, segmentIndex }] : [];
  });
  const active = candidates.filter((candidate) => !candidate.retained).sort((a, b) => b.start - a.start || b.segmentIndex - a.segmentIndex);
  const selected = active[0] ?? candidates.sort((a, b) => b.end - a.end || b.segmentIndex - a.segmentIndex)[0];
  return selected?.points ?? [];
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

  // joint 启动回填：把 fused overlay 帧的真实观测（canonical_court_position_ft）并入球员轨迹。
  // 仅在 overlay 帧存在时生效；bootstrap_backfill 覆盖 bootstrap 窗口内的 pre-lock 帧，
  // 与 tracks（lock 之后）衔接成连续轨迹，消除小地图前 1~2 秒空白（display-only，不修改 metrics）。
  for (const frame of options.overlayFrames ?? []) {
    if (!frame || !Number.isFinite(frame.timestamp_seconds) || frame.timestamp_seconds > currentTime || frame.timestamp_seconds < playerCutoff) continue;
    for (const entity of frame.players ?? []) {
      const cp = entity.canonical_court_position_ft;
      if (!Array.isArray(cp) || cp.length !== 2 || !Number.isFinite(cp[0]) || !Number.isFinite(cp[1])) continue;
      const point = validPoint(
        cp[0],
        cp[1],
        frame.timestamp_seconds,
        entity.source_confidence ?? null,
        false,
        config.courtWidth,
        config.courtLength,
      );
      if (!point) continue;
      const key = canonicalPlayerNumber(entity.player_id)?.toString() ?? entity.player_id;
      const values = groupedPlayers.get(key) ?? [];
      values.push({
        frame_index: frame.frame_index,
        timestamp_seconds: frame.timestamp_seconds,
        track_id: entity.player_id,
        image_point: { x: Array.isArray(entity.footpoint) ? entity.footpoint[0] : 0, y: 0 },
        confidence: entity.source_confidence ?? 0,
        side: "unknown",
        court_point: { x: cp[0], y: cp[1] },
      });
      groupedPlayers.set(key, values);
    }
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
      const segments = splitAtGaps(points, config.maxGapSeconds, config.maxPlayerPoints, config.maxTrailJumpFt);
      const sourceId = playerTracks[0]?.track_id ?? id;
      const latest = latestSegmentPoint(segments);
      return {
        id,
        playerId: canonicalPlayerNumber(sourceId) !== null ? `Player_${canonicalPlayerNumber(sourceId)}` : sourceId,
        label: formatPlayerId(sourceId) || "球员",
        segments,
        latest,
        stale: latest !== null && latest.timestampSeconds < currentTime - config.staleThresholdSeconds,
        ...resolveSpeed(segments, config.courtUnit),
      };
    })
    .filter((player) => player.latest !== null)
    .sort((left, right) => left.label.localeCompare(right.label, "en"));

  const reconstructedSegments = reconstructedBallSegments(config.reconstructedBallTrajectory, currentTime, config);
  const ballPoints = reconstructedSegments.length ? [] : (ballTrajectory?.samples ?? [])
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
  const ballSegments = reconstructedSegments.length
    ? reconstructedSegments
    : splitAtGaps(ballPoints, config.maxGapSeconds, config.maxBallPoints);

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
    ballPointCount: reconstructedSegments.length ? reconstructedSegments.flat().length : ballPoints.length,
  };
}
