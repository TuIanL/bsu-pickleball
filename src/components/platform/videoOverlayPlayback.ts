import type {
  DetectionOverlayBox,
  DetectionOverlayFrame,
  FusedPlayerOverlayEntity,
  FusedPlayerOverlayFrame,
  PoseKeypoint,
  PoseOverlayFrame,
  PoseSubject,
} from "../../types/report";
import { formatPlayerId } from "../../utils/analysisHelpers";

type OverlayFrame = DetectionOverlayFrame | PoseOverlayFrame | FusedPlayerOverlayFrame;

/** 骨架帧空洞超过此阈值（秒）时，骨架淡出隐藏而非沿用上一帧。 */
const MAX_POSE_GAP_SECONDS = 0.5;
/** fused overlay 跨帧插值的最大 gap（秒）：超过禁止插值（spec video-overlay-hud）。 */
const MAX_OVERLAY_GAP_SECONDS = 0.5;
/** predicted_only 实体的最大展示时长（秒）：超过立即隐藏（spec video-overlay-hud）。 */
const PREDICTED_TTL_SECONDS = 0.5;

export type PoseResolutionResult = {
  frame: PoseOverlayFrame | undefined;
  /** 当前播放时间是否落在骨架空洞区间（超出 MAX_POSE_GAP_SECONDS）。 */
  inGap: boolean;
};

type FrameWindow<T extends OverlayFrame> = {
  current?: T;
  next?: T;
  ratio: number;
};

export function findNearestFrame<T extends OverlayFrame>(
  frames: T[],
  currentTime: number
): T | undefined {
  if (!frames.length) {
    return undefined;
  }
  return frames.reduce((nearest, frame) => (
    Math.abs(frame.timestamp_seconds - currentTime) < Math.abs(nearest.timestamp_seconds - currentTime)
      ? frame
      : nearest
  ));
}

export function findFrameWindow<T extends OverlayFrame>(
  frames: T[],
  currentTime: number
): FrameWindow<T> {
  if (!frames.length) {
    return { ratio: 0 };
  }

  if (currentTime <= frames[0].timestamp_seconds) {
    return { current: frames[0], next: frames[1], ratio: 0 };
  }

  let low = 0;
  let high = frames.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const frame = frames[mid];
    if (frame.timestamp_seconds === currentTime) {
      return { current: frame, next: frames[mid + 1], ratio: 0 };
    }
    if (frame.timestamp_seconds < currentTime) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  const current = frames[Math.max(0, high)];
  const next = frames[low];
  if (!next) {
    return { current, ratio: 0 };
  }

  const duration = next.timestamp_seconds - current.timestamp_seconds;
  return { current, next, ratio: duration > 0 ? (currentTime - current.timestamp_seconds) / duration : 0 };
}

export function resolveDetectionFrame(frames: DetectionOverlayFrame[], currentTime: number): DetectionOverlayFrame | undefined {
  const window = findFrameWindow(frames, currentTime);
  if (!window.current) {
    return undefined;
  }
  if (!window.next) {
    return window.current;
  }

  const nextByTrackId = new Map(
    window.next.detections
      .filter((detection) => detection.track_id)
      .map((detection) => [detection.track_id, detection])
  );
  const detections = window.current.detections.map((detection) => {
    const next = detection.track_id ? nextByTrackId.get(detection.track_id) : undefined;
    return next ? interpolateDetection(detection, next, window.ratio, currentTime) : detection;
  });

  return {
    ...window.current,
    timestamp_seconds: currentTime,
    detections,
  };
}

export function resolvePoseFrame(frames: PoseOverlayFrame[], currentTime: number): PoseResolutionResult {
  const window = findFrameWindow(frames, currentTime);
  if (!window.current) {
    return { frame: undefined, inGap: false };
  }
  if (!window.next) {
    return { frame: window.current, inGap: false };
  }

  // 检测空洞：当前帧与下一帧间隔超过阈值 → 标记骨架应隐藏
  const gapSeconds = window.next.timestamp_seconds - window.current.timestamp_seconds;
  const inGap = gapSeconds > MAX_POSE_GAP_SECONDS;
  if (inGap) {
    return { frame: window.current, inGap: true };
  }

  const nextByTrackId = new Map(window.next.subjects.map((subject) => [subject.track_id, subject]));
  const subjects = window.current.subjects.map((subject) => {
    const next = nextByTrackId.get(subject.track_id);
    return next ? interpolatePoseSubject(subject, next, window.ratio) : subject;
  });

  return {
    frame: {
      ...window.current,
      timestamp_seconds: currentTime,
      subjects,
    },
    inGap: false,
  };
}

export type FusedPlayerOverlayResolution = {
  frame: FusedPlayerOverlayFrame | undefined;
  /** 当前时间是否落在 fused overlay 空洞区间（超出 MAX_OVERLAY_GAP_SECONDS）。 */
  inGap: boolean;
};

export function resolveFusedPlayerOverlayFrame(
  frames: FusedPlayerOverlayFrame[],
  currentTime: number
): FusedPlayerOverlayResolution {
  const window = findFrameWindow(frames, currentTime);
  if (!window.current) {
    return { frame: undefined, inGap: false };
  }
  if (!window.next) {
    return { frame: window.current, inGap: false };
  }

  // gap 语义：跨 gap 禁止插值（spec video-overlay-hud）
  const gapSeconds = window.next.timestamp_seconds - window.current.timestamp_seconds;
  const inGap = gapSeconds > MAX_OVERLAY_GAP_SECONDS;

  const nextById = new Map(window.next.players.map((player) => [player.player_id, player]));
  const players = window.current.players
    // predicted_only TTL（spec video-overlay-hud）：连续 predicted 帧间隔超 TTL 视为预测中断
    .filter((player) => {
      if (player.evidence_type !== "predicted_only") {
        return true;
      }
      const next = nextById.get(player.player_id);
      if (!next || next.evidence_type !== "predicted_only") {
        return true;
      }
      return gapSeconds <= PREDICTED_TTL_SECONDS;
    })
    .map((player) => {
      if (inGap) {
        return player; // 跨 gap 不插值
      }
      const next = nextById.get(player.player_id);
      return next ? interpolateFusedPlayer(player, next, window.ratio) : player;
    });

  return {
    frame: {
      ...window.current,
      timestamp_seconds: currentTime,
      players,
    },
    inGap,
  };
}

function interpolateFusedPlayer(
  current: FusedPlayerOverlayEntity,
  next: FusedPlayerOverlayEntity,
  ratio: number
): FusedPlayerOverlayEntity {
  return {
    ...current,
    bbox: current.bbox && next.bbox ? lerpTuple(current.bbox, next.bbox, ratio) : null,
    footpoint: current.footpoint && next.footpoint ? lerpTuple(current.footpoint, next.footpoint, ratio) : undefined,
    overlay_confidence: lerp(current.overlay_confidence, next.overlay_confidence, ratio),
  };
}

function lerpTuple(a: number[], b: number[], ratio: number): number[] {
  return a.map((value, index) => lerp(value, b[index] ?? value, ratio));
}

function interpolateDetection(
  current: DetectionOverlayBox,
  next: DetectionOverlayBox,
  ratio: number,
  timestamp: number
): DetectionOverlayBox {
  const playerId = current.player_id ?? next.player_id;
  const label = current.label
    ?? (playerId ? formatPlayerId(playerId) || next.label : next.label);
  return {
    ...current,
    timestamp_seconds: timestamp,
    bbox: current.bbox.map((value, index) => lerp(value, next.bbox[index] ?? value, ratio)),
    confidence: lerp(current.confidence, next.confidence, ratio),
    player_id: playerId,
    label,
  };
}

function interpolatePoseSubject(current: PoseSubject, next: PoseSubject, ratio: number): PoseSubject {
  const nextKeypoints = new Map(next.keypoints.map((keypoint) => [keypoint.name, keypoint]));
  return {
    ...current,
    bbox: current.bbox.map((value, index) => lerp(value, next.bbox[index] ?? value, ratio)),
    confidence: lerp(current.confidence, next.confidence, ratio),
    keypoints: current.keypoints.map((keypoint) => {
      const nextKeypoint = nextKeypoints.get(keypoint.name);
      return nextKeypoint ? interpolateKeypoint(keypoint, nextKeypoint, ratio) : keypoint;
    }),
  };
}

function interpolateKeypoint(current: PoseKeypoint, next: PoseKeypoint, ratio: number): PoseKeypoint {
  return {
    ...current,
    x: lerp(current.x, next.x, ratio),
    y: lerp(current.y, next.y, ratio),
    confidence: lerp(current.confidence, next.confidence, ratio),
    visible: current.visible && next.visible,
  };
}

function lerp(start: number, end: number, ratio: number): number {
  const clampedRatio = Math.min(1, Math.max(0, ratio));
  return start + (end - start) * clampedRatio;
}
