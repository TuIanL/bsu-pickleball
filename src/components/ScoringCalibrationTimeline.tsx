import type { ReactNode } from "react";
import type { CaptureSegmentSummary } from "../types/report";
import type {
  ScoringCalibrationAnnotation,
  ScoringCalibrationCandidate,
} from "../types/scoringCalibrationAnnotation";

interface ScoringCalibrationTimelineProps {
  segments: CaptureSegmentSummary[];
  annotations: ScoringCalibrationAnnotation[];
  candidates: ScoringCalibrationCandidate[];
  totalDurationMs: number;
  currentTimeMs: number;
  selectedAnnotationId?: string | null;
  selectedCandidateId?: string | null;
  onSeek: (timestampMs: number) => void;
  onSelectAnnotation: (annotation: ScoringCalibrationAnnotation) => void;
  onSelectCandidate: (candidate: ScoringCalibrationCandidate) => void;
}

export function ScoringCalibrationTimeline({
  segments,
  annotations,
  candidates,
  totalDurationMs,
  currentTimeMs,
  selectedAnnotationId,
  selectedCandidateId,
  onSeek,
  onSelectAnnotation,
  onSelectCandidate,
}: ScoringCalibrationTimelineProps) {
  const scale = (ms: number) => `${(Math.max(0, Math.min(ms, totalDurationMs)) / Math.max(totalDurationMs, 1)) * 100}%`;
  const rallies = segments.filter((segment) => segment.segment_type === "rally" && segment.edit_status !== "superseded");

  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-bold text-[#14241B]">标注时间线</h3>
        <span className="text-[11px] text-slate-400">候选 {candidates.length} · 人工 {annotations.length}</span>
      </div>
      <div
        className="relative select-none space-y-2"
        onClick={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          onSeek(Math.round(((event.clientX - rect.left) / rect.width) * totalDurationMs));
        }}
      >
        <TimelineRow label="回合" color="#22C55E">
          {rallies.map((segment) => {
            const start = segment.effective_start_ms ?? segment.start_ms;
            const end = segment.effective_end_ms ?? segment.end_ms ?? start + 500;
            return (
              <div
                key={segment.id}
                className="absolute top-0 h-6 rounded border border-[#22C55E] bg-[#22C55E]/15 text-[9px] font-bold text-[#15803D]"
                style={{ left: scale(start), width: `calc(${scale(Math.max(start, end))} - ${scale(start)})` }}
                title={`${segment.label || `回合 ${segment.ordinal}`} ${formatMs(start)}→${formatMs(end)}`}
              >
                <span className="px-1 leading-6">{segment.label || segment.ordinal}</span>
              </div>
            );
          })}
        </TimelineRow>
        <TimelineRow label="候选" color="#8B5CF6">
          {candidates.map((candidate) => (
            <button
              key={candidate.candidate_id}
              type="button"
              className={`absolute top-1 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-white shadow ${candidate.decision === "rejected" ? "bg-slate-300" : selectedCandidateId === candidate.candidate_id ? "bg-[#F97316] ring-2 ring-[#F97316]/30" : "bg-[#8B5CF6]"}`}
              style={{ left: scale(candidate.timestamp_ms) }}
              title={`算法候选 ${formatMs(candidate.timestamp_ms)}`}
              onClick={(event) => { event.stopPropagation(); onSelectCandidate(candidate); }}
            />
          ))}
        </TimelineRow>
        <TimelineRow label="人工" color="#2F80ED">
          {annotations.map((annotation) => (
            <button
              key={annotation.id}
              type="button"
              className={`absolute top-0 h-6 w-1.5 rounded ${selectedAnnotationId === annotation.id ? "bg-[#EF4444] ring-2 ring-[#EF4444]/30" : annotation.decision === "unreviewed" ? "bg-[#F59E0B]" : "bg-[#2F80ED]"}`}
              style={{ left: scale(annotation.event_ms) }}
              title={`人工标注 ${formatMs(annotation.event_ms)}`}
              onClick={(event) => { event.stopPropagation(); onSelectAnnotation(annotation); }}
            />
          ))}
        </TimelineRow>
        <div className="pointer-events-none absolute bottom-0 top-0 w-0.5 bg-red-500" style={{ left: scale(currentTimeMs) }} />
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-slate-400">
        <span>0:00</span>
        <span>{formatMs(totalDurationMs / 2)}</span>
        <span>{formatMs(totalDurationMs)}</span>
      </div>
    </div>
  );
}

function TimelineRow({ label, color, children }: { label: string; color: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-8 shrink-0 text-right text-[11px] font-bold" style={{ color }}>{label}</span>
      <div className="relative h-7 flex-1 rounded bg-slate-100">{children}</div>
    </div>
  );
}

function formatMs(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
