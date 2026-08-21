import { useEffect, useState, type ReactNode } from "react";
import { Activity, Camera } from "lucide-react";
import type { SyncRecordingSession } from "../types/report";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { taskListPath, withTaskListContext } from "../app/navigationContext";
import type { CalibrationPointDraft } from "../components/platform/CourtCornerCalibrator";
import { CourtCornerCalibrator } from "../components/platform/CourtCornerCalibrator";
import { PageFrame } from "../components/PageFrame";
import {
  getSyncRecording,
  getVideoStreamUrl,
  createAnalysisJob,
} from "../services/analysisClient";

// ── Types ───────────────────────────────────────────────────────────────────

interface RecordingAnalyzePageProps {
  sessionId: string;
  cam: "cam_1" | "cam_2" | null;
  onNavigate: NavigateFn;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</span>
      <span className="text-sm font-semibold text-[#14241B]">{value}</span>
    </div>
  );
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

// ── Component ───────────────────────────────────────────────────────────────

export function RecordingAnalyzePage({ sessionId, cam, onNavigate }: RecordingAnalyzePageProps) {
  const [session, setSession] = useState<SyncRecordingSession | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<{ title: string; body: string } | null>(null);

  // ── Load session ────────────────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    getSyncRecording(sessionId)
      .then((s) => {
        if (!cancelled) setSession(s);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "加载录制信息失败");
      });
    return () => { cancelled = true; };
  }, [sessionId]);

  // ── Derived data ────────────────────────────────────────────────────────

  const camSlot = cam ?? "cam_1";
  const taskContext = { source: "recorded" as const, sessionId, cameraSlot: cam ?? undefined };
  const returnParam = new URLSearchParams(window.location.search).get("return");
  const taskReturnPath = taskListPath(taskContext);
  // 从 Library 进入时优先回到来源工作区，否则回录制任务列表
  const goReturn = () => onNavigate((returnParam ?? taskReturnPath) as NavigatePath);
  const videoId = session?.registered_video_ids?.[camSlot];
  const videoSrc = videoId ? (getVideoStreamUrl(videoId) ?? undefined) : undefined;

  // ── Submit handler ──────────────────────────────────────────────────────

  const handleCalibrationComplete = async (calibrationId: string, points: CalibrationPointDraft[]) => {
    if (!session || !videoId) return;
    void points;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const angleMap: Record<string, "baseline" | "sideline" | "elevated" | "unknown"> = {
        baseline_high: "baseline",
        baseline: "baseline",
        sideline: "sideline",
        elevated: "elevated",
        side: "sideline",
        overhead: "elevated",
        unknown: "unknown",
      };

      const cameraAngle: "baseline" | "sideline" | "elevated" | "unknown" =
        session.camera_slots?.[camSlot]?.camera_angle
          ? angleMap[session.camera_slots[camSlot].camera_angle] ?? "unknown"
          : "unknown";

      const job = await createAnalysisJob({
        metadata: {
          fileName: `${session.court_name || "录制比赛"}_${camSlot}.mp4`,
          fileSize: undefined,
          sourceFps: session.fps || 60,
          matchTitle: `${session.court_name || "录制比赛"} ${formatDate(session.started_at)}`,
          venue: session.court_name || "未知球场",
          matchDate: session.started_at ? new Date(session.started_at).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10),
          matchFormat: session.match_format === "singles" ? "singles" : "doubles",
          cameraAngle,
          athleteLabel: "球���采集",
          level: "大众进阶",
          recording_session_id: sessionId,
          camera_slot: camSlot,
        },
        videoId,
        calibrationId,
        frameStride: 2,
        priority: 0,
        recordingSessionId: sessionId,
        cameraSlot: camSlot,
      });

      onNavigate(withTaskListContext(`/analysis/${job.id}`, taskContext));
    } catch (err) {
      setSubmitError({
        title: "分析任务创建失败",
        body: err instanceof Error ? err.message : "请检查后端连接后重试。",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // ── Error / loading states ──────────────────────────────────────────────

  if (loadError) {
    return (
      <PageFrame>
        <div className="mx-auto mt-20 max-w-md text-center">
          <div className="rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-6">
            <strong className="text-[#991B1B]">加载失败</strong>
            <p className="mt-2 text-sm text-[#B91C1C]">{loadError}</p>
          </div>
          <button
            className="quiet-button mt-4 px-4 py-2 text-sm"
            onClick={() => goReturn()}
            type="button"
          >
            返回任务列表
          </button>
        </div>
      </PageFrame>
    );
  }

  if (!session) {
    return (
      <PageFrame>
        <div className="mx-auto mt-20 max-w-md text-center">
          <div className="rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-6">
            <p className="text-sm text-slate-500">正在加载录制信息…</p>
          </div>
        </div>
      </PageFrame>
    );
  }

  if (!videoId || !videoSrc) {
    return (
      <PageFrame>
        <div className="mx-auto mt-20 max-w-md text-center">
          <div className="rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-6">
            <strong className="text-[#991B1B]">视频未就绪</strong>
            <p className="mt-2 text-sm text-[#B91C1C]">
              {camSlot === "cam_1" ? "A" : "B"} 机位的视频尚未合并完成。请先在任务管理中合并视频片段。
            </p>
          </div>
          <button
            className="quiet-button mt-4 px-4 py-2 text-sm"
            onClick={() => goReturn()}
            type="button"
          >
            返回任务列表
          </button>
        </div>
      </PageFrame>
    );
  }

  // ── Main render ──────────────────────────────────────────────────────────

  return (
    <PageFrame>
      <section className="mx-auto max-w-5xl">
        {/* Header */}
        <div className="mb-6">
          <button className="quiet-button mb-4 px-3 py-2 text-sm" onClick={() => goReturn()} type="button">
            返回录制任务
          </button>
          <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-[#22C55E]/15 text-[#168A34]">
            <Camera size={20} aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-black text-[#14241B]">从录制创建分析任务</h1>
            <p className="mt-0.5 text-sm text-slate-500">
              {camSlot === "cam_1" ? "底线 A 机位" : "底线 B 机位"} · 场地信息已锁定
            </p>
          </div>
          </div>
        </div>

        {/* Read-only metadata banner */}
        <div className="mb-6 rounded-3xl border border-[#DDE9D6] bg-white/70 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={16} className="text-[#168A34]" aria-hidden="true" />
            <span className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">
              录制信息（只读）
            </span>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
            <InfoRow label="场地" value={session.court_name || "—"} />
            <InfoRow label="比赛日期" value={formatDate(session.started_at)} />
            <InfoRow label="帧率" value={`${session.fps || "—"} fps`} />
            <InfoRow label="赛制" value={session.match_format === "singles" ? "单打" : "双打"} />
            <InfoRow label="分析机位" value={camSlot === "cam_1" ? "底线 A" : "底线 B"} />
            <InfoRow
              label="录制时长"
              value={session.duration_sec != null ? `${Math.round(session.duration_sec)} 秒` : "—"}
            />
          </div>
        </div>

        {/* Calibration */}
        <CourtCornerCalibrator
          videoSrc={videoSrc}
          videoId={videoId}
          onComplete={handleCalibrationComplete}
          onCancel={() => goReturn()}
          isSubmitting={isSubmitting}
        />

        {/* Submit error */}
        {submitError && (
          <div className="mt-4 rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-4">
            <strong className="block text-sm text-[#991B1B]">{submitError.title}</strong>
            <p className="mt-1 text-sm text-[#B91C1C]">{submitError.body}</p>
          </div>
        )}
      </section>
    </PageFrame>
  );
}
