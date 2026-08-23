import { useCallback, useRef, useState } from "react";
import type { CaptureSegmentSummary, SessionTimelineEvent } from "../types/report";

interface EditableSegmentTimelineProps {
  segments: CaptureSegmentSummary[];
  events: SessionTimelineEvent[];
  totalDurationMs: number;
  currentTimeMs: number;
  activeSegmentId?: string | null;
  savingSegmentId?: string | null;
  onSeek: (ms: number) => void;
  onSegmentClick?: (segmentId: string, startMs: number) => void;
  onBoundaryChange: (segmentId: string, startMs: number, endMs: number, expectedVersion: number) => void | Promise<void>;
}

const MIN_SEGMENT_DURATION_MS = 500;

const TRACKS = [
  { key: "set", label: "盘", color: "#F97316" } as const,
  { key: "game", label: "局", color: "#3B82F6" } as const,
  { key: "rally", label: "分", color: "#22C55E" } as const,
];

export function EditableSegmentTimeline({
  segments,
  events,
  totalDurationMs,
  currentTimeMs,
  activeSegmentId = null,
  savingSegmentId = null,
  onSeek,
  onSegmentClick,
  onBoundaryChange,
}: EditableSegmentTimelineProps) {
  const scale = (ms: number) => `${(Math.max(0, Math.min(ms, totalDurationMs)) / totalDurationMs) * 100}%`;
  const timelineRef = useRef<HTMLDivElement>(null);
  const suppressClickRef = useRef(false);
  const [dragging, setDragging] = useState<{
    segId: string;
    handle: "left" | "right";
    segStart: number;
    segEnd: number;
    draftStart: number;
    draftEnd: number;
    expectedVersion: number;
  } | null>(null);
  const [playheadDragging, setPlayheadDragging] = useState(false);
  const dragStartRef = useRef<{ pointerId: number; pointerX: number; segStart: number; segEnd: number } | null>(null);
  const playheadPointerIdRef = useRef<number | null>(null);

  const segmentsByType: Record<string, CaptureSegmentSummary[]> = {};
  for (const seg of segments) {
    if (seg.edit_status === "superseded") continue;
    (segmentsByType[seg.segment_type] ??= []).push(seg);
  }

  const handlePointerDown = useCallback((e: React.PointerEvent, seg: CaptureSegmentSummary, handle: "left" | "right") => {
    e.stopPropagation();
    e.preventDefault();
    if (savingSegmentId || seg.edit_status === "superseded" || seg.status === "open") return;
    const start = seg.effective_start_ms ?? seg.start_ms;
    const end = seg.effective_end_ms ?? seg.end_ms;
    if (end == null || end <= start) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging({
      segId: seg.id,
      handle,
      segStart: start,
      segEnd: end,
      draftStart: start,
      draftEnd: end,
      expectedVersion: seg.edit_version,
    });
    dragStartRef.current = { pointerId: e.pointerId, pointerX: e.clientX, segStart: start, segEnd: end };
  }, [savingSegmentId]);

  const seekFromPointer = useCallback((clientX: number) => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    const rect = timeline.getBoundingClientRect();
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    onSeek(Math.round((x / rect.width) * totalDurationMs));
  }, [onSeek, totalDurationMs]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (playheadPointerIdRef.current === e.pointerId) {
      seekFromPointer(e.clientX);
    }
    if (!dragging || !dragStartRef.current || e.pointerId !== dragStartRef.current.pointerId) return;
    const timeline = timelineRef.current;
    if (!timeline) return;
    const rect = timeline.getBoundingClientRect();
    const dx = e.clientX - dragStartRef.current.pointerX;
    const dMs = (dx / rect.width) * totalDurationMs;
    let draftStart = dragging.segStart;
    let draftEnd = dragging.segEnd;

    if (dragging.handle === "left") {
      draftStart = Math.max(0, Math.min(dragging.segEnd - MIN_SEGMENT_DURATION_MS, Math.round(dragging.segStart + dMs)));
    } else {
      draftEnd = Math.min(totalDurationMs, Math.max(dragging.segStart + MIN_SEGMENT_DURATION_MS, Math.round(dragging.segEnd + dMs)));
    }
    setDragging((current) => current ? { ...current, draftStart, draftEnd } : current);
  }, [dragging, seekFromPointer, totalDurationMs]);

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (playheadPointerIdRef.current === e.pointerId) {
      suppressClickRef.current = true;
      playheadPointerIdRef.current = null;
      setPlayheadDragging(false);
    }
    if (dragging && dragStartRef.current && e.pointerId === dragStartRef.current.pointerId) {
      suppressClickRef.current = true;
      if (dragging.draftStart !== dragging.segStart || dragging.draftEnd !== dragging.segEnd) {
        void onBoundaryChange(dragging.segId, dragging.draftStart, dragging.draftEnd, dragging.expectedVersion);
      }
      setDragging(null);
      dragStartRef.current = null;
    }
  }, [dragging, onBoundaryChange]);

  const handlePointerCancel = useCallback((e: React.PointerEvent) => {
    if (playheadPointerIdRef.current === e.pointerId) {
      suppressClickRef.current = true;
      playheadPointerIdRef.current = null;
      setPlayheadDragging(false);
    }
    if (dragging && dragStartRef.current && e.pointerId === dragStartRef.current.pointerId) {
      // A cancelled boundary gesture must not persist the in-progress draft.
      suppressClickRef.current = true;
      setDragging(null);
      dragStartRef.current = null;
    }
  }, [dragging]);

  const handlePlayheadPointerDown = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    playheadPointerIdRef.current = e.pointerId;
    setPlayheadDragging(true);
    seekFromPointer(e.clientX);
  }, [seekFromPointer]);

  const handleTimelineClick = useCallback((e: React.MouseEvent) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
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
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
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
                  const draft = dragging?.segId === seg.id ? dragging : null;
                  const s = draft?.draftStart ?? seg.effective_start_ms ?? seg.start_ms;
                  const e = draft?.draftEnd ?? seg.effective_end_ms ?? seg.end_ms ?? totalDurationMs;
                  const isSuperseded = seg.edit_status === "superseded";
                  const isOpen = seg.status === "open";
                  const isActive = activeSegmentId === seg.id;
                  const isSaving = savingSegmentId === seg.id;
                  return (
                    <div
                      key={seg.id}
                      className={`absolute top-0 h-full rounded-md border transition-opacity ${isActive ? "ring-2 ring-offset-1 ring-[#14241B] z-10" : ""} ${isSuperseded ? "opacity-30 border-dashed" : isOpen ? "opacity-100 animate-pulse" : isSaving ? "opacity-50" : "opacity-80"}`}
                      style={{
                        left: scale(s),
                        width: `calc(${scale(Math.max(s, e))} - ${scale(s)})`,
                        backgroundColor: `${track.color}20`,
                        borderColor: track.color,
                        borderWidth: 1.5,
                        cursor: isSuperseded || isSaving ? "default" : "pointer",
                      }}
                      title={`${seg.label}: ${(s / 1000).toFixed(1)}s → ${(e / 1000).toFixed(1)}s`}
                      onClick={(event) => {
                        event.stopPropagation();
                        if (suppressClickRef.current) {
                          suppressClickRef.current = false;
                          return;
                        }
                        if (!isSuperseded) onSegmentClick?.(seg.id, s);
                      }}
                    >
                      {!isSuperseded && !isOpen && (
                        <>
                          <div
                            className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-black/20 z-10"
                            onPointerDown={(ev) => handlePointerDown(ev, seg, "left")}
                          />
                          <div
                            className="absolute right-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-black/20 z-10"
                            onPointerDown={(ev) => handlePointerDown(ev, seg, "right")}
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
          <button
            type="button"
            aria-label="拖拽视频播放头"
            title="拖拽调整视频播放位置"
            className={`absolute -top-1 -left-1.5 h-3 w-3 rounded-full bg-red-500 pointer-events-auto ${playheadDragging ? "ring-2 ring-red-200" : "cursor-ew-resize"}`}
            onPointerDown={handlePlayheadPointerDown}
          />
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
