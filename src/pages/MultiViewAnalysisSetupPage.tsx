import { useEffect, useState, type ReactNode } from "react";
import { Activity, ArrowLeft, ArrowRight, Bug, Camera, CheckCircle2, Link2, Radio, Settings2, ShieldAlert, Video } from "lucide-react";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { buildAnalysisProgressPath, buildSyncCalibrationPath, taskListPath, withTaskListContext } from "../app/navigationContext";
import { CourtCornerCalibrator, type CalibrationPointDraft } from "../components/platform/CourtCornerCalibrator";
import {
  HOLDOUT_ORDER,
  NetProfileCalibrator,
  NetProfileSettings,
  estimateNetProfileHeight,
  type NetAnnotationDraft,
  type NetProfileSettingsValue,
} from "../components/platform/NetProfileCalibrator";
import { PageFrame } from "../components/PageFrame";
import { AnalysisFlowSelector, type AnalysisFlowMode } from "../components/platform/AnalysisFlowSelector";
import { AnalysisRosterConfirmation } from "../components/platform/AnalysisRosterConfirmation";
import type { RosterConfirmationRequest } from "../types/rallyContext";
import {
  createMultiviewAnalysisJob,
  getCaptureTake,
  getMetricCourtSceneDraft,
  publishMetricCourtScene,
  saveMetricCourtSceneDraft,
  getSyncAnchorStatus,
  getSyncRecording,
  getVideoStreamUrl,
  isAnalysisApiError,
  validateMetricCourtScene,
  type MultiViewCreateViewPayload,
} from "../services/analysisClient";
import { STANDARD_NET_HEIGHT_FT, buildNetProfile } from "../types/metricCourtScene";
import type { CaptureTakeSummary, SyncRecordingSession } from "../types/report";
import type { SyncAnchorStatus } from "../types/syncAnchors";
import type { MetricCourtSceneCalibration, NetProfileControlPoint, SceneImagePoint } from "../types/metricCourtScene";

// ── Types ───────────────────────────────────────────────────────────────────

interface MultiViewAnalysisSetupPageProps {
  captureTakeId: string;
  onNavigate: NavigateFn;
}

/**
 * 三阶段：球场标定 · 球网标定 · 名册与确认。
 * 「素材与同步前置检查」不再是独立步骤，改为顶部常驻状态条；
 * 它的「分析配置」项（分析窗口 / Debug Replay / 分析流程）下移到确认阶段。
 */
type SetupStep = 0 | 1 | 2;

/** 两路机位的展示标识；并排布局、完成度门控与文案统一由此驱动。 */
const VIEW_SIDES = [
  { slot: "cam_1" as const, label: "A 视角" },
  { slot: "cam_2" as const, label: "B 视角" },
];

// ── Helpers ─────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</span>
      <span className="text-sm font-semibold text-[var(--ui-ink)]">{value}</span>
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

function restoreNetDraft(scene: MetricCourtSceneCalibration, viewId: string): NetAnnotationDraft | null {
  const view = scene.views.find((item) => item.view_id === viewId);
  if (!view) return null;
  const annotations = Object.fromEntries(
    scene.net_profile.control_points.flatMap((control) => {
      const point = control.image_by_view?.[viewId] ?? view.net_annotations[control.id];
      return point ? [[control.id, point satisfies SceneImagePoint]] : [];
    }),
  );
  const holdoutAnnotations = Object.fromEntries(
    (scene.holdout_control_points ?? []).flatMap((control) => {
      const point = control.image_by_view?.[viewId] ?? view.holdout_annotations?.[control.id];
      return point ? [[control.id, point satisfies SceneImagePoint]] : [];
    }),
  );
  if (Object.keys(annotations).length < 3) return null;
  return {
    profile: scene.net_profile,
    annotations,
    holdoutAnnotations: Object.keys(holdoutAnnotations).length >= HOLDOUT_ORDER.length ? holdoutAnnotations : undefined,
    imageWidth: view.image_width ?? 1280,
    imageHeight: view.image_height ?? 720,
    frameIndex: view.frame_index ?? null,
  };
}

/**
 * 从已保存的场景草稿恢复**共享**球网高度取值。
 * 同一张球网只有一个高度模型，两路只贡献各自的 image-space 点位。
 */
function restoreNetProfileValue(scene: MetricCourtSceneCalibration): NetProfileSettingsValue {
  const controls = scene.net_profile.control_points;
  const endpoint = controls.find((point) => point.id === "left")?.world.z;
  const center = controls.find((point) => point.id === "center")?.world.z;
  return {
    mode: scene.net_profile.profile_type === "measured" ? "measured" : "standard",
    endpointCm: (typeof endpoint === "number" && Number.isFinite(endpoint) ? endpoint : STANDARD_NET_HEIGHT_FT.endpoint) * 30.48,
    centerCm: (typeof center === "number" && Number.isFinite(center) ? center : STANDARD_NET_HEIGHT_FT.center) * 30.48,
    confirmed: controls.length === 3 && controls.every((point) => Boolean(point.confirmed)),
  };
}

const STEP_LABELS: Array<{ n: number; label: string }> = [
  { n: 1, label: "球场标定" },
  { n: 2, label: "球网标定" },
  { n: 3, label: "名册与确认" },
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
                  ? "grid size-6 place-items-center rounded-full bg-[var(--ui-brand-solid)] text-white"
                  : active
                    ? "grid size-6 place-items-center rounded-full bg-[var(--ui-brand-solid-deep)] text-white"
                    : "grid size-6 place-items-center rounded-full bg-slate-200 text-slate-500"
              }
            >
              {done ? <CheckCircle2 size={14} aria-hidden="true" /> : item.n}
            </span>
            <span className={active ? "text-[var(--ui-ink)]" : done ? "text-[var(--ui-brand-deep)]" : "text-slate-400"}>
              {item.label}
            </span>
            {index < STEP_LABELS.length - 1 && <span className="mx-1 h-px w-6 bg-slate-200" />}
          </div>
        );
      })}
    </div>
  );
}

// ── 常驻素材与同步状态条 ────────────────────────────────────────────────────

type ChipTone = "ok" | "warn" | "danger" | "neutral";

const CHIP_TONE_CLASS: Record<ChipTone, string> = {
  ok: "border-[var(--ui-border)] bg-[var(--ui-surface-soft)]",
  warn: "border-[var(--ui-warning-border)] bg-[var(--ui-warning-soft-2)]",
  danger: "border-[var(--ui-danger-border)] bg-[var(--ui-danger-soft)]",
  neutral: "border-[var(--ui-border)] bg-[var(--ui-surface-soft)]",
};

const CHIP_ICON_CLASS: Record<ChipTone, string> = {
  ok: "text-[var(--ui-brand-deep)]",
  warn: "text-[var(--ui-warning-deeper)]",
  danger: "text-[var(--ui-danger-deep)]",
  neutral: "text-slate-400",
};

function StatusChip({ tone, icon, label, value }: { tone: ChipTone; icon: ReactNode; label: string; value: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${CHIP_TONE_CLASS[tone]}`}
    >
      <span className={CHIP_ICON_CLASS[tone]}>{icon}</span>
      <span className="font-bold text-slate-500">{label}</span>
      <span className="text-[var(--ui-ink)]">{value}</span>
    </span>
  );
}

interface MaterialStatusBarProps {
  videoReadyA: boolean;
  videoReadyB: boolean;
  videosReady: boolean;
  takeCompleted: boolean;
  takeStatusNote: string;
  syncStatusLoading: boolean;
  syncReady: boolean;
  syncLabel: string;
  syncAnchorStatus: SyncAnchorStatus | null;
  debugReplayEnabled: boolean;
  /** 提交失败时就地高亮，取代原先「回到素材检查步骤」的回退 */
  error: { title: string; body: string } | null;
  onOpenSyncCalibration: () => void;
  onDismissError: () => void;
  onSwitchToSingleView: () => void;
}

function MaterialStatusBar({
  videoReadyA,
  videoReadyB,
  videosReady,
  takeCompleted,
  takeStatusNote,
  syncStatusLoading,
  syncReady,
  syncLabel,
  syncAnchorStatus,
  debugReplayEnabled,
  error,
  onOpenSyncCalibration,
  onDismissError,
  onSwitchToSingleView,
}: MaterialStatusBarProps) {
  const debugReplayNeedsManualSync = debugReplayEnabled
    && Boolean(syncAnchorStatus?.state)
    && syncAnchorStatus?.state !== "confirmed"
    && syncAnchorStatus?.state !== "not_required";

  const takeTone: ChipTone = !videosReady ? "danger" : takeCompleted ? "ok" : "warn";
  const syncTone: ChipTone = syncReady ? "ok" : syncStatusLoading ? "neutral" : "warn";
  const syncActionLabel = syncAnchorStatus?.state === "draft"
    ? "继续标注"
    : syncAnchorStatus?.state === "invalidated"
      ? "重新标注"
      : "开始标注";

  return (
    <div
      className={`mb-5 rounded-2xl border p-3 ${
        error ? "border-[var(--ui-danger-border)] bg-[var(--ui-danger-soft)]" : "border-[var(--ui-border)] bg-[var(--ui-surface)]/70"
      }`}
      data-testid="material-status-bar"
    >
      <div className="mb-2 flex items-center gap-2">
        <Settings2 size={14} className="text-[var(--ui-brand-deep)]" aria-hidden="true" />
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--ui-brand-deep)]">素材与同步</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={videoReadyA ? "ok" : "danger"} icon={<Video size={13} aria-hidden="true" />} label="A 机位视频" value={videoReadyA ? "已就绪" : "未就绪"} />
        <StatusChip tone={videoReadyB ? "ok" : "danger"} icon={<Video size={13} aria-hidden="true" />} label="B 机位视频" value={videoReadyB ? "已就绪" : "未就绪"} />
        <StatusChip tone={takeTone} icon={<Activity size={13} aria-hidden="true" />} label="录制状态" value={takeStatusNote} />
        <StatusChip tone={syncTone} icon={<ShieldAlert size={13} aria-hidden="true" />} label="同步锚点" value={syncLabel} />
      </div>

      {!videosReady ? (
        <div className="mt-3 rounded-xl border border-[var(--ui-danger-border)] bg-[var(--ui-surface)]/70 p-3 text-sm text-[var(--ui-danger-deep)]">
          双摄素材尚未全部就绪，无法开始协同分析。请确认双机位视频已合并完成。
        </div>
      ) : null}

      {videosReady && !syncReady && !syncStatusLoading ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--ui-warning-border)] bg-[var(--ui-surface)]/70 p-3">
          <div>
            <div className="text-sm font-bold text-[var(--ui-ink)]">先完成同步锚点前置检查</div>
            <div className="mt-1 text-xs text-slate-500">
              {debugReplayNeedsManualSync
                ? "Debug Replay 需要人工确认的同步锚点。"
                : syncAnchorStatus?.reason_codes.join("；") || "当前录制还没有可复用的人工确认。"}
            </div>
          </div>
          <button className="quiet-button px-3 py-2 text-xs" onClick={onOpenSyncCalibration} type="button">
            <Link2 size={15} />
            {syncActionLabel}
          </button>
        </div>
      ) : null}

      {syncReady && syncAnchorStatus?.quality ? (
        <div className="mt-3 rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-3 text-xs text-[var(--ui-brand-deep)]">
          来源：{syncAnchorStatus.source === "manual_anchors" ? "人工锚点确认" : "自动估算"} · 锚点 {syncAnchorStatus.quality.anchor_count} 组 · 覆盖率{" "}
          {(syncAnchorStatus.quality.coverage_ratio * 100).toFixed(1)}% · residual {syncAnchorStatus.quality.residual_rms_ms?.toFixed(2) ?? "—"} ms · 确认时间{" "}
          {syncAnchorStatus.confirmed_at ? new Date(syncAnchorStatus.confirmed_at).toLocaleString("zh-CN") : "—"}
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-xl border border-[var(--ui-danger-border)] bg-[var(--ui-surface)]/70 p-3">
          <strong className="block text-sm text-[var(--ui-danger-deeper)]">{error.title}</strong>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--ui-danger-border)]/50 bg-[var(--ui-surface)]/70 p-3 text-xs leading-5 text-[var(--ui-danger-deep)]">
            {error.body}
          </pre>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="quiet-button px-3 py-1.5 text-xs" onClick={onOpenSyncCalibration} type="button">
              重新检查同步
            </button>
            <button className="quiet-button px-3 py-1.5 text-xs" onClick={onSwitchToSingleView} type="button">
              改用 A 机位单摄分析
            </button>
            <button className="quiet-button px-3 py-1.5 text-xs" onClick={onDismissError} type="button">
              关闭提示
            </button>
          </div>
        </div>
      ) : null}
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
  const [netAnnotationA, setNetAnnotationA] = useState<NetAnnotationDraft | null>(null);
  const [netAnnotationB, setNetAnnotationB] = useState<NetAnnotationDraft | null>(null);
  // 球网高度收敛为页面级唯一取值：同一张球网只有一个高度模型，两路仅贡献各自的 image-space 点位。
  const [netProfile, setNetProfile] = useState<NetProfileSettingsValue>(() => ({
    mode: "standard",
    endpointCm: STANDARD_NET_HEIGHT_FT.endpoint * 30.48,
    centerCm: STANDARD_NET_HEIGHT_FT.center * 30.48,
    confirmed: false,
  }));
  const [cam1AtEndA, setCam1AtEndA] = useState(true);
  /** 朝向改变会翻转球网左右端的 canonical 语义，已标注点位必须作废 */
  const [orientationChangedNetReset, setOrientationChangedNetReset] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<{ title: string; body: string } | null>(null);
  // 分析窗口（take 公共时间轴，秒）；关闭 = 整场分析。双摄不物理裁剪，附加信息天然一致。
  const [clipEnabled, setClipEnabled] = useState(false);
  const [clipStartSec, setClipStartSec] = useState(0);
  // 窗口默认结束点由录制时长决定；在录制时长加载前不伪造 60 秒默认值。
  const [clipEndSec, setClipEndSec] = useState<number | null>(null);
  const [debugReplayEnabled, setDebugReplayEnabled] = useState(false);
  const [analysisFlow, setAnalysisFlow] = useState<AnalysisFlowMode>("new");
  const [rosterConfirmation, setRosterConfirmation] = useState<RosterConfirmationRequest>({
    skipped: false,
    entries: [],
  });
  const [syncAnchorStatus, setSyncAnchorStatus] = useState<SyncAnchorStatus | null>(null);
  const [syncStatusLoading, setSyncStatusLoading] = useState(true);

  const handleAnalysisFlowChange = (next: AnalysisFlowMode) => {
    setAnalysisFlow(next);
    setRosterConfirmation(next === "legacy"
      ? { skipped: true, entries: [] }
      : { skipped: false, entries: [] });
  };

  // 路由带 `?session=`（录制卡片传入），缺失时回退到 take.source_session_id 反查
  const routeSessionId = new URLSearchParams(window.location.search).get("session");
  const returnParam = new URLSearchParams(window.location.search).get("return");
  const taskContext = {
    source: "sync_recording" as const,
    sessionId: session?.session_id ?? routeSessionId ?? undefined,
  };
  const taskReturnPath = () => taskListPath(taskContext);
  // 从 Library 进入时优先回到来源工作区，否则回双摄任务列表
  const goReturn = () => onNavigate((returnParam ?? taskReturnPath()) as NavigatePath);

  /**
   * 打开同步锚点工作台。嵌套 return：把完整上层 URL（含 session + 外层 library return）
   * 传给 SyncCalibration，完成/取消后原样回到本设置页，链条不丢。
   */
  const openSyncCalibration = () => {
    const outerParams = new URLSearchParams();
    if (routeSessionId) outerParams.set("session", routeSessionId);
    if (returnParam) outerParams.set("return", returnParam);
    const outerUrl = `/capture/takes/${encodeURIComponent(captureTakeId)}/analyze${outerParams.size ? `?${outerParams.toString()}` : ""}`;
    onNavigate(buildSyncCalibrationPath(captureTakeId, outerUrl));
  };

  // ── Load take + source session ────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const takeData = await getCaptureTake(captureTakeId);
        if (cancelled) return;
        setTake(takeData);
        try {
          const sceneDraft = await getMetricCourtSceneDraft(captureTakeId);
          if (!cancelled && sceneDraft) {
            const sharedValue = restoreNetProfileValue(sceneDraft);
            const sharedProfile = buildNetProfile(
              sharedValue.mode,
              sharedValue.endpointCm,
              sharedValue.centerCm,
              sharedValue.confirmed,
            );
            setNetProfile(sharedValue);
            const draftA = restoreNetDraft(sceneDraft, "cam_1");
            const draftB = restoreNetDraft(sceneDraft, "cam_2");
            setNetAnnotationA(draftA ? { ...draftA, profile: sharedProfile } : null);
            setNetAnnotationB(draftB ? { ...draftB, profile: sharedProfile } : null);
          }
        } catch {
          // Scene assets are optional for historical takes; the manual flow remains available.
        }
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
  const recordingDurationSec = session?.duration_sec != null
    && Number.isFinite(session.duration_sec)
    && session.duration_sec > 0
    ? session.duration_sec
    : null;
  const selectedClipEndSec = clipEndSec ?? recordingDurationSec;
  const clipWindowValid = !clipEnabled
    || (selectedClipEndSec != null
      && selectedClipEndSec > clipStartSec
      && (recordingDurationSec == null || selectedClipEndSec <= recordingDurationSec));

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
  const expectedRosterCount = session?.match_format === "singles" ? 2 : 4;
  const rosterConfirmationComplete = analysisFlow !== "new"
    || rosterConfirmation.skipped
    || (
      rosterConfirmation.entries.length === expectedRosterCount
      && rosterConfirmation.entries.every((entry) => entry.anchor_bbox?.length === 4)
      && Boolean(rosterConfirmation.initial_team_a_end)
    );
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
    ? "正在读取…"
    : syncAnchorStatus
      ? syncStatusLabel[syncAnchorStatus.state]
      : "不可用";

  // MVP：cam_1（reference view）位于球场哪一端 → identity/rotate_180 相对约定。
  // 精确的 mirror_x/mirror_y 语义 + 安装角色自动推断列为后续 Change。
  const cam1Orientation: MultiViewCreateViewPayload["courtOrientation"] = cam1AtEndA ? "identity" : "rotate_180";
  const cam2Orientation: MultiViewCreateViewPayload["courtOrientation"] = cam1AtEndA ? "rotate_180" : "identity";

  // 两路完成度：并排同页后，单路完成不再放行。
  const missingCourtSides = VIEW_SIDES
    .filter((side) => !(side.slot === "cam_1" ? calibrationA : calibrationB))
    .map((side) => side.label);
  const missingNetSides = VIEW_SIDES
    .filter((side) => !(side.slot === "cam_1" ? netAnnotationA : netAnnotationB))
    .map((side) => side.label);
  const courtStepReady = missingCourtSides.length === 0;
  const netStepReady = missingNetSides.length === 0 && netProfile.confirmed;

  const courtStepHint = !videosReady
    ? "双摄素材尚未就绪"
    : !syncReady
      ? "需先完成同步锚点前置检查"
      : courtStepReady
        ? "两路四角标定已完成"
        : `尚未完成：${missingCourtSides.join("、")}`;
  const netStepHint = missingNetSides.length > 0
    ? `尚未完成：${missingNetSides.join("、")}`
    : !netProfile.confirmed
      ? "请确认共享的球网高度模型"
      : "两路球网标注与高度模型已就绪";

  const sharedNetProfile = () => buildNetProfile(netProfile.mode, netProfile.endpointCm, netProfile.centerCm, netProfile.confirmed);

  // ── Actions ────────────────────────────────────────────────────────────────

  const persistSceneDraft = async (nextA: NetAnnotationDraft | null, nextB: NetAnnotationDraft | null) => {
    const source = nextA ?? nextB;
    if (!source) return;
    // 高度永远取自页面级共享取值，两路只贡献各自的 image-space 点位。
    const profile = sharedNetProfile();
    const sceneControlPoints = profile.control_points.map((point) => ({
      ...point,
      image_by_view: Object.fromEntries([
        nextA?.annotations[point.id] ? ["cam_1", nextA.annotations[point.id]] : [],
        nextB?.annotations[point.id] ? ["cam_2", nextB.annotations[point.id]] : [],
      ]),
    }));
    const holdoutControlPoints: NetProfileControlPoint[] = HOLDOUT_ORDER.map((control) => ({
      id: control.id,
      world: {
        x: control.x,
        y: profile.control_points[0]?.world.y ?? 22,
        z: estimateNetProfileHeight(profile, control.x),
      },
      image_by_view: Object.fromEntries([
        nextA?.holdoutAnnotations?.[control.id] ? ["cam_1", nextA.holdoutAnnotations[control.id]] : [],
        nextB?.holdoutAnnotations?.[control.id] ? ["cam_2", nextB.holdoutAnnotations[control.id]] : [],
      ]),
      provenance: "manual_verified",
      confirmed: true,
    }));
    const buildView = (viewId: "cam_1" | "cam_2", draft: NetAnnotationDraft | null, cameraId: string, videoId?: string | null, calibrationId?: string | null) => draft ? ({
      view_id: viewId,
      camera_id: cameraId,
      video_id: videoId,
      calibration_id: calibrationId,
      image_width: draft.imageWidth,
      image_height: draft.imageHeight,
      frame_index: draft.frameIndex,
      court_orientation: viewId === "cam_1" ? cam1Orientation : cam2Orientation,
      net_annotations: draft.annotations,
      holdout_annotations: draft.holdoutAnnotations ?? {},
      quality: { status: "warning" as const, rejection_reasons: [] },
      provenance: "manual" as const,
    }) : null;
    const views = [
      buildView("cam_1", nextA, cameraIdA, videoIdA, calibrationA),
      buildView("cam_2", nextB, cameraIdB, videoIdB, calibrationB),
    ].filter((view): view is NonNullable<typeof view> => Boolean(view));
    await saveMetricCourtSceneDraft(captureTakeId, {
      net_profile: { ...profile, control_points: sceneControlPoints },
      holdout_control_points: holdoutControlPoints,
      views,
      provenance: "manual_verified",
    });
  };

  // 只记录结果、不跳步：两路都完成由底部按钮放行。
  const handleCalibrationComplete = (slot: "cam_1" | "cam_2") => {
    return (calibrationId: string, points: CalibrationPointDraft[]) => {
      if (slot === "cam_1") {
        setCalibrationA(calibrationId);
        setCalibrationPointsA(points);
      } else {
        setCalibrationB(calibrationId);
        setCalibrationPointsB(points);
      }
    };
  };

  const handleNetComplete = (slot: "cam_1" | "cam_2") => (draft: NetAnnotationDraft) => {
    // 覆盖组件内部产出的 profile：高度只有一份权威来源（页面级共享取值）。
    const normalized: NetAnnotationDraft = { ...draft, profile: sharedNetProfile() };
    if (slot === "cam_1") {
      setNetAnnotationA(normalized);
      void persistSceneDraft(normalized, netAnnotationB).catch(() => undefined);
    } else {
      setNetAnnotationB(normalized);
      void persistSceneDraft(netAnnotationA, normalized).catch(() => undefined);
    }
  };

  const handleOrientationChange = (nextCam1AtEndA: boolean) => {
    if (nextCam1AtEndA === cam1AtEndA) return;
    setCam1AtEndA(nextCam1AtEndA);
    // 朝向决定球网左右端的 canonical 语义，翻转后旧的球网点位不再有意义。
    if (netAnnotationA || netAnnotationB) {
      setNetAnnotationA(null);
      setNetAnnotationB(null);
      setOrientationChangedNetReset(true);
    }
  };

  const handleStart = async () => {
    if (!take || !session || !videoIdA || !videoIdB || !calibrationA || !calibrationB || !netAnnotationA || !netAnnotationB) return;
    if (!clipWindowValid) {
      setSubmitError({
        title: "分析窗口无效",
        body: "请确认开始时间小于结束时间，且结束时间不超过录制时长。",
      });
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      // 两路共用页面级高度 profile；image-space 点位各取本路。
      const profile = sharedNetProfile();
      const sceneControlPoints = profile.control_points.map((point) => ({
        ...point,
        image_by_view: {
          cam_1: netAnnotationA.annotations[point.id] as SceneImagePoint,
          cam_2: netAnnotationB.annotations[point.id] as SceneImagePoint,
        },
      }));
      const holdoutControlPoints: NetProfileControlPoint[] = HOLDOUT_ORDER.map((control) => ({
        id: control.id,
        world: {
          x: control.x,
          y: profile.control_points[0]?.world.y ?? 22,
          z: estimateNetProfileHeight(profile, control.x),
        },
        image_by_view: {
          cam_1: netAnnotationA.holdoutAnnotations?.[control.id] as SceneImagePoint,
          cam_2: netAnnotationB.holdoutAnnotations?.[control.id] as SceneImagePoint,
        },
        provenance: "manual_verified",
        confirmed: true,
      }));
      const sceneDraft = await saveMetricCourtSceneDraft(captureTakeId, {
        net_profile: {
          ...profile,
          control_points: sceneControlPoints,
        },
        holdout_control_points: holdoutControlPoints,
        views: [
          {
            view_id: "cam_1",
            camera_id: cameraIdA,
            video_id: videoIdA,
            calibration_id: calibrationA,
            image_width: netAnnotationA.imageWidth,
            image_height: netAnnotationA.imageHeight,
            frame_index: netAnnotationA.frameIndex,
            court_orientation: cam1Orientation,
            net_annotations: netAnnotationA.annotations,
            holdout_annotations: netAnnotationA.holdoutAnnotations ?? {},
            quality: { status: "warning", rejection_reasons: [] },
            provenance: "manual",
          },
          {
            view_id: "cam_2",
            camera_id: cameraIdB,
            video_id: videoIdB,
            calibration_id: calibrationB,
            image_width: netAnnotationB.imageWidth,
            image_height: netAnnotationB.imageHeight,
            frame_index: netAnnotationB.frameIndex,
            court_orientation: cam2Orientation,
            net_annotations: netAnnotationB.annotations,
            holdout_annotations: netAnnotationB.holdoutAnnotations ?? {},
            quality: { status: "warning", rejection_reasons: [] },
            provenance: "manual",
          },
        ],
        provenance: "manual_verified",
      });
      const validation = await validateMetricCourtScene(captureTakeId);
      if (validation.status !== "ready") {
        throw new Error(`球网场景标定质量门未通过：${validation.rejection_reasons.join("、")}`);
      }
      const publishedScene = await publishMetricCourtScene(captureTakeId);
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
        clipEndMs: clipEnabled && selectedClipEndSec != null
          ? Math.max(1, Math.round(selectedClipEndSec * 1000))
          : undefined,
        // 快速验证窗口沿用正式 joint 的默认采样密度（60 FPS source / stride 2），
        // 保证高速球的双摄观测不因验证模式额外降采样。
        frameStride: clipEnabled ? 2 : undefined,
        // 双摄协同分析的正式展示链路统一走 canonical joint；Debug Replay 只是
        // 在同一条链路上额外保留四联诊断回放，不再决定是否启用球路分析。
        executionMode: "joint_tracking_v2",
        // 正式比赛分析必须先生成并绑定模型回合窗口计划。
        segmentationRequired: true,
        useRallyContext: analysisFlow === "new",
        rosterConfirmation,
        debugTraceEnabled: debugReplayEnabled,
        sceneCalibrationMode: "metric",
        sceneCalibrationRevision: publishedScene.revision,
        sceneViewIds: sceneDraft.views.map((view) => view.view_id),
        referenceViewId: "cam_1",
        views: [
          { viewId: "cam_1", cameraId: cameraIdA, videoId: videoIdA, calibrationId: calibrationA, courtOrientation: cam1Orientation, imageWidth: netAnnotationA.imageWidth, imageHeight: netAnnotationA.imageHeight },
          { viewId: "cam_2", cameraId: cameraIdB, videoId: videoIdB, calibrationId: calibrationB, courtOrientation: cam2Orientation, imageWidth: netAnnotationB.imageWidth, imageHeight: netAnnotationB.imageHeight },
        ],
        // canonical frame 是 take-scoped 物理定义。普通重试不再从展示/当前
        // 选择重新拼接端点；后端会只读复用已有 ccf_* 定义。
      });
      // 只导航到 Parent（用户永不直接进入 child）。
      // 统一生命周期：创建成功后进入 Analysis Progress（replace，Back 不回已提交的 Setup）。
      // Library origin 用上游 return；采集入口无 return 时以同步会话 materialize capture return。
      const effectiveReturn = returnParam ?? `/capture/${encodeURIComponent(session.session_id)}`;
      onNavigate(buildAnalysisProgressPath(parent.id, effectiveReturn, undefined), { replace: true });
    } catch (err) {
      const message = isAnalysisApiError(err)
        ? err.backendDetail ?? err.message
        : err instanceof Error
          ? err.message
          : "请检查后端连接后重试。";
      // 就地高亮顶部状态条，不再把用户弹回一个已不存在的「素材检查」步骤。
      setSubmitError({
        title: "双摄分析启动失败",
        body: message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // ── Error / loading states ─────────────────────────────────────────────────

  if (loadError) {
    return (
      <PageFrame>
        <div className="mx-auto mt-20 max-w-md text-center">
          <div className="rounded-2xl border border-[var(--ui-danger-border)] bg-[var(--ui-danger-soft)] p-6">
            <strong className="text-[var(--ui-danger-deeper)]">加载失败</strong>
            <p className="mt-2 text-sm text-[var(--ui-danger-deep)]">{loadError}</p>
          </div>
          <button
            className="quiet-button mt-4 px-4 py-2 text-sm"
            onClick={() => goReturn()}
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
          <div className="rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-6">
            <p className="text-sm text-slate-500">正在加载双摄素材…</p>
          </div>
        </div>
      </PageFrame>
    );
  }

  // ── Main render ──────────────────────────────────────────────────────────

  return (
    <PageFrame>
      <section className="mx-auto max-w-5xl xl:max-w-7xl">
        {/* Header */}
        <button
          className="mb-5 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[var(--ui-brand-deep)]"
          onClick={() => goReturn()}
          type="button"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          返回双摄任务
        </button>
        <div className="mb-6 flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-[var(--ui-brand-solid)]/15 text-[var(--ui-brand-deep)]">
            <Camera size={20} aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-black text-[var(--ui-ink)]">双摄协同分析</h1>
            <p className="mt-0.5 text-sm text-slate-500">
              {session.court_name || "未知球场"} · {session.match_format === "singles" ? "单打" : "双打"} ·{" "}
              {session.duration_sec != null ? `${Math.round(session.duration_sec)} 秒` : "—"}
            </p>
          </div>
        </div>

        <StepBar step={step} />

        <MaterialStatusBar
          debugReplayEnabled={debugReplayEnabled}
          error={submitError}
          onDismissError={() => setSubmitError(null)}
          onOpenSyncCalibration={openSyncCalibration}
          onSwitchToSingleView={() => onNavigate(withTaskListContext(`/capture/${session.session_id}/analyze?cam=cam_1`, { source: "recorded", sessionId: session.session_id, cameraSlot: "cam_1" }))}
          syncAnchorStatus={syncAnchorStatus}
          syncLabel={syncLabel}
          syncReady={syncReady}
          syncStatusLoading={syncStatusLoading}
          takeCompleted={takeCompleted}
          takeStatusNote={takeStatusNote}
          videoReadyA={Boolean(videoIdA)}
          videoReadyB={Boolean(videoIdB)}
          videosReady={videosReady}
        />

        {/* ── Step 0: 球场标定（两路同页） ── */}
        {step === 0 && (
          <div className="rounded-3xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-4 sm:p-6">
            {/* 机位朝向前置：它决定球网左右端的 canonical 语义，必须先于任一标定确认 */}
            <div className="mb-5 rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-4">
              <div className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-[var(--ui-brand-deep)]">机位朝向</div>
              <p className="mb-3 text-sm text-slate-500">
                请先确认 A 机位（参考机位）位于球场的哪一端底线。B 机位默认为对向端；该选择决定球网左右端的判定方向。
              </p>
              <div className="flex flex-wrap gap-4">
                <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[var(--ui-ink)]">
                  <input checked={cam1AtEndA} onChange={() => handleOrientationChange(true)} type="radio" />
                  A 机位位于球场 A 端底线
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[var(--ui-ink)]">
                  <input checked={!cam1AtEndA} onChange={() => handleOrientationChange(false)} type="radio" />
                  A 机位位于球场 B 端底线
                </label>
              </div>
            </div>

            <div className="mb-4 flex items-center gap-2">
              <Camera size={16} className="text-[var(--ui-brand-deep)]" aria-hidden="true" />
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--ui-brand-deep)]">球场标定 · 两路同页</span>
            </div>

            <div className="grid gap-6 xl:grid-cols-2" data-testid="court-calibration-panel">
              {VIEW_SIDES.map((side) => {
                const videoSrc = side.slot === "cam_1" ? videoSrcA : videoSrcB;
                const videoId = side.slot === "cam_1" ? videoIdA : videoIdB;
                const points = side.slot === "cam_1" ? calibrationPointsA : calibrationPointsB;
                if (!videoSrc || !videoId) {
                  return (
                    <div key={side.slot} className="rounded-2xl border border-[var(--ui-danger-border)] bg-[var(--ui-danger-soft)] p-4 text-sm text-[var(--ui-danger-deep)]">
                      {side.label} 视频未就绪，无法标定。
                    </div>
                  );
                }
                return (
                  <CourtCornerCalibrator
                    key={side.slot}
                    initialPoints={points}
                    isSubmitting={isSubmitting}
                    onComplete={handleCalibrationComplete(side.slot)}
                    submitLabel={`确认 ${side.label}球场四角`}
                    title={`${side.label} · 球场四角`}
                    variant="embedded"
                    videoId={videoId}
                    videoSrc={videoSrc}
                  />
                );
              })}
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs font-semibold text-slate-500">{courtStepHint}</div>
              <div className="flex flex-wrap gap-3">
                <button className="quiet-button px-4 py-2 text-sm" onClick={() => goReturn()} type="button">
                  <ArrowLeft size={15} aria-hidden="true" />
                  退出向导
                </button>
                <button
                  className="green-button px-4 py-2 text-sm disabled:opacity-40"
                  disabled={!allReady || !courtStepReady}
                  onClick={() => setStep(1)}
                  type="button"
                >
                  <ArrowRight size={15} aria-hidden="true" />
                  下一步：球网标定
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Step 1: 球网标定（两路同页 + 共享高度） ── */}
        {step === 1 && (
          <div className="rounded-3xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-4 sm:p-6">
            <div className="mb-4 flex items-center gap-2">
              <Camera size={16} className="text-[var(--ui-brand-deep)]" aria-hidden="true" />
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--ui-brand-deep)]">球网标定 · 两路同页</span>
            </div>

            {orientationChangedNetReset ? (
              <div className="mb-4 rounded-2xl border border-[var(--ui-warning-border)] bg-[var(--ui-warning-soft-2)] p-3 text-xs leading-5 text-[var(--ui-warning-deeper)]">
                机位朝向已改变，球网左右端的判定方向随之翻转，此前标注的球网点位已作废。请重新标注两路球网；球场标定不受影响。
              </div>
            ) : null}

            {/* 高度只有一份：同一张球网一个高度模型，两路共用 */}
            <div className="mb-5 rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-4" data-testid="shared-net-profile-panel">
              <NetProfileSettings onChange={setNetProfile} value={netProfile} />
            </div>

            <div className="grid gap-6 xl:grid-cols-2" data-testid="net-calibration-panel">
              {VIEW_SIDES.map((side) => {
                const videoSrc = side.slot === "cam_1" ? videoSrcA : videoSrcB;
                const draft = side.slot === "cam_1" ? netAnnotationA : netAnnotationB;
                if (!videoSrc) {
                  return (
                    <div key={side.slot} className="rounded-2xl border border-[var(--ui-danger-border)] bg-[var(--ui-danger-soft)] p-4 text-sm text-[var(--ui-danger-deep)]">
                      {side.label} 视频未就绪，无法标注球网。
                    </div>
                  );
                }
                return (
                  <div key={side.slot} className="rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-3">
                    <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--ui-brand-deep)]">
                      {side.label} · 球网控制点
                    </div>
                    <NetProfileCalibrator
                      courtOrientation={side.slot === "cam_1" ? cam1Orientation : cam2Orientation}
                      initial={draft}
                      isSubmitting={isSubmitting}
                      onComplete={handleNetComplete(side.slot)}
                      variant="embedded"
                      videoSrc={videoSrc}
                      viewId={side.slot}
                    />
                  </div>
                );
              })}
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs font-semibold text-slate-500">{netStepHint}</div>
              <div className="flex flex-wrap gap-3">
                <button className="quiet-button px-4 py-2 text-sm" onClick={() => setStep(0)} type="button">
                  <ArrowLeft size={15} aria-hidden="true" />
                  上一步
                </button>
                <button
                  className="green-button px-4 py-2 text-sm disabled:opacity-40"
                  disabled={!netStepReady}
                  onClick={() => setStep(2)}
                  type="button"
                >
                  <ArrowRight size={15} aria-hidden="true" />
                  下一步：名册与确认
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Step 2: 名册与确认 ── */}
        {step === 2 && (
          <div className="rounded-3xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-4 sm:p-6">
            <div className="mb-4 flex items-center gap-2">
              <Radio size={16} className="text-[var(--ui-brand-deep)]" aria-hidden="true" />
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--ui-brand-deep)]">名册与确认 · 双摄协同分析</span>
            </div>

            <div className="mb-5 grid gap-x-8 gap-y-4 sm:grid-cols-3">
              <InfoRow label="A 视角球场标定" value={calibrationA ? "已就绪" : "未完成"} />
              <InfoRow label="B 视角球场标定" value={calibrationB ? "已就绪" : "未完成"} />
              <InfoRow label="球网标注" value={netAnnotationA && netAnnotationB ? "两路已确认" : "未完成"} />
              <InfoRow label="球网高度模型" value={netProfile.confirmed ? "已确认（两路共用）" : "未确认"} />
              <InfoRow label="录制时长" value={session.duration_sec != null ? `${Math.round(session.duration_sec)} 秒` : "—"} />
              <InfoRow label="机位朝向" value={cam1AtEndA ? "A 机位位于 A 端底线" : "A 机位位于 B 端底线"} />
            </div>

            {/* 朝向只读回显：修改入口跳回球场标定阶段 */}
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-3">
              <span className="text-xs text-slate-500">机位朝向决定球网左右端方向；如需修改请回到球场标定阶段（会清空已标注的球网点位）。</span>
              <button className="quiet-button px-3 py-1.5 text-xs" onClick={() => setStep(0)} type="button">
                返回修改朝向
              </button>
            </div>

            {/* 分析配置（原素材检查步骤迁入）：窗口 / Debug Replay / 分析流程 */}
            <div className="mb-5 rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-4" data-testid="analysis-config">
              <div className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-[var(--ui-brand-deep)]">分析配置</div>
              <label className="flex cursor-pointer items-center gap-2 text-sm font-bold text-[var(--ui-ink)]">
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
                    className="w-24 rounded-lg border border-[var(--ui-border-soft)] bg-[var(--ui-surface)] px-2 py-1.5 text-sm font-semibold text-[var(--ui-ink)]"
                    max={selectedClipEndSec != null ? Math.max(0, selectedClipEndSec - 1) : undefined}
                    min={0}
                    onChange={(e) => {
                      const nextStart = Math.max(0, Number(e.target.value) || 0);
                      const boundedStart = recordingDurationSec != null
                        ? Math.min(nextStart, Math.max(0, recordingDurationSec - 1))
                        : nextStart;
                      setClipStartSec(boundedStart);
                      if (selectedClipEndSec != null && selectedClipEndSec <= boundedStart) {
                        setClipEndSec(Math.min(recordingDurationSec ?? Number.POSITIVE_INFINITY, boundedStart + 1));
                      }
                    }}
                    type="number"
                    value={clipStartSec}
                  />
                  <span className="text-slate-500">到</span>
                  <input
                    className="w-24 rounded-lg border border-[var(--ui-border-soft)] bg-[var(--ui-surface)] px-2 py-1.5 text-sm font-semibold text-[var(--ui-ink)]"
                    max={recordingDurationSec ?? undefined}
                    min={clipStartSec + 1}
                    onChange={(e) => {
                      const nextEnd = Math.max(clipStartSec + 1, Number(e.target.value) || clipStartSec + 1);
                      setClipEndSec(recordingDurationSec != null ? Math.min(nextEnd, recordingDurationSec) : nextEnd);
                    }}
                    type="number"
                    value={selectedClipEndSec ?? ""}
                  />
                  <span className="text-slate-500">秒（整场 {session.duration_sec != null ? Math.round(session.duration_sec) : "—"} 秒）</span>
                  <span className="text-xs text-slate-400">双摄自动对齐，无需手动切帧；附加信息保持一致</span>
                </div>
              )}
              <label className={`mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition ${debugReplayEnabled ? "border-[#8FD39D] bg-[#EFFAF1]" : "border-[var(--ui-border)] bg-[var(--ui-surface)]"}`}>
                <input
                  aria-label="生成 Debug Replay"
                  checked={debugReplayEnabled}
                  className="mt-0.5 size-4 accent-[#168A34]"
                  onChange={(event) => setDebugReplayEnabled(event.target.checked)}
                  type="checkbox"
                />
                <span className="flex items-start gap-2">
                  <Bug className="mt-0.5 shrink-0 text-[var(--ui-brand-deep)]" size={17} aria-hidden="true" />
                  <span>
                    <span className="block text-sm font-bold text-[var(--ui-ink)]">生成 Debug Replay</span>
                    <span className="mt-1 block text-xs leading-5 text-slate-500">在 joint_tracking_v2 双摄链路上额外保留四联诊断回放；会增加分析耗时和存储占用。</span>
                  </span>
                </span>
              </label>
              <div className="mt-4">
                <AnalysisFlowSelector value={analysisFlow} onChange={handleAnalysisFlowChange} />
              </div>
            </div>

            {analysisFlow === "new" ? (
              <>
                <p className="mb-3 rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-3 text-xs leading-5 text-slate-600">
                  要计算“发球队 · 网前到位率”，请在下方确认球员、Team A/B 和初始端位；也可以明确跳过并继续普通分析。
                </p>
                <AnalysisRosterConfirmation
                  captureTakeId={captureTakeId}
                  clipEndMs={
                    clipEnabled && selectedClipEndSec != null
                      ? Math.max(1, Math.round(selectedClipEndSec * 1000))
                      : null
                  }
                  clipStartMs={clipEnabled ? Math.max(0, Math.round(clipStartSec * 1000)) : null}
                  matchFormat={session.match_format === "singles" ? "singles" : "doubles"}
                  onChange={setRosterConfirmation}
                  videoId={videoIdA}
                  videoIdB={videoIdB}
                />
              </>
            ) : (
              <div className="mb-5 rounded-2xl border border-[var(--ui-warning-border)] bg-[#FFF8EA] p-4 text-sm leading-6 text-[#7A4A00]">
                已选择旧流程：本次任务不会冻结 P1–P4 名册和回合上下文。需要发球队网前到位率时，请切回新流程并确认名册。
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs font-semibold text-slate-500">
                {!clipWindowValid ? "分析窗口无效：请确认开始时间小于结束时间" : "确认无误后即可启动双摄协同分析"}
              </div>
              <div className="flex flex-wrap gap-3">
                <button className="quiet-button px-4 py-2 text-sm" onClick={() => setStep(1)} type="button">
                  <ArrowLeft size={15} aria-hidden="true" />
                  上一步
                </button>
                <button
                  className="green-button px-5 py-2 text-sm disabled:opacity-40"
                  disabled={
                    !allReady
                    || !calibrationA
                    || !calibrationB
                    || !netAnnotationA
                    || !netAnnotationB
                    || !netProfile.confirmed
                    || !clipWindowValid
                    || !rosterConfirmationComplete
                    || isSubmitting
                  }
                  onClick={handleStart}
                  type="button"
                >
                  {isSubmitting ? "正在创建任务…" : "开始双摄协同分析"}
                </button>
              </div>
            </div>
          </div>
        )}
      </section>
    </PageFrame>
  );
}
