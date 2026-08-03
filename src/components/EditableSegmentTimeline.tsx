import { useCallback, useRef, useState } from "react";
import type { CaptureSegmentSummary, SessionTimelineEvent } from "../types/report";

interface EditableSegmentTimelineProps {
  segments: CaptureSegmentSummary[];
  events: SessionTimelineEvent[];
  totalDurationMs: number;
  currentTimeMs: number;
  onSeek: (ms: number) => void;
  onBoundaryChange: (segmentId: string, startMs: number, endMs: number) => void;
}

const TRACKS = [
  { key: "set", label: "盘", color: "#F97316" } as const,
  { key: "game", label: "局", color: "#3B82F6" } as const,
  { key: "rally", label: "分", color: "#22C55E" } as const,
];

export function EditableSegmentTimeline({
  segments, events, totalDurationMs, currentTimeMs, onSeek, onBoundaryChange,
}: EditableSegmentTimelineProps) {
  const scale = (ms: number) => `${(ms / totalDurationMs) * 100}%`;
  const timelineRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<{ segId: string; handle: "left" | "right" } | null>(null);
  const dragStartRef = useRef<{ mouseX: number; segStart: number; segEnd: number } | null>(null);

  const segmentsByType: Record<string, CaptureSegmentSummary[]> = {};
  for (const seg of segments) {
    if (seg.edit_status === "superseded") continue;
    (segmentsByType[seg.segment_type] ??= []).push(seg);
  }

  const handleMouseDown = useCallback((e: React.MouseEvent, seg: CaptureSegmentSummary, handle: "left" | "right") => {
    e.stopPropagation();
    e.preventDefault();
    const start = seg.effective_start_ms ?? seg.start_ms;
    const end = seg.effective_end_ms ?? seg.end_ms;
    if (end == null) return;
    setDragging({ segId: seg.id, handle });
    dragStartRef.current = { mouseX: e.clientX, segStart: start, segEnd: end };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging || !dragStartRef.current) return;
    const timeline = timelineRef.current;
    if (!timeline) return;
    const rect = timeline.getBoundingClientRect();
    const dx = e.clientX - dragStartRef.current.mouseX;
    const dMs = (dx / rect.width) * totalDurationMs;

    if (dragging.handle === "left") {
      onBoundaryChange(dragging.segId, Math.max(0, Math.round(dragStartRef.current.segStart + dMs)), dragStartRef.current.segEnd);
    } else {
      onBoundaryChange(dragging.segId, dragStartRef.current.segStart, Math.min(totalDurationMs, Math.round(dragStartRef.current.segEnd + dMs)));
    }
  }, [dragging, totalDurationMs, onBoundaryChange]);

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    dragStartRef.current = null;
  }, []);

  const handleTimelineClick = useCallback((e: React.MouseEvent) => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    const rect = timeline.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const ms = Math.round((x / rect.width) * totalDurationMs);
    onSeek(Math.max(0, Math.min(ms, totalDurationMs)));
  }, [totalDurationMs, onSeek]);

  const eventMarkers = events.filter((e) => ["side_change", "non_play_start", "session_note"].includes(e.event_type ?? ""));

  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
      <h3 className="text-sm font-bold text-[#14241B] mb-3">时间线</h3>

      <div
        ref={timelineRef}
        className="relative select-none"
        style={{ height: TRACKS.length * 28 + 20 }}
        onMouseMove={dragging ? handleMouseMove : undefined}
        onMouseUp={dragging ? handleMouseUp : undefined}
        onMouseLeave={dragging ? handleMouseUp : undefined}
        onClick={handleTimelineClick}
      >
        {TRACKS.map((track, ti) => {
          const items = segmentsByType[track.key] ?? [];
          const top = ti * 28;
          return (
            <div key={track.key} className="absolute left-0 right-0 flex items-center gap-2" style={{ top }}>
              <span className="text-xs font-bold w-6 text-right shrink-0" style={{ color: track.color }}>{track.label}</span>
              <div className="relative flex-1 h-6 bg-slate-100 rounded-md overflow-hidden">
                {items.map(seg => {
                  const s = seg.effective_start_ms ?? seg.start_ms;
                  const e = seg.effective_end_ms ?? seg.end_ms ?? totalDurationMs;
                  const isSuperseded = seg.edit_status === "superseded";
                  const isOpen = seg.status === "open";
                  return (
                    <div
                      key={seg.id}
                      className={`absolute top-0 h-full rounded-md border transition-opacity ${isSuperseded ? "opacity-30 border-dashed" : isOpen ? "opacity-100 animate-pulse" : "opacity-80"}`}
                      style={{
                        left: scale(s),
                        width: `calc(${scale(e)} - ${scale(s)})`,
                        backgroundColor: `${track.color}20`,
                        borderColor: track.color,
                        borderWidth: 1.5,
                        cursor: isSuperseded ? "default" : "pointer",
                      }}
                      title={`${seg.label}: ${(s / 1000).toFixed(1)}s → ${(e / 1000).toFixed(1)}s`}
                    >
                      {!isSuperseded && !isOpen && (
                        <>
                          <div
                            className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-black/20 z-10"
                            onMouseDown={(ev) => handleMouseDown(ev, seg, "left")}
                          />
                          <div
                            className="absolute right-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-black/20 z-10"
                            onMouseDown={(ev) => handleMouseDown(ev, seg, "right")}
                          />
                        </>
                      )}
                      <span className="absolute inset-0 flex items-center px-1 text-[9px] font-bold truncate pointer-events-none" style={{ color: track.color }}>
                        {seg.label || seg.ordinal}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Event markers */}
        {eventMarkers.length > 0 && (
          <div className="absolute left-0 right-0 flex items-center gap-2" style={{ top: TRACKS.length * 28 + 2 }}>
            <span className="text-xs font-bold w-6 text-right text-slate-400 shrink-0">事件</span>
            <div className="relative flex-1 h-4">
              {eventMarkers.map((evt) => (
                <div key={evt.id} className="absolute top-0" style={{ left: scale(evt.timestamp_ms ?? 0) }}>
                  <svg width="10" height="16"><polygon points="5,16 0,8 10,8" fill="#94A3B8" /></svg>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Playhead */}
        <div className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-20 pointer-events-none" style={{ left: scale(currentTimeMs) }}>
          <div className="absolute -top-1 -left-1.5 w-3 h-3 rounded-full bg-red-500" />
        </div>
      </div>

      <div className="flex justify-between text-[10px] text-slate-400 mt-2">
        <span>0:00</span>
        <span>{formatDuration(totalDurationMs / 2)}</span>
        <span>{formatDuration(totalDurationMs)}</span>
      </div>
    </div>
  );
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}
