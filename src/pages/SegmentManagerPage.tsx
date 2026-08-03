import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Play, Scissors, Combine, Archive, RotateCcw } from "lucide-react";
import type { AppPath, CaptureSegmentSummary, CaptureTakeSummary, SessionTimelineEvent } from "../types/report";
import { getCaptureTake, listSegments, patchSegment, splitSegment, mergeSegments, archiveSegment, restoreSegment, createAnalysisBatch, listTimelineEvents } from "../services/analysisClient";
import { SegmentVideoPlayer, type SegmentVideoPlayerHandle } from "../components/SegmentVideoPlayer";
import { EditableSegmentTimeline } from "../components/EditableSegmentTimeline";

type NavigateFn = (path: AppPath | `/capture/${string}`) => void;
type FilterType = "all" | "set" | "game" | "rally";

export function SegmentManagerPage({
  fieldSessionId,
  takeId,
  onNavigate,
}: {
  fieldSessionId: string;
  takeId: string;
  onNavigate: NavigateFn;
}) {
  const [take, setTake] = useState<CaptureTakeSummary | null>(null);
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const [events, setEvents] = useState<SessionTimelineEvent[]>([]);
  const [filter, setFilter] = useState<FilterType>("rally");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editingLabel, setEditingLabel] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const playerRef = useRef<SegmentVideoPlayerHandle>(null);

  const videoUrl = `/api/videos/${take?.source_session_id ?? ""}/stream`;

  const loadData = useCallback(async () => {
    try {
      const [t, segs, evts] = await Promise.all([
        getCaptureTake(takeId),
        listSegments(takeId),
        listTimelineEvents(fieldSessionId, { capture_take_id: takeId }),
      ]);
      setTake(t);
      setSegments(segs ?? []);
      setEvents(evts ?? []);
    } catch { /* ignore */ }
  }, [takeId, fieldSessionId]);

  useEffect(() => {
    // Load the selected CaptureTake and its derived timeline data.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes async API results.
    void loadData();
  }, [loadData]);

  const filteredSegments = useMemo(() => {
    const active = segments.filter(s => s.edit_status !== "superseded");
    return filter === "all" ? active : active.filter(s => s.segment_type === filter);
  }, [segments, filter]);

  const timelineTotalMs = useMemo(() => {
    const max = segments.reduce((m, s) => Math.max(m, s.effective_end_ms ?? s.end_ms ?? 0), 0);
    return Math.max(max, 60000);
  }, [segments]);

  const handleSegmentClick = (seg: CaptureSegmentSummary) => {
    playerRef.current?.seekToTakeTime(seg.effective_start_ms ?? seg.start_ms);
  };

  const handleSegmentDoubleClick = (seg: CaptureSegmentSummary) => {
    const end = seg.effective_end_ms ?? seg.end_ms;
    if (end) playerRef.current?.playSegment(seg.effective_start_ms ?? seg.start_ms, end);
  };

  const handleTimelineSeek = (ms: number) => {
    playerRef.current?.seekToTakeTime(ms);
  };

  const handleSaveLabel = async (seg: CaptureSegmentSummary, label: string) => {
    setSaveStatus("saving");
    try {
      await patchSegment(seg.id, { label, expected_version: seg.edit_version });
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 1500);
      await loadData();
    } catch {
      setSaveStatus("error");
    }
    setEditingLabel(null);
  };

  const handleSplit = async (seg: CaptureSegmentSummary) => {
    const ms = seg.effective_start_ms ?? seg.start_ms + 3000;
    try {
      await splitSegment(seg.id, ms);
      await loadData();
    } catch { /* ignore */ }
  };

  const handleMerge = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length !== 2) return;
    try {
      await mergeSegments(ids as [string, string]);
      setSelectedIds(new Set());
      await loadData();
    } catch { /* ignore */ }
  };

  const handleArchive = async (seg: CaptureSegmentSummary) => {
    try {
      await archiveSegment(seg.id);
      await loadData();
    } catch { /* ignore */ }
  };

  const handleRestore = async (seg: CaptureSegmentSummary) => {
    try {
      await restoreSegment(seg.id);
      await loadData();
    } catch { /* ignore */ }
  };

  const handleCreateAnalysis = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      const result = await createAnalysisBatch(takeId, ids);
      alert(`已创建分析批次: ${result.batch_id}\n${result.items.length} 个任务已排队`);
      setSelectedIds(new Set());
    } catch (error: unknown) {
      alert(`创建失败: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (!take) return <div className="p-8 text-slate-400">加载中...</div>;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button className="text-sm text-[#2F80ED] flex items-center gap-1" onClick={() => onNavigate(`/capture/${fieldSessionId}`)}>
          <ArrowLeft size={16} /> 返回采集任务
        </button>
        <h2 className="text-lg font-bold text-[#14241B]">片段管理</h2>
        <div className="flex items-center gap-2">
          {saveStatus === "saving" && <span className="text-xs text-[#E8A838]">保存中...</span>}
          {saveStatus === "saved" && <span className="text-xs text-[#22C55E]">已保存</span>}
          {saveStatus === "error" && <span className="text-xs text-[#EF4444]">保存失败</span>}
          <button
            className="green-button inline-flex items-center gap-2 px-4 py-2 text-sm"
            disabled={selectedIds.size === 0}
            onClick={handleCreateAnalysis}
          >
            <Play size={16} /> 创建分析 ({selectedIds.size})
          </button>
        </div>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-[1fr_320px] gap-4">
        {/* Player */}
        <SegmentVideoPlayer
          ref={playerRef}
          videoUrl={videoUrl}
          fps={take.capture_mode === "dual" ? 30 : 30}
          onTimeUpdate={() => { /* timeline sync */ }}
        />

        {/* Segment list */}
        <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4 max-h-[500px] overflow-y-auto">
          <div className="flex gap-2 mb-3">
            {(["all", "set", "game", "rally"] as FilterType[]).map(f => (
              <button
                key={f}
                className={`text-xs px-3 py-1 rounded-full font-bold transition ${filter === f ? "bg-[#2F80ED] text-white" : "bg-slate-100 text-slate-500"}`}
                onClick={() => { setFilter(f); setSelectedIds(new Set()); }}
              >
                {{ all: "全部", set: "盘", game: "局", rally: "分" }[f]}
              </button>
            ))}
          </div>

          {filteredSegments.map(seg => (
            <div
              key={seg.id}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-sm border mb-1 transition ${
                selectedIds.has(seg.id) ? "border-[#22C55E] bg-[#F0FDF4]" : "border-transparent hover:bg-slate-50"
              }`}
              onClick={() => handleSegmentClick(seg)}
              onDoubleClick={() => handleSegmentDoubleClick(seg)}
            >
              <input
                type="checkbox"
                className="size-3.5 accent-[#22C55E] shrink-0"
                checked={selectedIds.has(seg.id)}
                onChange={(e) => { e.stopPropagation(); toggleSelect(seg.id); }}
                onClick={(e) => e.stopPropagation()}
              />
              {editingLabel === seg.id ? (
                <input
                  className="flex-1 text-xs border rounded px-1"
                  defaultValue={seg.label}
                  onBlur={(e) => handleSaveLabel(seg, e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSaveLabel(seg, (e.target as HTMLInputElement).value); }}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span
                  className="flex-1 font-medium text-[#14241B] text-xs truncate"
                  onDoubleClick={(e) => { e.stopPropagation(); setEditingLabel(seg.id); }}
                >
                  {seg.label}
                </span>
              )}
              <span className="text-[10px] text-slate-400 tabular-nums shrink-0">
                {formatMs(seg.effective_start_ms ?? seg.start_ms)}→{seg.effective_end_ms != null ? formatMs(seg.effective_end_ms) : "?"}
              </span>
              <div className="flex gap-0.5 shrink-0">
                {seg.segment_type === "rally" && (
                  <>
                    <button className="p-0.5 hover:bg-slate-200 rounded" title="拆分" onClick={(e) => { e.stopPropagation(); handleSplit(seg); }}><Scissors size={12} /></button>
                    {selectedIds.size === 2 && selectedIds.has(seg.id) && (
                      <button className="p-0.5 hover:bg-slate-200 rounded text-[#22C55E]" title="合并选中" onClick={(e) => { e.stopPropagation(); handleMerge(); }}><Combine size={12} /></button>
                    )}
                  </>
                )}
                <button className="p-0.5 hover:bg-slate-200 rounded" title="归档" onClick={(e) => { e.stopPropagation(); handleArchive(seg); }}><Archive size={12} /></button>
                {seg.edit_status === "archived" && (
                  <button className="p-0.5 hover:bg-slate-200 rounded text-[#22C55E]" title="恢复" onClick={(e) => { e.stopPropagation(); handleRestore(seg); }}><RotateCcw size={12} /></button>
                )}
              </div>
            </div>
          ))}

          {selectedIds.size === 2 && filter === "rally" && (
            <button className="w-full mt-2 text-xs bg-[#22C55E]/10 border border-[#22C55E] text-[#22C55E] rounded-lg py-1.5 font-bold hover:bg-[#22C55E]/20 transition" onClick={handleMerge}>
              <Combine size={14} className="inline mr-1" /> 合并选中的 2 个 Rally
            </button>
          )}
        </div>
      </div>

      {/* Timeline */}
      <EditableSegmentTimeline
        segments={segments}
        events={events}
        totalDurationMs={timelineTotalMs}
        currentTimeMs={0}
        onSeek={handleTimelineSeek}
        onBoundaryChange={async (segId, startMs, endMs) => {
          setSaveStatus("saving");
          try {
            await patchSegment(segId, { corrected_start_ms: startMs, corrected_end_ms: endMs });
            setSaveStatus("saved");
            setTimeout(() => setSaveStatus("idle"), 1500);
            await loadData();
          } catch { setSaveStatus("error"); }
        }}
      />
    </div>
  );
}

function formatMs(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
