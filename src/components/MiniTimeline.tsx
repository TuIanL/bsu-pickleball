import { type ReactNode } from "react";
import type { CaptureSegmentSummary, SessionTimelineEvent, LiveCodingState } from "../types/report";

interface TimelineProps {
  segments: CaptureSegmentSummary[];
  events: SessionTimelineEvent[];
  liveState: LiveCodingState | null;
  totalDurationMs: number;
  elapsedMs: number;
}

const TRACK_HEIGHT = 22;
const TRACK_GAP = 6;
const TRACKS = [
  { key: "set", label: "盘", color: "#F97316" },
  { key: "game", label: "局", color: "#3B82F6" },
  { key: "rally", label: "分", color: "#22C55E" },
] as const;

export function MiniTimeline({ segments, events, liveState, totalDurationMs, elapsedMs }: TimelineProps) {
  const viewDuration = Math.max(totalDurationMs, elapsedMs + 30000, 60000);
  const scale = (ms: number) => `${(ms / viewDuration) * 100}%`;

  const segmentsByType: Record<string, CaptureSegmentSummary[]> = {};
  for (const seg of segments) {
    (segmentsByType[seg.segment_type] ??= []).push(seg);
  }

  const eventMarkers = events.filter(
    (e) => ["side_change", "non_play_start", "session_note"].includes(e.event_type)
  );

  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
      <h3 className="text-sm font-bold text-[#14241B] mb-3">时间线</h3>
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
                    const endMs = seg.end_ms ?? viewDuration;
                    const left = scale(seg.start_ms);
                    const width = seg.end_ms
                      ? `calc(${scale(seg.end_ms)} - ${left})`
                      : `calc(${scale(viewDuration)} - ${left})`;
                    const isOpen = seg.status === "open";
                    return (
                      <div
                        key={seg.id}
                        className={`absolute top-0 h-full rounded-md border transition-opacity ${isOpen ? "opacity-100 animate-pulse" : "opacity-80"}`}
                        style={{
                          left,
                          width,
                          backgroundColor: `${track.color}20`,
                          borderColor: track.color,
                          borderWidth: 1.5,
                        }}
                        title={`${seg.label}: ${(seg.start_ms / 1000).toFixed(1)}s → ${seg.end_ms != null ? (seg.end_ms / 1000).toFixed(1) + "s" : "进行中"}`}
                      >
                        <span className="absolute inset-0 flex items-center px-1 text-[9px] font-bold truncate" style={{ color: track.color }}>
                          {seg.ordinal}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}

        {/* Event markers */}
        {eventMarkers.length > 0 && (
          <div className="absolute left-0 right-0 flex items-center gap-2" style={{ top: TRACKS.length * (TRACK_HEIGHT + TRACK_GAP) }}>
            <span className="text-xs font-bold w-6 text-right text-slate-400">事件</span>
            <div className="relative flex-1 h-4">
              {eventMarkers.map((evt) => (
                <div
                  key={evt.id}
                  className="absolute top-0"
                  style={{ left: scale(evt.timestamp_ms) }}
                  title={`${evt.label || evt.event_type} @ ${(evt.timestamp_ms / 1000).toFixed(1)}s`}
                >
                  <svg width="10" height="16" viewBox="0 0 10 16">
                    <polygon points="5,16 0,8 10,8" fill="#94A3B8" />
                  </svg>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Playhead */}
        {elapsedMs > 0 && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-10"
            style={{ left: scale(elapsedMs) }}
          >
            <div className="absolute -top-1 -left-1 w-2.5 h-2.5 rounded-full bg-red-500" />
          </div>
        )}
      </div>

      {/* Time labels */}
      <div className="flex justify-between text-[10px] text-slate-400 mt-2">
        <span>0:00</span>
        <span>{formatDuration(viewDuration / 2)}</span>
        <span>{formatDuration(viewDuration)}</span>
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
