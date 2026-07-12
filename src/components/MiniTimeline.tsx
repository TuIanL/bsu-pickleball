import { useEffect, useMemo, useRef, useState } from "react";
import type { CaptureSegmentSummary, SessionTimelineEvent, LiveCodingState } from "../types/report";

interface TimelineRange {
  startMs: number;
  endMs: number;
  kind: "between_rallies" | "timeout" | "side_change";
}

interface TimelineProps {
  segments: CaptureSegmentSummary[];
  events: SessionTimelineEvent[];
  liveState: LiveCodingState | null;
  totalDurationMs: number;
  elapsedMs: number;
  showDurationHint?: boolean;
  staticMode?: boolean;
}

const TRACK_HEIGHT = 26;
const TRACK_GAP = 6;
const VIEW_DURATION_MS = 90000;
const PLAYHEAD_HEADROOM_MS = 5000;
const TRACKS = [
  { key: "set", label: "盘", color: "#F97316" },
  { key: "game", label: "局", color: "#3B82F6" },
  { key: "rally", label: "分", color: "#22C55E" },
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

  if (openStart !== null) {
    ranges.push({ startMs: openStart, endMs: elapsedMs, kind: openKind });
  }

  return ranges;
}

export function MiniTimeline({ segments, events, liveState, totalDurationMs, elapsedMs, showDurationHint, staticMode = false }: TimelineProps) {
  const [smoothElapsedMs, setSmoothElapsedMs] = useState(elapsedMs);
  const anchorRef = useRef({ elapsedMs, at: performance.now() });
  useEffect(() => {
    if (staticMode) {
      setSmoothElapsedMs(elapsedMs);
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
  }, [elapsedMs, staticMode]);
  const displayElapsedMs = staticMode ? elapsedMs : Math.max(elapsedMs, smoothElapsedMs);
  // Keep a small amount of room to the right of the playhead. Without this,
  // events created just after the latest elapsed tick are all clamped to 100%.
  const latestContentMs = Math.max(
    displayElapsedMs,
    ...segments.flatMap((segment) => [segment.start_ms, segment.end_ms ?? 0]),
    ...events.map((event) => event.timestamp_ms),
  );
  const windowEnd = Math.max(displayElapsedMs + PLAYHEAD_HEADROOM_MS, latestContentMs);
  const windowStart = Math.max(0, windowEnd - VIEW_DURATION_MS);
  const scale = (ms: number) => `${Math.max(0, Math.min(100, ((ms - windowStart) / VIEW_DURATION_MS) * 100))}%`;

  const segmentsByType: Record<string, CaptureSegmentSummary[]> = {};
  for (const seg of segments) {
    (segmentsByType[seg.segment_type] ??= []).push(seg);
  }

  // Some older dual-camera takes persisted inferred parent segments with a
  // zero-length end. The live state still identifies those parents as active,
  // so extend them visually until the corresponding end action arrives.
  const liveSegmentIds = new Set([
    liveState?.current_set_segment_id,
    liveState?.current_game_segment_id,
    liveState?.current_rally_segment_id,
  ].filter((id): id is string => Boolean(id)));
  const hasLiveDescendant = (segmentId: string): boolean => segments.some(
    (candidate) => candidate.parent_segment_id === segmentId
      && (liveSegmentIds.has(candidate.id) || hasLiveDescendant(candidate.id)),
  );

  const instantMarkers = useMemo(() => events.filter(
    (e) => e.event_type === "side_change" || (e.event_type === "session_note" || e.event_type === "add_note"),
  ), [events]);

  const nonPlayRanges = useMemo(() => deriveNonPlayRanges(events, displayElapsedMs), [events, displayElapsedMs]);

  const isRecording = showDurationHint === true || segments.length > 0 || elapsedMs > 0;

  return (
    <div className="w-full">
      <div className="relative" style={{ height: TRACKS.length * (TRACK_HEIGHT + TRACK_GAP) + 24 }}>
        {/* Tracks */}
        {TRACKS.map((track, ti) => {
          const items = segmentsByType[track.key] ?? [];
          const top = ti * (TRACK_HEIGHT + TRACK_GAP);
          return (
            <div key={track.key} className="absolute left-0 right-0" style={{ top }}>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold w-6 text-right" style={{ color: track.color }}>
                  {track.label}
                </span>
                <div className="relative flex-1 h-5 bg-slate-100 rounded-md overflow-hidden">
                  {items.map((seg) => {
                    const extendsToPlayhead = seg.status === "open"
                      || liveSegmentIds.has(seg.id)
                      || hasLiveDescendant(seg.id);
                    const effectiveEndMs = extendsToPlayhead
                      ? Math.max(displayElapsedMs, seg.start_ms)
                      : (seg.end_ms ?? Math.max(displayElapsedMs, seg.start_ms));
                    const left = scale(seg.start_ms);
                    const width = `calc(${scale(effectiveEndMs)} - ${left})`;
                    const isOpen = seg.status === "open" || extendsToPlayhead;
                    return (
                      <div
                        key={seg.id}
                        className={`absolute top-0 h-full rounded-md border transition-opacity ${isOpen ? "opacity-100" : "opacity-80"}`}
                        style={{
                          left,
                          width,
                          backgroundColor: `${track.color}20`,
                          borderColor: track.color,
                          borderWidth: 1.5,
                        }}
                        title={`${seg.label}: ${(seg.start_ms / 1000).toFixed(1)}s → ${effectiveEndMs != null ? (effectiveEndMs / 1000).toFixed(1) + "s" : "进行中"}`}
                      >
                        <span className="absolute inset-0 flex items-center px-1 text-[9px] font-bold truncate" style={{ color: track.color }}>
                          {seg.ordinal}
                        </span>
                      </div>
                    );
                  })}

                  {/* Non-play overlay on each track */}
                  {nonPlayRanges.map((range, ri) => (
                    <div
                      key={`np-${ri}`}
                      className="absolute top-0 h-full pointer-events-none"
                      style={{
                        left: scale(range.startMs),
                        width: `calc(${scale(range.endMs)} - ${scale(range.startMs)})`,
                          backgroundColor: range.kind === "side_change" ? "rgba(168, 85, 247, 0.16)" : "rgba(156, 163, 175, 0.2)",
                          backgroundImage: range.kind === "timeout" ? "repeating-linear-gradient(135deg, rgba(71,85,105,.32) 0 3px, transparent 3px 6px)" : undefined,
                          borderLeft: range.kind === "side_change" ? "1px solid #A855F7" : undefined,
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          );
        })}

        {/* Instant markers */}
        {instantMarkers.length > 0 && (
          <div className="absolute left-8 right-0 top-0 bottom-0 pointer-events-none">
            {instantMarkers.map((evt) => {
              if (evt.event_type === "side_change") {
                return (
                  <div
                    key={evt.id}
                    className="absolute top-0 bottom-0 w-px"
                    style={{ left: scale(evt.timestamp_ms), top: 0, height: TRACKS.length * (TRACK_HEIGHT + TRACK_GAP) }}
                  >
                    <div
                      className="absolute -top-1 -left-[2.5px] rotate-45"
                      style={{ backgroundColor: "#A855F7", width: 6, height: 6 }}
                    />
                    <div className="h-full w-px" style={{ backgroundColor: "#A855F7" }} />
                  </div>
                );
              }
              if (evt.event_type === "session_note" || evt.event_type === "add_note") {
                const highlight = evt.payload_json?.highlight === true || evt.note?.includes("highlight");
                if (!highlight) return null;
                return (
                  <div
                    key={evt.id}
                    className="absolute"
                    style={{ left: `calc(${scale(evt.timestamp_ms)} - 4px)`, top: 4 }}
                    title={evt.note || evt.label}
                  >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="#F59E0B">
                      <polygon points="5,0 6.5,3.5 10,4 7.5,6.5 8,10 5,8.5 2,10 2.5,6.5 0,4 3.5,3.5" />
                    </svg>
                  </div>
                );
              }
              return null;
            })}
          </div>
        )}

        {/* Playhead — 前 100ms 不渲染，避免指针从 0 位置走入 */}
        {displayElapsedMs > 100 && (
          <div className="absolute left-8 right-0 top-0 bottom-0 pointer-events-none">
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-10"
              style={{ left: scale(displayElapsedMs) }}
            >
              <div className="absolute -top-1 -left-1 w-2.5 h-2.5 rounded-full bg-red-500" />
            </div>
          </div>
        )}
      </div>

      {/* Time labels */}
      <div className="flex justify-between text-[10px] text-slate-400 mt-2">
        <span>{formatDuration(windowStart)}</span>
        <span>{formatDuration(windowStart + VIEW_DURATION_MS / 2)}</span>
        <span className="flex items-center gap-1">
          <span>{formatDuration(windowEnd)}</span>
        </span>
      </div>
    </div>
  );
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
