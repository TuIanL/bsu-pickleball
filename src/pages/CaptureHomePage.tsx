import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Camera,
  CheckCircle2,
  Clock,
  MapPin,
  PlusCircle,
  Trash2,
  Users,
} from "lucide-react";
import type { AppPath } from "../types/report";
import type { FieldSession } from "../types/report";
import { completeFieldSession, deleteFieldSession, listFieldSessions } from "../services/analysisClient";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

const captureModeLabel: Record<string, string> = {
  practice: "自由练习",
  match: "记分比赛",
  engineering: "工程测试",
};

const matchFormatLabel: Record<string, string> = {
  singles: "单打",
  doubles: "双打",
};

const statusLabel: Record<string, string> = {
  planned: "待开始",
  live: "进行中",
  completed: "已完成",
  archived: "已归档",
};

const statusStyle: Record<string, string> = {
  planned: "bg-slate-100 text-slate-600",
  live: "bg-[#22C55E]/12 text-[#168A34]",
  completed: "bg-[#2F80ED]/12 text-[#1E63B6]",
  archived: "bg-slate-100 text-slate-400",
};

export function CaptureHomePage({ onNavigate }: { onNavigate: NavigateFn }) {
  const [fieldSessions, setFieldSessions] = useState<FieldSession[]>([]);
  const [loading, setLoading] = useState(true);

  const loadSessions = useCallback(async () => {
    try {
      setLoading(true);
      const sessions = await listFieldSessions();
      setFieldSessions(sessions);
    } catch {
      setFieldSessions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleComplete = async (e: React.MouseEvent, id: string, title: string) => {
    e.stopPropagation();
    if (!window.confirm(`确定完成采集任务「${title || id}」吗？完成后将无法继续录制。`)) return;
    try {
      await completeFieldSession(id);
      await loadSessions();
    } catch {
      alert("完成任务失败，请刷新后重试");
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string, title: string) => {
    e.stopPropagation();
    if (!window.confirm(`确定删除采集任务「${title || id}」吗？`)) return;
    try {
      await deleteFieldSession(id);
      await loadSessions();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "删除失败，请刷新后重试";
      alert(msg);
    }
  };

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  return (
    <div className="mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 py-10 lg:py-12">
      {/* 标题区 */}
      <div className="mb-8">
        <h1 className="text-4xl font-black text-[#14241B]">现场采集</h1>
        <p className="mt-2 text-lg text-slate-600">
          创建一次新的球场采集任务，系统会记录摄像头、场地、比赛模式和录制视频。
        </p>
      </div>

      {/* 主按钮 */}
      <button
        className="green-button inline-flex items-center gap-2 px-6 py-3.5 text-base mb-10"
        onClick={() => onNavigate("/capture/new")}
        type="button"
      >
        <PlusCircle size={18} aria-hidden="true" />
        新建采集任务
      </button>

      {/* 最近采集任务 */}
      <div>
        <h2 className="text-lg font-bold text-[#14241B] mb-4">最近采集任务</h2>

        {loading ? (
          <p className="text-sm text-slate-400">加载中…</p>
        ) : fieldSessions.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#DDE9D6] p-12 text-center">
            <Camera size={32} className="mx-auto text-slate-300 mb-3" />
            <p className="text-sm text-slate-400">还没有采集任务</p>
            <p className="text-xs text-slate-300 mt-1">点击上方按钮创建第一次现场采集</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {fieldSessions.map((session) => (
              <button
                key={session.id}
                className="sport-card group flex items-center gap-6 p-5 text-left transition hover:-translate-y-0.5 hover:border-[#22C55E]/35"
                onClick={() => onNavigate(`/capture/${session.id}`)}
                type="button"
              >
                <div className="grid size-12 shrink-0 place-items-center rounded-xl bg-[#22C55E]/10 text-[#168A34]">
                  <Camera size={20} aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <strong className="block text-base font-black text-[#14241B] truncate">
                    {session.title || "未命名采集任务"}
                  </strong>
                  <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                    {session.court_name && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin size={12} /> {session.court_name}
                      </span>
                    )}
                    {session.match_format && (
                      <span className="inline-flex items-center gap-1">
                        <Users size={12} /> {matchFormatLabel[session.match_format] ?? session.match_format}
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1">
                      <Clock size={12} /> {new Date(session.created_at).toLocaleDateString("zh-CN")}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {session.capture_mode && (
                    <span className="text-xs font-medium text-slate-500">
                      {captureModeLabel[session.capture_mode] ?? session.capture_mode}
                    </span>
                  )}
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${statusStyle[session.status] ?? "bg-slate-100 text-slate-500"}`}>
                    {statusLabel[session.status] ?? session.status}
                  </span>
                  {session.status === "live" && (
                    <button
                      className="quiet-button px-2 py-1 text-xs text-[#168A34] opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => handleComplete(e, session.id, session.title)}
                      type="button"
                    >
                      <CheckCircle2 size={12} className="inline mr-1" />完成任务
                    </button>
                  )}
                  <button
                    className="quiet-button px-2 py-1 text-xs text-[#C92A2A] opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => handleDelete(e, session.id, session.title)}
                    type="button"
                  >
                    <Trash2 size={12} className="inline mr-1" />删除
                  </button>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
