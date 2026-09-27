import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CaptureSegmentSummary } from "../types/report";
import {
  buildAutoRallySegments,
  resolveAutoRallyWindow,
  resolveCompletedRallyWindow,
  resolveNextAutoRallyWindow,
  useAutoRallyPlayback,
  type AutoRallySegment,
} from "./useAutoRallyPlayback";

const segment = (id: string, ordinal: number, startMs: number, endMs: number | null): AutoRallySegment => ({
  id,
  ordinal,
  startMs,
  endMs,
});

const sourceSegment = (overrides: Partial<CaptureSegmentSummary>): CaptureSegmentSummary => ({
  id: "segment",
  segment_type: "rally",
  ordinal: 1,
  label: "第1回合",
  start_ms: 1000,
  end_ms: 2000,
  edit_version: 1,
  edit_status: "active",
  status: "closed",
  source: "algorithm",
  segmentation_run_id: "run-current",
  is_highlight: false,
  ...overrides,
});

describe("buildAutoRallySegments", () => {
  it("只取已发布 run 的 active algorithm rally，使用 effective 边界并按起点排序", () => {
    const result = buildAutoRallySegments([
      sourceSegment({ id: "later", start_ms: 4000, end_ms: 5000, ordinal: 2 }),
      sourceSegment({ id: "earlier", start_ms: 1000, end_ms: 3000, effective_start_ms: 1200, effective_end_ms: 2800 }),
      sourceSegment({ id: "manual", source: "manual" }),
      sourceSegment({ id: "archived", edit_status: "archived" }),
      sourceSegment({ id: "old-run", segmentation_run_id: "run-old" }),
      sourceSegment({ id: "set", segment_type: "set" }),
    ], "run-current");

    expect(result).toEqual([
      { id: "earlier", ordinal: 1, startMs: 1200, endMs: 2800 },
      { id: "later", ordinal: 2, startMs: 4000, endMs: 5000 },
    ]);
  });
});

describe("auto rally time axis", () => {
  const rallies = [segment("r1", 1, 1000, 3000), segment("r2", 2, 6000, 8000)];

  it("starts inside a rally from the playhead and from the next rally before or between windows", () => {
    expect(resolveAutoRallyWindow(rallies, 1500, 10000)).toEqual({ id: "r1", ordinal: 1, startMs: 1500, endMs: 3000 });
    expect(resolveAutoRallyWindow(rallies, 500, 10000)).toEqual({ id: "r1", ordinal: 1, startMs: 1000, endMs: 3000 });
    expect(resolveAutoRallyWindow(rallies, 4000, 10000)).toEqual({ id: "r2", ordinal: 2, startMs: 6000, endMs: 8000 });
  });

  it("keeps playback paused after the final rally and chooses the next start by window end", () => {
    expect(resolveAutoRallyWindow(rallies, 9000, 10000)).toBeNull();
    expect(resolveNextAutoRallyWindow(rallies, 3000, 10000)).toEqual({ id: "r2", ordinal: 2, startMs: 6000, endMs: 8000 });
    expect(resolveNextAutoRallyWindow(rallies, 8000, 10000)).toBeNull();
  });

  it("uses the media duration for a missing end and a 500ms floor when duration is unknown", () => {
    const openEnded = [segment("open", 1, 9000, null)];
    expect(resolveAutoRallyWindow(openEnded, 9500, 12000)?.endMs).toBe(12000);
    expect(resolveAutoRallyWindow(openEnded, 9200, 0)?.endMs).toBe(9500);
    expect(resolveAutoRallyWindow([segment("short", 1, 1000, null)], 1100, 0)?.endMs).toBe(1500);
  });

  it("only advances after natural playback reaches the half-open window end", () => {
    const window = { id: "r1", ordinal: 1, startMs: 1000, endMs: 3000 };
    expect(resolveCompletedRallyWindow({ segments: rallies, window, playheadMs: 2999, durationMs: 10000, isPlaying: true, autoSkipEnabled: true })).toBeNull();
    expect(resolveCompletedRallyWindow({ segments: rallies, window: null, playheadMs: 4000, durationMs: 10000, isPlaying: true, autoSkipEnabled: true })).toBeNull();
    expect(resolveCompletedRallyWindow({ segments: rallies, window, playheadMs: 3000, durationMs: 10000, isPlaying: true, autoSkipEnabled: true })).toEqual({
      endMs: 3000,
      nextWindow: { id: "r2", ordinal: 2, startMs: 6000, endMs: 8000 },
    });
    expect(resolveCompletedRallyWindow({ segments: rallies, window, playheadMs: 3000, durationMs: 10000, isPlaying: true, autoSkipEnabled: false })).toEqual({ endMs: 3000, nextWindow: null });
    expect(resolveCompletedRallyWindow({ segments: rallies, window, playheadMs: 3000, durationMs: 10000, isPlaying: false, autoSkipEnabled: true })).toBeNull();
  });
});

describe("useAutoRallyPlayback", () => {
  it("defaults auto-skip on, advances after natural playback, and stops at the final rally", () => {
    const requestSeek = vi.fn();
    const requestPlay = vi.fn();
    const requestPause = vi.fn();
    const { result, rerender } = renderHook(
      ({ playheadMs, isPlaying }) => useAutoRallyPlayback({
        segments: [segment("r1", 1, 1000, 3000), segment("r2", 2, 6000, 8000)],
        durationMs: 10000,
        playheadMs,
        isPlaying,
        requestSeek,
        requestPlay,
        requestPause,
      }),
      { initialProps: { playheadMs: 1500, isPlaying: false } },
    );

    expect(result.current.autoSkipEnabled).toBe(true);
    act(() => result.current.handlePlaybackToggle());
    expect(requestSeek).not.toHaveBeenCalled();
    expect(requestPlay).toHaveBeenCalledTimes(1);

    rerender({ playheadMs: 3000, isPlaying: true });
    expect(requestSeek).toHaveBeenLastCalledWith(6000);
    expect(result.current.activeRally).toMatchObject({
      id: "r2",
      ordinal: 2,
      cause: "autoAdvance",
    });
    rerender({ playheadMs: 6000, isPlaying: true });
    expect(result.current.activeRally).toMatchObject({
      id: "r2",
      ordinal: 2,
      cause: "autoAdvance",
    });
    expect(requestPlay).toHaveBeenCalledTimes(2);

    rerender({ playheadMs: 8000, isPlaying: true });
    expect(requestSeek).toHaveBeenLastCalledWith(8000);
    expect(requestPause).toHaveBeenCalledTimes(1);
  });

  it("keeps a rally window when auto-skip is off, then pauses at its end", () => {
    const requestSeek = vi.fn();
    const requestPlay = vi.fn();
    const requestPause = vi.fn();
    const { result, rerender } = renderHook(
      ({ playheadMs, isPlaying }) => useAutoRallyPlayback({
        segments: [segment("r1", 1, 1000, 3000), segment("r2", 2, 6000, 8000)],
        durationMs: 10000,
        playheadMs,
        isPlaying,
        requestSeek,
        requestPlay,
        requestPause,
      }),
      { initialProps: { playheadMs: 500, isPlaying: false } },
    );

    act(() => result.current.setAutoSkipEnabled(false));
    act(() => result.current.handlePlaybackToggle());
    expect(requestSeek).toHaveBeenCalledWith(1000);
    expect(requestPlay).toHaveBeenCalledTimes(1);

    rerender({ playheadMs: 3000, isPlaying: true });
    expect(requestPause).toHaveBeenCalledTimes(1);
    expect(requestSeek).toHaveBeenLastCalledWith(3000);
    expect(requestPlay).toHaveBeenCalledTimes(1);
  });

  it("manual seeking or stepping interrupts a rally window and cannot trigger auto-advance", () => {
    const requestSeek = vi.fn();
    const requestPlay = vi.fn();
    const requestPause = vi.fn();
    const { result, rerender } = renderHook(
      ({ playheadMs, isPlaying }) => useAutoRallyPlayback({
        segments: [segment("r1", 1, 1000, 3000), segment("r2", 2, 6000, 8000)],
        durationMs: 10000,
        playheadMs,
        isPlaying,
        requestSeek,
        requestPlay,
        requestPause,
      }),
      { initialProps: { playheadMs: 1500, isPlaying: false } },
    );

    act(() => result.current.navigateToRally("r1"));
    expect(requestSeek).toHaveBeenLastCalledWith(1000);
    act(() => result.current.interruptPlayback());
    rerender({ playheadMs: 3000, isPlaying: true });
    expect(requestSeek).toHaveBeenCalledTimes(1);
    expect(requestSeek).toHaveBeenLastCalledWith(1000);
    expect(requestPlay).toHaveBeenCalledTimes(1);
    expect(requestPause).not.toHaveBeenCalled();
  });

  it("converts canonical rally seeks through the active display mapping", () => {
    const requestSeek = vi.fn();
    const { result } = renderHook(() => useAutoRallyPlayback({
      segments: [segment("r1", 1, 1000, 3000)],
      durationMs: 10000,
      playheadMs: 0,
      isPlaying: false,
      displayTimeMapping: { offsetMs: 36, rate: 0.5 },
      requestSeek,
      requestPlay: vi.fn(),
      requestPause: vi.fn(),
    }));
    act(() => result.current.navigateToRally("r1"));
    expect(requestSeek).toHaveBeenCalledWith(536);
  });
});
