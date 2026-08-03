import { useEffect, useMemo, useRef, useState } from "react";
import type { CaptureSegmentSummary, SessionTimelineEvent, LiveCodingState } from "../types/report";
import { computeTicks, toTimelineMarkers } from "./capture/timelineScale";
import type { TimelineMarker } from "./capture/captureTypes";

interface TimelineRange {
  startMs: number;
  endMs: number;
  kind: "between_rallies" | "timeout" | "side_change";
}

export type TimelineWindowMode = "full" | "recent";
export type TimelineDensity = "compact" | "expanded";

interface TimelineProps {
  segments: CaptureSegmentSummary[];
  events: SessionTimelineEvent[];
  liveState: LiveCodingState | null;
  totalDurationMs: number;
  elapsedMs: number;
  staticMode?: boolean;
  playing?: boolean;
  markers?: TimelineMarker[];
  compact?: boolean;
  windowMode?: TimelineWindowMode;
  onWindowModeChange?: (mode: TimelineWindowMode) => void;
  density?: TimelineDensity;
  onDensityChange?: (density: TimelineDensity) => void;
}

const TRACK_HEIGHT_COMPACT = 18;
const TRACK_HEIGHT_EXPANDED = 26;
const TRACK_GAP_COMPACT = 4;
const TRACK_GAP_EXPANDED = 6;
const HIGHLIGHT_TRACK_HEIGHT = 20;
const PLAYHEAD_HEADROOM_MS = 5000;

const TRACKS = [
  { key: "set", label: "盘", color: "var(--capture-timeline-set)" },
  { key: "game", label: "局", color: "var(--capture-timeline-game)" },
  { key: "rally", label: "分", color: "var(--capture-timeline-rally)" },
] as const;

export function deriveNonPlayRanges(events: SessionTimelineEvent[], elapsedMs: number): TimelineRange[] {
  const sorted = [...events].filter(e => e.event_type === "non_play_start" || e.event_type === "non_play_end")
    .sort((a, b) => a.timestamp_ms - b.timestamp_ms);
  const ranges: TimelineRange[] = [];
  let openStart: number | null = null;
  let openKind: TimelineRange["kind"] = "between_rallies";
  for (const evt of sorted) {
    if (evt.event_type === "non_play_start") {
      if (openStart !== null) continue;
      openStart = evt.timestamp_ms;
      const kind = evt.payload_json?.intermission_kind;
      openKind = kind === "timeout" || kind === "side_change" ? kind : "between_rallies";
    } else if (evt.event_type === "non_play_end") {
      if (openStart === null) continue;
      ranges.push({ startMs: openStart, endMs: evt.timestamp_ms, kind: openKind });
      openStart = null;
    }
  }
  if (openStart !== null) ranges.push({ startMs: openStart, endMs: elapsedMs, kind: openKind });
  return ranges;
}

export function MiniTimeline({ segments, events, liveState, totalDurationMs, elapsedMs, staticMode = false, playing = false, markers: externalMarkers, compact = false, windowMode, onWindowModeChange, density, onDensityChange }: TimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(600);
  const [smoothElapsedMs, setSmoothElapsedMs] = useState(elapsedMs);
  const anchorRef = useRef({ elapsedMs, at: 0 });

  const trackHeight = compact ? TRACK_HEIGHT_COMPACT : TRACK_HEIGHT_EXPANDED;
  const trackGap = compact ? TRACK_GAP_COMPACT : TRACK_GAP_EXPANDED;

  const internalWindowMode = windowMode ?? (elapsedMs > 300_000 ? "recent" : "full");
  const internalDensity = density ?? "compact";

  const latestContentMs = Math.max(
    elapsedMs,
    ...segments.flatMap(s => [s.start_ms, s.end_ms ?? 0]),
    ...events.map(e => e.timestamp_ms),
  );
  const VIEW_DURATION_MS_CURRENT = internalWindowMode === "recent"
    ? 300_000
    : Math.max(totalDurationMs, latestContentMs, 30_000) + PLAYHEAD_HEADROOM_MS;

  useEffect(() => {
    if (!staticMode || !playing) {
      anchorRef.current = { elapsedMs, at: performance.now() };
      return;
    }
    anchorRef.current = { elapsedMs, at: performance.now() };
    let frame = 0;
    const tick = () => {
      setSmoothElapsedMs(anchorRef.current.elapsedMs + performance.now() - anchorRef.current.at);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [elapsedMs, staticMode, playing]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 录制中使用 runtime 每 250ms 更新的时间，避免 rAF 让整个时间轴每帧重排；
  // 静态播放仍保留平滑指针。
  const displayElapsedMs = staticMode && playing ? smoothElapsedMs : elapsedMs;
  const contentEndMs = Math.max(totalDurationMs, displayElapsedMs, latestContentMs);
  const windowEnd = internalWindowMode === "recent"
    ? Math.max(displayElapsedMs + PLAYHEAD_HEADROOM_MS, latestContentMs)
    : Math.max(contentEndMs, VIEW_DURATION_MS_CURRENT);
  const windowStart = internalWindowMode === "recent"
    ? Math.max(0, windowEnd - VIEW_DURATION_MS_CURRENT)
    : 0;
  const scale = (ms: number) => `${Math.max(0, Math.min(100, ((ms - windowStart) / VIEW_DURATION_MS_CURRENT) * 100))}%`;

  const ticks = useMemo(() =>
    computeTicks(windowStart, windowEnd, containerWidth, compact ? 56 : 72),
    [windowStart, windowEnd, containerWidth, compact],
  );

  const segmentsByType: Record<string, CaptureSegmentSummary[]> = {};
  for (const seg of segments) (segmentsByType[seg.segment_type] ??= []).push(seg);

  const liveSegmentIds = new Set([
    liveState?.current_set_segment_id,
    liveState?.current_game_segment_id,
    liveState?.current_rally_segment_id,
  ].filter((id): id is string => Boolean(id)));

  const hasLiveDescendant = (segmentId: string): boolean => segments.some(
    c => c.parent_segment_id === segmentId && (liveSegmentIds.has(c.id) || hasLiveDescendant(c.id)),
  );

  const markers = externalMarkers ?? toTimelineMarkers(events);

  const highlightMarkers = markers.filter(m => m.track === "highlight");

  const nonPlayRanges = useMemo(() => deriveNonPlayRanges(events, displayElapsedMs), [events, displayElapsedMs]);

  const controlsHeight = onWindowModeChange ? 28 : 0;
  const totalTrackHeight = controlsHeight + TRACKS.length * (trackHeight + trackGap) + (highlightMarkers.length > 0 ? HIGHLIGHT_TRACK_HEIGHT + trackGap : 0) + 24;

  return (
    <div className="w-full" ref={containerRef}>
      <div className="relative" style={{ height: totalTrackHeight }}>
        {/* View controls */}
        {onWindowModeChange && (
          <div className="flex items-center gap-2 mb-1 text-xs" style={{ color: "var(--capture-text-muted)" }}>
            <button className={`px-2 py-0.5 rounded ${internalWindowMode === "full" ? "font-bold" : ""}`}
              style={internalWindowMode === "full" ? { background: "var(--capture-brand-soft)", color: "var(--capture-brand-primary)" } : {}}
              onClick={() => onWindowModeChange("full")} type="button">全场</button>
            <button className={`px-2 py-0.5 rounded ${internalWindowMode === "recent" ? "font-bold" : ""}`}
              style={internalWindowMode === "recent" ? { background: "var(--capture-brand-soft)", color: "var(--capture-brand-primary)" } : {}}
              onClick={() => onWindowModeChange("recent")} type="button">最近</button>
            {onDensityChange && (
              <button className="ml-auto px-2 py-0.5 rounded hover:bg-gray-100 transition"
                onClick={() => onDensityChange(internalDensity === "compact" ? "expanded" : "compact")} type="button">
                {internalDensity === "compact" ? "展开" : "收起"}
              </button>
            )}
          </div>
        )}
        {TRACKS.map((track, ti) => {
          const items = segmentsByType[track.key] ?? [];
          const top = controlsHeight + ti * (trackHeight + trackGap);
          return (
            <div key={track.key} className="absolute left-0 right-0" style={{ top }}>
              <div className="flex items-center gap-2">
                <span className={`${compact ? "text-[10px]" : "text-xs"} font-bold w-5 text-right shrink-0`} style={{ color: track.color }}>{track.label}</span>
                <div className="relative flex-1 rounded-md overflow-hidden" style={{ background: "var(--capture-surface-page)", height: compact ? 14 : 20 }}>
                  {items.map(seg => {
                    const extendsToPlayhead = seg.status === "open" || liveSegmentIds.has(seg.id) || hasLiveDescendant(seg.id);
                    const effectiveEndMs = extendsToPlayhead ? Math.max(displayElapsedMs, seg.start_ms) : (seg.end_ms ?? Math.max(displayElapsedMs, seg.start_ms));
                    const left = scale(seg.start_ms);
                    const widthVal = `calc(${scale(effectiveEndMs)} - ${left})`;
                    const isOpen = seg.status === "open" || extendsToPlayhead;
                    return (
                      <div key={seg.id} className={`absolute top-0 h-full rounded-md border transition-opacity ${isOpen ? "opacity-100" : "opacity-80"}`}
                        style={{ left: left, width: widthVal, backgroundColor: `${track.color}20`, borderColor: track.color, borderWidth: 1.5 }}
                        title={`${seg.label}: ${(seg.start_ms / 1000).toFixed(1)}s → ${effectiveEndMs ? (effectiveEndMs / 1000).toFixed(1) + "s" : "进行中"}`}>
                        <span className="absolute inset-0 flex items-center px-1 text-[9px] font-bold truncate" style={{ color: track.color }}>{seg.ordinal}</span>
                      </div>
                    );
                  })}
                  {nonPlayRanges.map((range, ri) => (
                    <div key={`np-${ri}`} className="absolute top-0 h-full pointer-events-none"
                      style={{ left: scale(range.startMs), width: `calc(${scale(range.endMs)} - ${scale(range.startMs)})`,
                        backgroundColor: range.kind === "side_change" ? "rgba(168, 85, 247, 0.16)" : "rgba(156, 163, 175, 0.2)",
                        backgroundImage: range.kind === "timeout" ? "repeating-linear-gradient(135deg, rgba(71,85,105,.32) 0 3px, transparent 3px 6px)" : undefined,
                        borderLeft: range.kind === "side_change" ? "1px solid #A855F7" : undefined }} />
                  ))}
                  {ticks.map(tick => (
                    <div key={tick.label} className="absolute top-0 bottom-0 w-px pointer-events-none" style={{ left: `${tick.positionPct}%`, background: "var(--capture-border-default)", opacity: 0.5 }} />
                  ))}
                </div>
              </div>
            </div>
          );
        })}

        {/* Highlight marker track */}
        {highlightMarkers.length > 0 && (
          <div className="absolute left-0 right-0" style={{ top: controlsHeight + TRACKS.length * (trackHeight + trackGap) }}>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold w-6 text-right shrink-0" style={{ color: "var(--capture-timeline-highlight)" }}>标记</span>
              <div className="relative flex-1 h-4 rounded-md" style={{ background: "var(--capture-surface-page)" }}>
                {highlightMarkers.map(m => (
                  <div key={m.id} className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2" style={{ left: scale(m.timestampMs) }}>
                    <div style={{ width: 8, height: 8, background: "var(--capture-timeline-highlight)", transform: "rotate(45deg)" }} title={m.label} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Side_change markers */}
        {markers.filter(m => m.track === "side_change").map(m => (
          <div key={m.id} className="absolute pointer-events-none" style={{ left: `calc(${scale(m.timestampMs)} - 3px)`, top: controlsHeight, height: TRACKS.length * (trackHeight + trackGap) }}>
            <div className="absolute -top-1 -left-[2.5px] rotate-45" style={{ backgroundColor: "var(--capture-timeline-side-change)", width: 6, height: 6 }} />
            <div className="h-full w-px" style={{ backgroundColor: "var(--capture-timeline-side-change)" }} />
          </div>
        ))}

        {/* Playhead */}
        {displayElapsedMs > 100 && (
          <div className="absolute left-8 right-0 top-0 bottom-0 pointer-events-none">
            <div className="absolute bottom-0 w-0.5 z-10" style={{ left: scale(displayElapsedMs), top: controlsHeight, background: "var(--capture-timeline-playhead)" }}>
              <div className="absolute -top-1 -left-1 w-2.5 h-2.5 rounded-full" style={{ background: "var(--capture-timeline-playhead)" }} />
            </div>
          </div>
        )}
      </div>

      {/* Time ticks labels */}
      <div className="flex relative text-[10px] mt-1" style={{ color: "var(--capture-text-muted)", height: 16 }}>
        {ticks.map(tick => (
          <span key={tick.label} className="absolute" style={{ left: `${tick.positionPct}%`, transform: "translateX(-50%)" }}>
            {tick.label}
          </span>
        ))}
      </div>
    </div>
  );
}
