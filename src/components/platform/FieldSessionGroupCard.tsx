import { useState } from "react";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import type { AppPath, FieldSession, RecordingSession } from "../../types/report";
import { RecordingTaskCard } from "./RecordingTaskCard";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

interface FieldSessionGroupCardProps {
  fieldSession: FieldSession | null;
  recordings: RecordingSession[];
  onNavigate: NavigateFn;
  onRefresh: () => void;
  onPlay: (session: RecordingSession) => void;
  onDeleteFieldSession?: (session: FieldSession) => void;
}

const STATUS_LABEL: Record<string, string> = {
  planned: "计划中",
  live: "进行中",
  completed: "已完成",
  archived: "已归档",
};

function formatGroupTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function FieldSessionGroupCard({
  fieldSession,
  recordings,
  onNavigate,
  onRefresh,
  onPlay,
  onDeleteFieldSession,
}: FieldSessionGroupCardProps) {
  const [expanded, setExpanded] = useState(true);

  const isUncategorized = fieldSession === null;
  const title = isUncategorized ? "未归类录制" : fieldSession.title || "未命名采集任务";
  const hasRecording = recordings.some((r) => r.status === "recording");
  const latestStartedAt = recordings.reduce<string | undefined>(
    (acc, r) => (!acc || r.started_at > acc ? r.started_at : acc),
    undefined,
  );

  return (
    <section className="overflow-hidden rounded-3xl border border-[#DDE9D6] bg-white/80 shadow-sm">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left transition hover:bg-[#F5FAF1]"
        aria-expanded={expanded}
      >
        <span className="text-[#168A34]">
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-black text-[#14241B]">{title}</h3>
            {hasRecording && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-black text-red-500">
                <span className="size-1.5 rounded-full bg-red-500" />
                录制中
              </span>
            )}
            {!isUncategorized && fieldSession?.status && (
              <span className="rounded-full bg-[#F1F7EC] px-2.5 py-0.5 text-xs font-bold text-slate-500">
                {STATUS_LABEL[fieldSession.status] ?? fieldSession.status}
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-slate-400">
            {isUncategorized
              ? "未关联到任何采集任务的录制"
              : `${fieldSession.venue || "未知场地"} · ${fieldSession.court_name || "未知球场"}`}
            {latestStartedAt ? ` · 最近 ${formatGroupTime(latestStartedAt)}` : ""}
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-[#17231D] px-3 py-1 text-xs font-black text-white">
          {recordings.length} 条
        </span>
        {!isUncategorized && (
          <button
            type="button"
            className="shrink-0 rounded-lg px-2 py-1 text-xs text-[#C92A2A] hover:bg-red-50 transition"
            onClick={(e) => {
              e.stopPropagation();
              if (fieldSession && onDeleteFieldSession) {
                if (!window.confirm(`确定删除采集任务「${fieldSession.title || fieldSession.id}」吗？`)) return;
                onDeleteFieldSession(fieldSession);
              }
            }}
          >
            <Trash2 size={12} className="inline mr-1" />删除
          </button>
        )}
      </button>

      {expanded && (
        <div className="grid gap-3 border-t border-[#DDE9D6] bg-white/60 p-4">
          {recordings.length === 0 ? (
            <p className="px-1 py-3 text-sm text-slate-400">暂无录制</p>
          ) : (
            recordings.map((session) => (
              <RecordingTaskCard
                key={session.session_id}
                session={session}
                onNavigate={onNavigate}
                onRefresh={onRefresh}
                onPlay={onPlay}
              />
            ))
          )}
        </div>
      )}
    </section>
  );
}
