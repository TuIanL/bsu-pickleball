import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CaptureSegmentSummary } from "../types/report";
import {
  canonicalTimeToSourceTimeMs,
  type DisplayTimeMapping,
} from "../utils/multiviewDisplay";

export interface AutoRallySegment {
  id: string;
  ordinal: number;
  startMs: number;
  endMs: number | null;
}

export interface AutoRallyWindow extends Omit<AutoRallySegment, "endMs"> {
  /** 起播可从回合内部续上，因此窗口播放起点可以晚于 startMs。 */
  startMs: number;
  endMs: number;
}

export interface AutoRallyCue {
  id: string;
  ordinal: number;
  cause?: "user" | "autoAdvance";
  cueKey?: number;
}

export interface RallyNavigationRequest {
  requestId: number;
  rally: AutoRallySegment;
}

export function buildAutoRallySegments(
  segments: CaptureSegmentSummary[],
  publishedRunId: string | null | undefined,
): AutoRallySegment[] {
  if (!publishedRunId) return [];
  return segments
    .filter((segment) =>
      segment.edit_status === "active"
      && segment.source === "algorithm"
      && segment.segment_type === "rally"
      && segment.segmentation_run_id === publishedRunId,
    )
    .map((segment) => ({
      id: segment.id,
      ordinal: segment.ordinal,
      startMs: segment.effective_start_ms ?? segment.start_ms,
      endMs: segment.effective_end_ms ?? segment.end_ms ?? null,
    }))
    .sort((left, right) => left.startMs - right.startMs);
}

function rallyEndMs(segment: AutoRallySegment, durationMs: number): number {
  return segment.endMs ?? Math.max(durationMs, segment.startMs + 500);
}

export function findAutoRallyAtTime(
  segments: AutoRallySegment[],
  playheadMs: number,
  durationMs: number,
): AutoRallySegment | null {
  const playhead = Math.max(0, Number.isFinite(playheadMs) ? playheadMs : 0);
  return segments.find((segment) => {
    const endMs = rallyEndMs(segment, durationMs);
    return endMs > segment.startMs && playhead >= segment.startMs && playhead < endMs;
  }) ?? null;
}

export function resolveAutoRallyWindow(
  segments: AutoRallySegment[],
  playheadMs: number,
  durationMs: number,
): AutoRallyWindow | null {
  const playhead = Math.max(0, Number.isFinite(playheadMs) ? playheadMs : 0);
  const inside = segments.find((segment) => {
    const endMs = rallyEndMs(segment, durationMs);
    return endMs > segment.startMs && playhead >= segment.startMs && playhead < endMs;
  });
  const target = inside ?? segments.find((segment) => segment.startMs >= playhead);
  if (!target) return null;
  return {
    ...target,
    startMs: inside ? playhead : target.startMs,
    endMs: rallyEndMs(target, durationMs),
  };
}

export function resolveNextAutoRallyWindow(
  segments: AutoRallySegment[],
  currentWindowEndMs: number,
  durationMs: number,
): AutoRallyWindow | null {
  const target = segments.find((segment) => segment.startMs >= currentWindowEndMs);
  if (!target) return null;
  return { ...target, endMs: rallyEndMs(target, durationMs) };
}

export function resolveCompletedRallyWindow(input: {
  segments: AutoRallySegment[];
  window: AutoRallyWindow | null;
  playheadMs: number;
  durationMs: number;
  isPlaying: boolean;
  autoSkipEnabled: boolean;
}): { endMs: number; nextWindow: AutoRallyWindow | null } | null {
  const { segments, window, playheadMs, durationMs, isPlaying, autoSkipEnabled } = input;
  if (!window || !isPlaying || playheadMs < window.endMs) return null;
  return {
    endMs: window.endMs,
    nextWindow: autoSkipEnabled
      ? resolveNextAutoRallyWindow(segments, window.endMs, durationMs)
      : null,
  };
}

export interface UseAutoRallyPlaybackOptions {
  segments: AutoRallySegment[];
  durationMs: number;
  playheadMs: number;
  isPlaying: boolean;
  unavailableReason?: string | null;
  displayTimeMapping?: DisplayTimeMapping;
  /** Receives source-media milliseconds; this hook owns the canonical→source conversion. */
  requestSeek: (sourceMs: number) => void;
  requestPlay: () => void;
  requestPause: () => void;
}

export function useAutoRallyPlayback({
  segments,
  durationMs,
  playheadMs,
  isPlaying,
  unavailableReason,
  displayTimeMapping,
  requestSeek,
  requestPlay,
  requestPause,
}: UseAutoRallyPlaybackOptions) {
  const [autoSkipEnabled, setAutoSkipEnabled] = useState(true);
  const [cueCause, setCueCause] = useState<AutoRallyCue | null>(null);
  const [pendingWindowCueId, setPendingWindowCueId] = useState<string | null>(null);
  const playbackWindowRef = useRef<AutoRallyWindow | null>(null);
  const cueKeyRef = useRef(0);

  const activeSegment = useMemo(
    () => findAutoRallyAtTime(segments, playheadMs, durationMs),
    [durationMs, playheadMs, segments],
  );
  const pendingWindowCue = !activeSegment
    && cueCause
    && pendingWindowCueId === cueCause.id
    ? segments.find((segment) => segment.id === cueCause.id && playheadMs < segment.startMs) ?? null
    : null;
  const cueSegment = activeSegment ?? pendingWindowCue;
  const activeRally = cueSegment
    ? {
        id: cueSegment.id,
        ordinal: cueSegment.ordinal,
        cause: cueCause?.id === cueSegment.id ? cueCause.cause : "user" as const,
        cueKey: cueCause?.id === cueSegment.id ? cueCause.cueKey : undefined,
      }
    : null;

  const seekCanonical = useCallback((canonicalMs: number) => {
    requestSeek(canonicalTimeToSourceTimeMs(canonicalMs, displayTimeMapping));
  }, [displayTimeMapping, requestSeek]);

  const interruptPlayback = useCallback(() => {
    playbackWindowRef.current = null;
    setPendingWindowCueId(null);
  }, []);

  const markUserNavigation = useCallback((canonicalMs: number) => {
    interruptPlayback();
    const segment = findAutoRallyAtTime(segments, canonicalMs, durationMs);
    setCueCause(segment ? { id: segment.id, ordinal: segment.ordinal, cause: "user", cueKey: ++cueKeyRef.current } : null);
  }, [durationMs, interruptPlayback, segments]);

  const navigateToRally = useCallback((rallyId: string) => {
    const segment = segments.find((item) => item.id === rallyId);
    if (!segment) return;
    const window = resolveAutoRallyWindow([segment], segment.startMs, durationMs);
    if (!window) return;
    playbackWindowRef.current = window;
    setPendingWindowCueId(window.id);
    setCueCause({ id: segment.id, ordinal: segment.ordinal, cause: "user", cueKey: ++cueKeyRef.current });
    seekCanonical(window.startMs);
    requestPlay();
  }, [durationMs, requestPlay, seekCanonical, segments]);

  const handlePlaybackToggle = useCallback(() => {
    if (isPlaying) {
      interruptPlayback();
      requestPause();
      return;
    }
    if (unavailableReason || segments.length === 0) {
      interruptPlayback();
      requestPlay();
      return;
    }
    const window = resolveAutoRallyWindow(segments, playheadMs, durationMs);
    if (!window) {
      interruptPlayback();
      requestPause();
      return;
    }
    playbackWindowRef.current = window;
    setPendingWindowCueId(window.id);
    setCueCause({ id: window.id, ordinal: window.ordinal, cause: "user", cueKey: ++cueKeyRef.current });
    if (Math.abs(window.startMs - playheadMs) > 1) seekCanonical(window.startMs);
    requestPlay();
  }, [durationMs, interruptPlayback, isPlaying, playheadMs, requestPause, requestPlay, seekCanonical, segments, unavailableReason]);

  useEffect(() => {
    const completed = resolveCompletedRallyWindow({
      segments,
      window: playbackWindowRef.current,
      playheadMs,
      durationMs,
      isPlaying,
      autoSkipEnabled,
    });
    if (!completed) return;

    if (completed.nextWindow) {
      playbackWindowRef.current = completed.nextWindow;
      setPendingWindowCueId(completed.nextWindow.id);
      setCueCause({
        id: completed.nextWindow.id,
        ordinal: completed.nextWindow.ordinal,
        cause: "autoAdvance",
        cueKey: ++cueKeyRef.current,
      });
      seekCanonical(completed.nextWindow.startMs);
      requestPlay();
      return;
    }

    playbackWindowRef.current = null;
    setPendingWindowCueId(null);
    seekCanonical(completed.endMs);
    requestPause();
  }, [autoSkipEnabled, durationMs, isPlaying, playheadMs, requestPause, requestPlay, seekCanonical, segments]);

  const autoSkipUnavailableReason = unavailableReason
    ?? (segments.length === 0 ? "无正式切分结果" : null);

  return {
    activeRally,
    autoSkipEnabled,
    setAutoSkipEnabled,
    autoSkipUnavailableReason,
    handlePlaybackToggle,
    interruptPlayback,
    markUserNavigation,
    navigateToRally,
    resolveWindow: useCallback(
      (timeMs: number) => resolveAutoRallyWindow(segments, timeMs, durationMs),
      [durationMs, segments],
    ),
  };
}
