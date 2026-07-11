import { Camera, LayoutDashboard, Play, Trash2 } from "lucide-react";
import type { AppPath, RecordingSession } from "../../types/report";
import { deleteRecording } from "../../services/analysisClient";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

export function RecordingTaskCard({
  session,
  onNavigate,
  onRefresh,
  onPlay,
  selectable = false,
  selected = false,
  onToggleSelect,
}: {
  session: RecordingSession;
  onNavigate: NavigateFn;
  onRefresh: () => void;
  onPlay: (session: RecordingSession) => void;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (sessionId: string) => void;
}) {
  const isPlayable = session.status === "completed" && !!session.video_id;
  const hasAnalysis = !!session.auto_analysis_job_id;

  const statusLabel = (status: string) => {
    const map: Record<string, string> = { recording: "录制中", completed: "已完成", failed: "失败", canceled: "已取消" };
    return map[status] ?? status;
  };
  const statusColor = (status: string) => {
    const map: Record<string, string> = { recording: "text-red-500 bg-red-50", completed: "text-green-600 bg-green-50", failed: "text-orange-500 bg-orange-50", canceled: "text-gray-400 bg-gray-50" };
    return map[status] ?? "text-gray-500 bg-gray-50";
  };

  const handleDelete = async () => {
    if (!window.confirm(`确定删除录制「${session.session_id}」吗？`)) return;
    try {
      await deleteRecording(session.session_id);
      onRefresh();
    } catch {
      // silent
    }
  };

  return (
    <article className={`sport-card p-5 sm:p-6 ${selected ? "border-[#22C55E]/50 ring-1 ring-[#22C55E]/20" : ""}`}>
      <div className="grid gap-5 lg:grid-cols-[1fr_0.38fr] lg:items-center">
        <div className="flex items-start gap-3">
          {selectable && (
            <input
              type="checkbox"
              checked={selected}
              className="mt-1 size-4 shrink-0 accent-[#22C55E]"
              onChange={() => onToggleSelect?.(session.session_id)}
            />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="inline-flex items-center gap-1 text-xs font-bold text-slate-500">
                <Camera size={12} /> 录制视频
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-black ${statusColor(session.status)}`}>{statusLabel(session.status)}</span>
              {hasAnalysis && <span className="rounded-full border border-[#22C55E]/30 bg-[#22C55E]/8 px-3 py-1 text-xs font-bold text-[#168A34]">已分析</span>}
              {session.duration_sec ? <span className="text-xs text-slate-400">{session.duration_sec.toFixed(0)}秒</span> : null}
            </div>
            <h4 className="text-lg font-black text-[#14241B]">{session.court_name || session.session_id}</h4>
            <p className="mt-1 text-xs text-slate-400">
              {session.camera_id} · {session.camera_angle ?? "未知角度"} · {session.match_format === "doubles" ? "双打" : "单打"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          {isPlayable && (
            <button className="quiet-button px-3 py-2 text-xs" onClick={() => onPlay(session)} type="button">
              <Play size={12} className="inline mr-1" />查看视频
            </button>
          )}
          {session.status === "completed" && (
            <button className="quiet-button px-3 py-2 text-xs" onClick={() => onNavigate(`/recording/${session.session_id}`)} type="button">
              <LayoutDashboard size={12} className="inline mr-1" />工作台
            </button>
          )}
          {isPlayable && !hasAnalysis && (
            <button className="green-button px-3 py-2 text-xs" onClick={() => onNavigate(`/analysis/new?videoId=${session.video_id}&source=recording&sessionId=${session.session_id}`)} type="button">
              开始分析
            </button>
          )}
          {hasAnalysis && (
            <button className="green-button px-3 py-2 text-xs" onClick={() => onNavigate(`/analysis/${session.auto_analysis_job_id}`)} type="button">
              查看分析结果
            </button>
          )}
          {session.status !== "recording" && (
            <button className="quiet-button px-3 py-2 text-xs text-[#C92A2A]" onClick={handleDelete} type="button">
              <Trash2 size={12} className="inline mr-1" />删除
            </button>
          )}
          {session.status === "recording" && (
            <span className="text-xs text-slate-400">录制进行中...</span>
          )}
          {!isPlayable && session.status !== "recording" && (
            <span className="text-xs text-slate-400">{session.status === "failed" ? `失败: ${session.error_message ?? "未知错误"}` : "视频未注册"}</span>
          )}
        </div>
      </div>
    </article>
  );
}
