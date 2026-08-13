import { useEffect, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, Bug, Camera, CheckCircle2, Link2, Radio, Settings2, ShieldAlert, Video } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { taskListPath, withTaskListContext } from "../app/navigationContext";
import { CourtCornerCalibrator, type CalibrationPointDraft } from "../components/platform/CourtCornerCalibrator";
import { PageFrame } from "../components/PageFrame";
import {
  createMultiviewAnalysisJob,
  getCaptureTake,
  getSyncAnchorStatus,
  getSyncRecording,
  getVideoStreamUrl,
  isAnalysisApiError,
  type MultiViewCreateViewPayload,
} from "../services/analysisClient";
import type { CaptureTakeSummary, SyncRecordingSession } from "../types/report";
import type { SyncAnchorStatus } from "../types/syncAnchors";

// ── Types ───────────────────────────────────────────────────────────────────

interface MultiViewAnalysisSetupPageProps {
  captureTakeId: string;
  onNavigate: NavigateFn;
}

type SetupStep = 0 | 1 | 2 | 3; // 0 素材检查 · 1 A标定 · 2 B标定 · 3 确认

// ── Helpers ─────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: string }) {
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
    return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  } catch {
    return iso.slice(0, 10);
  }
}

const STEP_LABELS: Array<{ n: number; label: string }> = [
  { n: 1, label: "素材检查" },
  { n: 2, label: "A 机位标定" },
  { n: 3, label: "B 机位标定" },
  { n: 4, label: "确认" },
];

function StepBar({ step }: { step: SetupStep }) {
  return (
    <div className="mb-6 flex items-center gap-2 text-xs font-semibold">
      {STEP_LABELS.map((item, index) => {
        const active = index === step;
        const done = index < step;
        return (
          <div key={item.n} className="flex items-center gap-2">
            <span
              className={
                done
                  ? "grid size-6 place-items-center rounded-full bg-[#22C55E] text-white"
                  : active
                    ? "grid size-6 place-items-center rounded-full bg-[#168A34] text-white"
                    : "grid size-6 place-items-center rounded-full bg-slate-200 text-slate-500"
              }
            >
              {done ? <CheckCircle2 size={14} aria-hidden="true" /> : item.n}
            </span>
            <span className={active ? "text-[#14241B]" : done ? "text-[#168A34]" : "text-slate-400"}>
              {item.label}
            </span>
            {index < STEP_LABELS.length - 1 && <span className="mx-1 h-px w-6 bg-slate-200" />}
          </div>
        );
      })}
    </div>
  );
}

// ── Component ───────────────────────────────────────────────────────────────

export function MultiViewAnalysisSetupPage({ captureTakeId, onNavigate }: MultiViewAnalysisSetupPageProps) {
  const [take, setTake] = useState<CaptureTakeSummary | null>(null);
  const [session, setSession] = useState<SyncRecordingSession | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState<SetupStep>(0);
  const [calibrationA, setCalibrationA] = useState<string | null>(null);
  const [calibrationB, setCalibrationB] = useState<string | null>(null);
  const [calibrationPointsA, setCalibrationPointsA] = useState<CalibrationPointDraft[]>([]);
  const [calibrationPointsB, setCalibrationPointsB] = useState<CalibrationPointDraft[]>([]);
  const [cam1AtEndA, setCam1AtEndA] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<{ title: string; body: string } | null>(null);
  // 分析窗口（take 公共时间轴，秒）；关闭 = 整场分析。双摄不物理裁剪，附加信息天然一致。
  const [clipEnabled, setClipEnabled] = useState(false);
  const [clipStartSec, setClipStartSec] = useState(0);
  const [clipEndSec, setClipEndSec] = useState(60);
  const [debugReplayEnabled, setDebugReplayEnabled] = useState(false);
  const [syncAnchorStatus, setSyncAnchorStatus] = useState<SyncAnchorStatus | null>(null);
  const [syncStatusLoading, setSyncStatusLoading] = useState(true);

  // 路由带 `?session=`（录制卡片传入），缺失时回退到 take.source_session_id 反查
  const routeSessionId = new URLSearchParams(window.location.search).get("session");
  const taskContext = {
    source: "sync_recording" as const,
    sessionId: session?.session_id ?? routeSessionId ?? undefined,
  };
  const taskReturnPath = () => taskListPath(taskContext);

  // ── Load take + source session ────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const takeData = await getCaptureTake(captureTakeId);
        if (cancelled) return;
        setTake(takeData);
        try {
          const status = await getSyncAnchorStatus(captureTakeId);
          if (!cancelled) setSyncAnchorStatus(status);
        } catch {
          if (!cancelled) setSyncAnchorStatus(takeData.sync_anchor_status ?? null);
        } finally {
          if (!cancelled) setSyncStatusLoading(false);
        }

        // 解析双摄源会话：优先路由参数；否则从 take 的 source_session_id 反查。
        // 注意 take id 与 sync 会话 id 不是同一命名空间，不能直接当 session id 用。
        const sourceSessionId = routeSessionId ?? takeData.source_session_id;
        if (!sourceSessionId) {
          if (!cancelled) setSession(null);
          return;
        }
        try {
          const s = await getSyncRecording(sourceSessionId);
          if (!cancelled) setSession(s);
        } catch (err) {
          if (!cancelled) {
            setLoadError(
              err instanceof Error ? err.message : "无法解析双摄同步会话，请确认该录制已完成双摄同步。",
            );
          }
        }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "加载录制信息失败");
        if (!cancelled) setSyncStatusLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [captureTakeId, routeSessionId]);

  // ── Derived data ──────────────────────────────────────────────────────────

  const videoIdA = session?.registered_video_ids?.cam_1;
  const videoIdB = session?.registered_video_ids?.cam_2;
  const cameraIdA = session?.camera_slots?.cam_1?.camera_id ?? "cam_1";
  const cameraIdB = session?.camera_slots?.cam_2?.camera_id ?? "cam_2";
  const videoSrcA = videoIdA ? (getVideoStreamUrl(videoIdA) ?? undefined) : undefined;
  const videoSrcB = videoIdB ? (getVideoStreamUrl(videoIdB) ?? undefined) : undefined;

  const takeCompleted = take?.status === "completed";
  const videosReady = Boolean(videoIdA && videoIdB);
  // 素材就绪只取决于双视频已注册；take.status（如 failed/partial）不作为硬闸——
  // 深层校验（take 目录 / sync / 朝向）由后端 preflight 在启动时执行。
  const manualSyncState = syncAnchorStatus?.state;
  const debugReplayNeedsManualSync = debugReplayEnabled
    && Boolean(manualSyncState)
    && manualSyncState !== "confirmed"
    && manualSyncState !== "not_required";
  const syncReady = !syncStatusLoading
    && Boolean(syncAnchorStatus?.analysis_allowed)
    && !debugReplayNeedsManualSync;
  const allReady = videosReady && syncReady;
  const takeStatusNote = !videosReady
    ? "视频未就绪"
    : takeCompleted
      ? "已录制完成"
      : `视频可用（录制标记 ${take?.status ?? "未知"}）`;

  const syncStatusLabel: Record<SyncAnchorStatus["state"], string> = {
    not_required: "无需人工标注",
    required: "需要标注",
    draft: "草稿未完成",
    confirmed: "人工锚点已确认",
    auto_degraded: "仅自动估算",
    invalidated: "确认已失效",
  };
  const syncLabel = syncStatusLoading
    ? "正在读取录制级同步状态…"
    : syncAnchorStatus
      ? syncStatusLabel[syncAnchorStatus.state]
      : "同步状态不可用";

  // MVP：cam_1（reference view）位于球场哪一端 → identity/rotate_180 相对约定。
  // 精确的 mirror_x/mirror_y 语义 + 安装角色自动推断列为后续 Change。
  const cam1Orientation: MultiViewCreateViewPayload["courtOrientation"] = cam1AtEndA ? "identity" : "rotate_180";
  const cam2Orientation: MultiViewCreateViewPayload["courtOrientation"] = cam1AtEndA ? "rotate_180" : "identity";

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleCalibrationComplete = (slot: "cam_1" | "cam_2") => {
    return (calibrationId: string, points: CalibrationPointDraft[]) => {
      if (slot === "cam_1") {
        setCalibrationA(calibrationId);
        setCalibrationPointsA(points);
        setStep(2);
      } else {
        setCalibrationB(calibrationId);
        setCalibrationPointsB(points);
        setStep(3);
      }
    };
  };

  const handleStart = async () => {
    if (!take || !session || !videoIdA || !videoIdB || !calibrationA || !calibrationB) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const parent = await createMultiviewAnalysisJob({
        metadata: {
          fileName: `${session.court_name || "双摄录制"}_${take.id}.mp4`,
          fileSize: undefined,
          sourceFps: session.fps || 60,
          matchTitle: `${session.court_name || "双摄录制"} ${formatDate(session.started_at)}`,
          venue: session.court_name || "未知球场",
          matchDate: session.started_at ? new Date(session.started_at).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10),
          matchFormat: session.match_format === "singles" ? "singles" : "doubles",
          cameraAngle: "baseline",
          athleteLabel: "球采集",
          level: "大众进阶",
          recording_session_id: take.source_session_id || session.session_id,
          capture_take_id: take.id,
        },
        clipStartMs: clipEnabled ? Math.max(0, Math.round(clipStartSec * 1000)) : undefined,
        clipEndMs: clipEnabled ? Math.max(1, Math.round(clipEndSec * 1000)) : undefined,
        executionMode: debugReplayEnabled ? "joint_tracking_v2" : "late_fusion_v1",
        debugTraceEnabled: debugReplayEnabled,
        referenceViewId: "cam_1",
        views: [
          { viewId: "cam_1", cameraId: cameraIdA, videoId: videoIdA, calibrationId: calibrationA, courtOrientation: cam1Orientation },
          { viewId: "cam_2", cameraId: cameraIdB, videoId: videoIdB, calibrationId: calibrationB, courtOrientation: cam2Orientation },
        ],
        canonicalFrame: {
          endA: cam1AtEndA ? "cam_1_physical_end" : "cam_2_physical_end",
          endB: cam1AtEndA ? "cam_2_physical_end" : "cam_1_physical_end",
        },
      });
      // 只导航到 Parent（用户永不直接进入 child）
      onNavigate(withTaskListContext(`/analysis/${parent.id}`, taskContext));
    } catch (err) {
      const message = isAnalysisApiError(err)
        ? err.backendDetail ?? err.message
        : err instanceof Error
          ? err.message
          : "请检查后端连接后重试。";
      setSubmitError({
        title: "双摄分析启动失败",
        body: message,
      });
      if (/sync|同步|preflight|朝向|双摄素材/i.test(message)) {
        setStep(0);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // ── Error / loading states ─────────────────────────────────────────────────

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
            onClick={() => onNavigate(taskReturnPath())}
            type="button"
          >
            返回双摄任务
          </button>
        </div>
      </PageFrame>
    );
  }

  if (!take || !session) {
    return (
      <PageFrame>
        <div className="mx-auto mt-20 max-w-md text-center">
          <div className="rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-6">
            <p className="text-sm text-slate-500">正在加载双摄素材…</p>
          </div>
        </div>
      </PageFrame>
    );
  }

  // ── Main render ──────────────────────────────────────────────────────────

  return (
    <PageFrame>
      <section className="mx-auto max-w-5xl">
        {/* Header */}
        <button
          className="mb-5 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
          onClick={() => onNavigate(taskReturnPath())}
          type="button"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          返回双摄任务
        </button>
        <div className="mb-6 flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-[#22C55E]/15 text-[#168A34]">
            <Camera size={20} aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-black text-[#14241B]">双摄协同分析</h1>
            <p className="mt-0.5 text-sm text-slate-500">
              {session.court_name || "未知球场"} · {session.match_format === "singles" ? "单打" : "双打"} ·{" "}
              {session.duration_sec != null ? `${Math.round(session.duration_sec)} 秒` : "—"}
            </p>
          </div>
        </div>

        <StepBar step={step} />

        {/* ── Step 0: 素材检查 ── */}
        {step === 0 && (
          <div className="rounded-3xl border border-[#DDE9D6] bg-white/70 p-6">
            <div className="mb-4 flex items-center gap-2">
              <Settings2 size={16} className="text-[#168A34]" aria-hidden="true" />
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">素材与同步检查</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className={`flex items-center gap-3 rounded-2xl border p-4 ${videoIdA ? "border-[#DDE9D6] bg-[#F5FAF1]" : "border-[#FCA5A5] bg-[#FEF2F2]"}`}>
                <Video size={18} className={videoIdA ? "text-[#168A34]" : "text-[#B91C1C]"} aria-hidden="true" />
                <div>
                  <div className="text-sm font-bold text-[#14241B]">A 机位视频</div>
                  <div className="text-xs text-slate-500">{videoIdA ? "已就绪" : "未就绪"}</div>
                </div>
              </div>
              <div className={`flex items-center gap-3 rounded-2xl border p-4 ${videoIdB ? "border-[#DDE9D6] bg-[#F5FAF1]" : "border-[#FCA5A5] bg-[#FEF2F2]"}`}>
                <Video size={18} className={videoIdB ? "text-[#168A34]" : "text-[#B91C1C]"} aria-hidden="true" />
                <div>
                  <div className="text-sm font-bold text-[#14241B]">B 机位视频</div>
                  <div className="text-xs text-slate-500">{videoIdB ? "已就绪" : "未就绪"}</div>
                </div>
              </div>
              <div className={`flex items-center gap-3 rounded-2xl border p-4 ${
                !videosReady
                  ? "border-[#FCA5A5] bg-[#FEF2F2]"
                  : takeCompleted
                    ? "border-[#DDE9D6] bg-[#F5FAF1]"
                    : "border-[#F4D8A8] bg-[#FDF6E7]"
              }`}>
                <Activity size={18} className={!videosReady ? "text-[#B91C1C]" : takeCompleted ? "text-[#168A34]" : "text-[#9A6500]"} aria-hidden="true" />
                <div>
                  <div className="text-sm font-bold text-[#14241B]">录制状态</div>
                  <div className="text-xs text-slate-500">{takeStatusNote}</div>
                </div>
              </div>
              <div className={`flex items-center gap-3 rounded-2xl border p-4 ${syncReady ? "border-[#DDE9D6] bg-[#F5FAF1]" : "border-[#F4D8A8] bg-[#FDF6E7]"}`}>
                <ShieldAlert size={18} className="text-[#168A34]" aria-hidden="true" />
                <div>
                  <div className="text-sm font-bold text-[#14241B]">同步锚点状态</div>
                  <div className="text-xs text-slate-500">{syncLabel}</div>
                </div>
              </div>
            </div>
            {/* 分析窗口：分析级裁剪，不物理切视频 → 双摄时间轴 + 附加信息天然一致 */}
            <div className="mt-4 rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
              <label className="flex cursor-pointer items-center gap-2 text-sm font-bold text-[#14241B]">
                <input
                  checked={clipEnabled}
                  onChange={(e) => setClipEnabled(e.target.checked)}
                  type="checkbox"
                />
                仅分析指定窗口（快速验证短片段）
              </label>
              {clipEnabled && (
                <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                  <span className="text-slate-500">从</span>
                  <input
                    className="w-24 rounded-lg border border-[#D8E5D2] bg-white px-2 py-1.5 text-sm font-semibold text-[#14241B]"
                    max={clipEndSec - 1}
                    min={0}
                    onChange={(e) => setClipStartSec(Math.max(0, Number(e.target.value) || 0))}
                    type="number"
                    value={clipStartSec}
                  />
                  <span className="text-slate-500">到</span>
                  <input
                    className="w-24 rounded-lg border border-[#D8E5D2] bg-white px-2 py-1.5 text-sm font-semibold text-[#14241B]"
                    max={session.duration_sec ?? 3600}
                    min={clipStartSec + 1}
                    onChange={(e) => setClipEndSec(Math.max(clipStartSec + 1, Number(e.target.value) || clipStartSec + 1))}
                    type="number"
                    value={clipEndSec}
                  />
                  <span className="text-slate-500">秒（整场 {session.duration_sec != null ? Math.round(session.duration_sec) : "—"} 秒）</span>
                  <span className="text-xs text-slate-400">双摄自动对齐，无需手动切帧；附加信息保持一致</span>
                </div>
              )}
            </div>
            <label className={`mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition ${debugReplayEnabled ? "border-[#8FD39D] bg-[#EFFAF1]" : "border-[#DDE9D6] bg-white"}`}>
              <input
                aria-label="生成 Debug Replay"
                checked={debugReplayEnabled}
                className="mt-0.5 size-4 accent-[#168A34]"
                onChange={(event) => setDebugReplayEnabled(event.target.checked)}
                type="checkbox"
              />
              <span className="flex items-start gap-2">
                <Bug className="mt-0.5 shrink-0 text-[#168A34]" size={17} aria-hidden="true" />
                <span>
                  <span className="block text-sm font-bold text-[#14241B]">生成 Debug Replay</span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">创建 joint_tracking_v2 任务并保留四联诊断回放；会增加分析耗时和存储占用。</span>
                </span>
              </span>
            </label>
            {!videosReady && (
              <div className="mt-4 rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-4 text-sm text-[#B91C1C]">
                双摄素材尚未全部就绪，无法开始协同分析。请确认双机位视频已合并完成。
              </div>
            )}
            {videosReady && !syncReady && (
              <div className="mt-4 rounded-2xl border border-[#F4D8A8] bg-[#FDF6E7] p-4">
                <div>
                  <div className="text-sm font-bold text-[#14241B]">先完成同步锚点前置检查</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {debugReplayNeedsManualSync
                      ? "Debug Replay 需要人工确认的同步锚点。"
                      : syncAnchorStatus?.reason_codes.join("；") || "当前录制还没有可复用的人工确认。"}
                  </div>
                </div>
                <button className="quiet-button mt-3 px-3 py-2 text-xs" onClick={() => onNavigate(`/sync-calibration?take=${encodeURIComponent(captureTakeId)}&return=${encodeURIComponent(`/capture/takes/${captureTakeId}/analyze`)}`)} type="button">
                  <Link2 size={15} />
                  {syncAnchorStatus?.state === "draft" ? "继续标注" : syncAnchorStatus?.state === "invalidated" ? "重新标注" : "开始标注"}
                </button>
              </div>
            )}
            {syncReady && syncAnchorStatus?.quality && (
              <div className="mt-4 rounded-2xl border border-[#B7E2C1] bg-[#F5FAF1] p-4 text-xs text-[#168A34]">
                来源：{syncAnchorStatus.source === "manual_anchors" ? "人工锚点确认" : "自动估算"} · 锚点 {syncAnchorStatus.quality.anchor_count} 组 · 覆盖率 {(syncAnchorStatus.quality.coverage_ratio * 100).toFixed(1)}% · residual {syncAnchorStatus.quality.residual_rms_ms?.toFixed(2) ?? "—"} ms · 确认时间 {syncAnchorStatus.confirmed_at ? new Date(syncAnchorStatus.confirmed_at).toLocaleString("zh-CN") : "—"}
              </div>
            )}
            {submitError && (
              <div className="mt-4 rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-4">
                <strong className="block text-sm text-[#991B1B]">{submitError.title}</strong>
                <p className="mt-1 text-sm leading-6 text-[#B91C1C]">{submitError.body}</p>
                <button className="quiet-button mt-3 px-3 py-1.5 text-xs" onClick={() => setSubmitError(null)} type="button">
                  重新检查同步
                </button>
              </div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button className="quiet-button px-4 py-2 text-sm" onClick={() => onNavigate(taskReturnPath())} type="button">
                <ArrowLeft size={15} aria-hidden="true" />
                退出向导
              </button>
              <button
                className="green-button px-4 py-2 text-sm disabled:opacity-40"
                disabled={!allReady}
                onClick={() => setStep(1)}
                type="button"
              >
                <ArrowRight size={15} aria-hidden="true" />
                下一步：A 机位标定
              </button>
            </div>
          </div>
        )}

        {/* ── Step 1: A 机位标定 ── */}
        {step === 1 && videoSrcA && videoIdA && (
          <div className="rounded-3xl border border-[#DDE9D6] bg-white/70 p-6">
            <div className="mb-4 flex items-center gap-2">
              <Camera size={16} className="text-[#168A34]" aria-hidden="true" />
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">A 机位 · 球场标定</span>
            </div>
            <CourtCornerCalibrator
              videoSrc={videoSrcA}
              videoId={videoIdA}
              initialPoints={calibrationPointsA}
              isSubmitting={isSubmitting}
              cancelLabel="上一步"
              onComplete={handleCalibrationComplete("cam_1")}
              onCancel={() => setStep(0)}
            />
          </div>
        )}

        {/* ── Step 2: B 机位标定 ── */}
        {step === 2 && videoSrcB && videoIdB && (
          <div className="rounded-3xl border border-[#DDE9D6] bg-white/70 p-6">
            <div className="mb-4 flex items-center gap-2">
              <Camera size={16} className="text-[#168A34]" aria-hidden="true" />
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">B 机位 · 球场标定</span>
            </div>
            <CourtCornerCalibrator
              videoSrc={videoSrcB}
              videoId={videoIdB}
              initialPoints={calibrationPointsB}
              isSubmitting={isSubmitting}
              cancelLabel="上一步"
              onComplete={handleCalibrationComplete("cam_2")}
              onCancel={() => setStep(1)}
            />
          </div>
        )}

        {/* ── Step 3: 确认 ── */}
        {step === 3 && (
          <div className="rounded-3xl border border-[#DDE9D6] bg-white/70 p-6">
            <div className="mb-4 flex items-center gap-2">
              <Radio size={16} className="text-[#168A34]" aria-hidden="true" />
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">确认并开始双摄协同分析</span>
            </div>

            <div className="mb-5 grid gap-x-8 gap-y-4 sm:grid-cols-3">
              <InfoRow label="A 机位标定" value={calibrationA ? "已就绪" : "未完成"} />
              <InfoRow label="B 机位标定" value={calibrationB ? "已就绪" : "未完成"} />
              <InfoRow label="录制时长" value={session.duration_sec != null ? `${Math.round(session.duration_sec)} 秒` : "—"} />
            </div>

            {/* CourtOrientation 产品化确认：端 A/B，而非算法枚举 */}
            <div className="mb-5 rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
              <div className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-[#168A34]">机位朝向</div>
              <p className="mb-3 text-sm text-slate-500">
                请确认 A 机位（参考机位）位于球场的哪一端底线。B 机位默认为对向端。
              </p>
              <div className="flex gap-4">
                <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[#14241B]">
                  <input
                    type="radio"
                    checked={cam1AtEndA}
                    onChange={() => setCam1AtEndA(true)}
                  />
                  A 机位位于球场 A 端底线
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[#14241B]">
                  <input
                    type="radio"
                    checked={!cam1AtEndA}
                    onChange={() => setCam1AtEndA(false)}
                  />
                  A 机位位于球场 B 端底线
                </label>
              </div>
            </div>

            {submitError && (
              <div className="mb-4 rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-4">
                <strong className="block text-sm text-[#991B1B]">{submitError.title}</strong>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl border border-[#FCA5A5]/50 bg-white/70 p-3 text-xs leading-5 text-[#B91C1C]">
                  {submitError.body}
                </pre>
                <div className="mt-3 flex gap-2">
                  <button className="quiet-button px-3 py-1.5 text-xs" onClick={() => setStep(0)} type="button">
                    重新检查同步
                  </button>
                  <button className="quiet-button px-3 py-1.5 text-xs" onClick={() => onNavigate(withTaskListContext(`/capture/${session.session_id}/analyze?cam=cam_1`, { source: "recorded", sessionId: session.session_id, cameraSlot: "cam_1" }))} type="button">
                    改用 A 机位单摄分析
                  </button>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button className="quiet-button px-4 py-2 text-sm" onClick={() => setStep(2)} type="button">
                <ArrowLeft size={15} aria-hidden="true" />
                上一步
              </button>
              <button
                className="green-button px-5 py-2 text-sm disabled:opacity-40"
                disabled={!calibrationA || !calibrationB || isSubmitting}
                onClick={handleStart}
                type="button"
              >
                {isSubmitting ? "正在创建任务…" : "开始双摄协同分析"}
              </button>
            </div>
          </div>
        )}
      </section>
    </PageFrame>
  );
}
