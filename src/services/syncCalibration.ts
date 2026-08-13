import type { VideoTimingFrame } from "./analysisClient";

export interface CalibrationAnchor {
  id: string;
  label: string;
  note: string;
  frameByCamera: Record<string, number>;
  ptsByCamera: Record<string, number>;
  createdAt: string;
}

export interface AnchorExportPayload {
  reference_camera: string;
  cameras: string[];
  anchors: Array<Record<string, number>>;
}

export interface AnchorCoverage {
  count: number;
  spanSeconds: number;
  spanRatio: number;
  hasEarly: boolean;
  hasMiddle: boolean;
  hasLate: boolean;
}

export function clampFrameIndex(frameIndex: number, frames: readonly VideoTimingFrame[]): number {
  if (!frames.length) return 0;
  return Math.min(frames.length - 1, Math.max(0, Math.trunc(frameIndex)));
}

export function getTimingFrame(frames: readonly VideoTimingFrame[], frameIndex: number): VideoTimingFrame | undefined {
  const safeIndex = clampFrameIndex(frameIndex, frames);
  return frames[safeIndex];
}

export function findNearestFrameIndex(frames: readonly VideoTimingFrame[], ptsSeconds: number): number {
  if (!frames.length) return 0;
  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (frames[middle].pts_seconds < ptsSeconds) low = middle + 1;
    else high = middle;
  }
  const next = frames[low];
  const previous = frames[Math.max(0, low - 1)];
  return Math.abs(previous.pts_seconds - ptsSeconds) <= Math.abs(next.pts_seconds - ptsSeconds)
    ? Math.max(0, low - 1)
    : low;
}

export function buildAnchorExport(
  referenceCamera: string,
  cameras: readonly string[],
  anchors: readonly CalibrationAnchor[],
): AnchorExportPayload {
  return {
    reference_camera: referenceCamera,
    cameras: [...cameras],
    anchors: anchors.map((anchor) =>
      Object.fromEntries(cameras.map((camera) => [camera, anchor.ptsByCamera[camera]])),
    ),
  };
}

export function evaluateAnchorCoverage(
  anchors: readonly CalibrationAnchor[],
  referenceCamera: string,
  firstPts: number,
  lastPts: number,
): AnchorCoverage {
  const referenceTimes = anchors
    .map((anchor) => anchor.ptsByCamera[referenceCamera])
    .filter((value): value is number => Number.isFinite(value))
    .sort((left, right) => left - right);
  const spanSeconds = referenceTimes.length > 1 ? referenceTimes[referenceTimes.length - 1] - referenceTimes[0] : 0;
  const mediaSpan = Math.max(0, lastPts - firstPts);
  const spanRatio = mediaSpan > 0 ? spanSeconds / mediaSpan : 0;
  const band = Math.max(0, mediaSpan) / 3;
  return {
    count: referenceTimes.length,
    spanSeconds,
    spanRatio,
    hasEarly: referenceTimes.some((time) => time <= firstPts + band),
    hasMiddle: referenceTimes.some((time) => time > firstPts + band && time < lastPts - band),
    hasLate: referenceTimes.some((time) => time >= lastPts - band),
  };
}

export function formatPts(seconds: number | null | undefined): string {
  return Number.isFinite(seconds) ? `${Number(seconds).toFixed(6)} s` : "—";
}
