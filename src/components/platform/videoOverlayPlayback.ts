import type {
  BallOverlayFrame,
  BallTrajectoryPoint,
  DetectionOverlayBox,
  DetectionOverlayFrame,
  PoseKeypoint,
  PoseOverlayFrame,
  PoseSubject,
} from "../../types/report";

type OverlayFrame = DetectionOverlayFrame | PoseOverlayFrame | BallOverlayFrame;

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

export function resolvePoseFrame(frames: PoseOverlayFrame[], currentTime: number): PoseOverlayFrame | undefined {
  const window = findFrameWindow(frames, currentTime);
  if (!window.current) {
    return undefined;
  }
  if (!window.next) {
    return window.current;
  }

  const nextByTrackId = new Map(window.next.subjects.map((subject) => [subject.track_id, subject]));
  const subjects = window.current.subjects.map((subject) => {
    const next = nextByTrackId.get(subject.track_id);
    return next ? interpolatePoseSubject(subject, next, window.ratio) : subject;
  });

  return {
    ...window.current,
    timestamp_seconds: currentTime,
    subjects,
  };
}

export function resolveBallFrame(frames: BallOverlayFrame[], currentTime: number): BallOverlayFrame | undefined {
  const nearest = findNearestFrame(frames, currentTime);
  if (!nearest) {
    return undefined;
  }
  const currentSegmentId = nearest.points[0]?.segment_id;
  const visiblePoints = frames
    .flatMap((frame) => frame.points)
    .filter((point) => point.segment_id === currentSegmentId && point.timestamp_seconds <= currentTime)
    .slice(-24);

  return {
    ...nearest,
    timestamp_seconds: currentTime,
    points: visiblePoints.length ? visiblePoints : nearest.points,
  };
}

function interpolateDetection(
  current: DetectionOverlayBox,
  next: DetectionOverlayBox,
  ratio: number,
  timestamp: number
): DetectionOverlayBox {
  return {
    ...current,
    timestamp_seconds: timestamp,
    bbox: current.bbox.map((value, index) => lerp(value, next.bbox[index] ?? value, ratio)),
    confidence: lerp(current.confidence, next.confidence, ratio),
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

export function ballPointKey(point: BallTrajectoryPoint): string {
  return `${point.segment_id}-${point.frame_index}-${point.source}`;
}

function lerp(start: number, end: number, ratio: number): number {
  const clampedRatio = Math.min(1, Math.max(0, ratio));
  return start + (end - start) * clampedRatio;
}
