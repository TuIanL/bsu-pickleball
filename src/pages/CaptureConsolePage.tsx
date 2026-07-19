import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera, CheckCircle2, Clock, FolderOpen, Loader2, MapPin, Pencil, Play, PlusCircle,
  RefreshCw, Square, Trash2, Upload, Users, Wifi, WifiOff, X,
} from "lucide-react";
import type { AppPath, FieldSession, CameraInfo, ProbeResult, RecordingSession, SyncRecordingSession, SessionTimelineEvent, CaptureStopResult } from "../types/report";
import {
  getFieldSession, startFieldSession, completeFieldSession,
  listCameras, createCamera, deleteCamera, probeCamera, updateCamera,
  getCameraPreviewUrl, cancelRecording, cancelSyncRecording, getDefaultStorageLocation, pickStorageLocation,
} from "../services/analysisClient";
import { useCaptureRuntime } from "../hooks/useCaptureRuntime";
import { useCaptureRuntimeStatus } from "../hooks/useCaptureRuntimeStatus";
import { MiniTimeline } from "../components/MiniTimeline";
import { ScoreBoard } from "../components/ScoreBoard";
import { useCameraSetup } from "../hooks/useCameraSetup";
import { useCapturePreflight } from "../hooks/useCapturePreflight";
import { useLiveCoding } from "../hooks/useLiveCoding";
import { CaptureWorkspaceLayout } from "../components/capture/CaptureWorkspaceLayout";
import { CameraPreviewGrid, CameraPreviewCard } from "../components/capture/CameraPreviewCard";
import { RecordingControlPanel } from "../components/capture/RecordingControlPanel";
import { EventActionToolbar } from "../components/capture/EventActionToolbar";
import { RecentEventsCard } from "../components/capture/RecentEventsCard";
import { CompactScoreStrip } from "../components/capture/CompactScoreStrip";
import { CameraInfoCard } from "../components/capture/CameraInfoCard";
import { SystemStatusCard, adaptRuntimeMetric } from "../components/capture/SystemStatusCard";
import { formatTimelineEventLabel } from "../components/capture/eventLabels";
import type { TimelineWindowMode, TimelineDensity } from "../components/MiniTimeline";
import type { RecordingControlViewModel } from "../components/capture/captureTypes";

/** 导航跳转函数签名 */
type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

const captureModeLabel: Record<string, string> = {
  practice: "自由练习", match: "记分比赛", engineering: "工程测试",
};

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

/** 格式化字节数为人类可读 */
function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/** 格式化码率（bps → Mbps） */
function formatBitrate(bps: number | null | undefined): string {
  if (bps == null) return "-";
  const mbps = bps / 1_000_000;
  return `${mbps.toFixed(2)} Mbps`;
}

/** 录制控制台页面 Props */
type CaptureConsolePageProps = {
  sessionId: string;       // 场次 ID
  onNavigate: NavigateFn;  // 路由跳转
};

export default function CaptureConsolePage({ sessionId, onNavigate }: CaptureConsolePageProps) {
  const [fieldSession, setFieldSession] = useState<FieldSession | null>(null);  // 场次信息
  const [loading, setLoading] = useState(true);                                  // 初始加载中
  const [analysisIntent, setAnalysisIntent] = useState<string>("ask_after_recording");  // 分析策略
  const [recordingFps, setRecordingFps] = useState<number>(60);                  // 录制帧率
  const [storageRoot, setStorageRoot] = useState<string>("");                    // 自定义存储目录
  const [defaultStorageRoot, setDefaultStorageRoot] = useState<string>("");      // 系统默认存储目录
  const [storagePickerBusy, setStoragePickerBusy] = useState(false);             // 目录选择器中

  const [drawerOpen, setDrawerOpen] = useState(false);                           // 设备抽屉打开
  const [previewKey, setPreviewKey] = useState(0);                               // 预览图刷新 key
  const [drawerTab, setDrawerTab] = useState<"list" | "register">("list");       // 设备列表/注册标签
  const [newCameraForm, setNewCameraForm] = useState({ camera_id: "", name: "", stream_url: "", protocol: "rtsp" as const });
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null);    // 正在编辑的摄像头 ID
  const [editingCameraForm, setEditingCameraForm] = useState({ camera_id: "", name: "" });
  const [savingCamera, setSavingCamera] = useState(false);                        // 正在保存摄像头
  const cameraSelectRef = useRef<HTMLSelectElement>(null);

  const isDualMode = fieldSession?.camera_setup === "dual";
  const mode = isDualMode ? "dual" as const : "single" as const;

  // ── Hooks ──
  const runtime = useCaptureRuntime({ fieldSessionId: sessionId, onFieldSessionStarted: setFieldSession });
  const cameraSetup = useCameraSetup({ sessionId, mode });
  const preflight = useCapturePreflight({ mode, slots: isDualMode ? cameraSetup.selectedSlots : undefined });
  const liveCoding = useLiveCoding({
    fieldSessionId: sessionId,
    captureTakeId: runtime.captureTakeId,
    captureMode: fieldSession?.capture_mode ?? "practice",
    phase: runtime.phase,
    elapsedMs: runtime.elapsedMs,
    startedAt: runtime.session?.startedAt,
  });
  // 运行状态轮询：recording/stopping/recovering 阶段每 2s 拉取，终态停止
  const runtimeStatus = useCaptureRuntimeStatus({
    captureTakeId: runtime.captureTakeId,
    phase: runtime.phase,
  });

  // ── 页面协调 ──
  const handleStart = async () => {
    if (!cameraSetup.startIntent) return;
    await runtime.start({ ...cameraSetup.startIntent, storageRoot: storageRoot || undefined, fps: recordingFps, autoAnalyze: analysisIntent === "auto_analyze" });
  };

  const handlePickStorage = async () => {
    if (runtime.isRecording || storagePickerBusy) return;
    setStoragePickerBusy(true);
    try {
      const result = await pickStorageLocation();
      if (!result.canceled) {
        setStorageRoot(result.storage_root);
        sessionStorage.setItem(`capture.storageRoot.${sessionId}`, result.storage_root);
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "无法打开本地目录选择器");
    } finally {
      setStoragePickerBusy(false);
    }
  };

  // ── 键盘快捷键 ──
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (runtime.phase !== "recording") return;
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") return;
    const key = e.key;
    const quickEvents = liveCoding.quickEvents;
    const findAndTrigger = (type: string) => {
      const ev = quickEvents.find(q => q.type === type);
      if (ev) liveCoding.addTimelineEvent(ev);
    };
    if (key === "1") findAndTrigger("start_set");
    else if (key === "2") findAndTrigger("start_game");
    else if (key === "3") findAndTrigger("start_next_rally");
    else if (key === "4") findAndTrigger("rally_result_a");
    else if (key === "5") findAndTrigger("rally_result_b");
    else if (key === "6") findAndTrigger("rally_replay");
    else if (key === "7") findAndTrigger("change_side");
    else if (key === "8") findAndTrigger("start_timeout");
    else if (key.toUpperCase() === "H") findAndTrigger("add_note");
    else if (key === "Backspace") findAndTrigger("undo");
  }, [runtime.phase, liveCoding.quickEvents, liveCoding.addTimelineEvent]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const handleStop = async () => {
    liveCoding.freeze();
    const stopPromise = runtime.stop();
    void liveCoding.flushWithDeadline(3000);

    // 10 秒超时兜底，防止 API 卡死前端
    const timeoutPromise = new Promise<null>((resolve) =>
      setTimeout(() => resolve(null), 10000)
    );

    const result = await Promise.race([stopPromise, timeoutPromise]);
    // 如果超时先到，stopPromise 还在跑，API 回来后会自己 dispatch
    // 超时后页面显示"恢复中"，useCaptureRuntime 的自动轮询会处理

    // 启动合并状态轮询
    const takeId = runtime.captureTakeId;
    if (isDualMode && takeId) {
      pollMergeStatus(takeId);
    }
    setPreviewKey(k => k + 1);
  };

  const handleCancel = async () => { await runtime.cancel(); };
  const handleReset = () => {
    runtime.reset();
  };

  const handleUseDefaultStorage = () => {
    setStorageRoot("");
    sessionStorage.removeItem(`capture.storageRoot.${sessionId}`);
  };

  const handleDeleteCamera = async (camera: CameraInfo) => {
    if (runtime.isRecording) return;
    if (!window.confirm(`确定要删除摄像头「${camera.name || camera.camera_id}」吗？`)) return;

    try {
      await deleteCamera(camera.camera_id);
      if (cameraSetup.selectedCameraId === camera.camera_id) {
        cameraSetup.setSelectedCameraId("");
      }
      for (const slot of ["cam_1", "cam_2"] as const) {
        if (cameraSetup.selectedSlots[slot] === camera.camera_id) {
          cameraSetup.selectSlot(slot, "");
        }
      }
      await cameraSetup.loadCameras();
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除设备失败，请刷新后重试");
    }
  };

  const startEditingCamera = (camera: CameraInfo) => {
    setEditingCameraId(camera.camera_id);
    setEditingCameraForm({ camera_id: camera.camera_id, name: camera.name });
  };

  const handleUpdateCamera = async (camera: CameraInfo) => {
    const nextId = editingCameraForm.camera_id.trim();
    const nextName = editingCameraForm.name.trim();
    if (!nextId || !nextName) {
      alert("摄像头 ID 和名称不能为空");
      return;
    }
    setSavingCamera(true);
    try {
      await updateCamera(camera.camera_id, { camera_id: nextId, name: nextName });
      if (cameraSetup.selectedCameraId === camera.camera_id) {
        cameraSetup.setSelectedCameraId(nextId);
      }
      for (const slot of ["cam_1", "cam_2"] as const) {
        if (cameraSetup.selectedSlots[slot] === camera.camera_id) {
          cameraSetup.selectSlot(slot, nextId);
        }
      }
      setEditingCameraId(null);
      await cameraSetup.loadCameras();
    } catch (e) {
      alert(e instanceof Error ? e.message : "修改设备失败，请刷新后重试");
    } finally {
      setSavingCamera(false);
    }
  };

  const canStart = runtime.phase === "idle" && cameraSetup.isReady && preflight.preflightState.status !== "running";

  // ── 运行状态派生 ViewModel ──
  const rtSnapshot = runtimeStatus.state.snapshot;
  const rtRecording = rtSnapshot?.recording;

  // 录制控制条 ViewModel：从 runtime status 映射文件大小/帧率/码率
  const recordingControlVm: RecordingControlViewModel = {
    phase: runtime.phase,
    elapsedMs: runtime.elapsedMs,
    fileSize: rtRecording
      ? adaptRuntimeMetric(rtRecording.fileSizeBytes, (v) => formatBytes(v))
      : { state: "loading" },
    fps: rtRecording
      ? adaptRuntimeMetric(rtRecording.effectiveFps, (v) => `${v} fps`)
      : { state: "loading" },
    bitrate: rtRecording
      ? adaptRuntimeMetric(rtRecording.avgBitrateBps, (v) => formatBitrate(v))
      : { state: "loading" },
  };

  // 标题区存储摘要
  const storageSummary = rtSnapshot?.storage
    ? rtSnapshot.storage.state === "ready"
      ? `剩余 ${formatBytes(rtSnapshot.storage.freeBytes)} / ${formatBytes(rtSnapshot.storage.totalBytes)}`
      : rtSnapshot.storage.state === "error"
        ? `存储异常：${rtSnapshot.storage.message ?? ""}`
        : "存储容量读取中…"
    : runtime.phase === "idle"
      ? ""
      : "存储容量读取中…";

  // 预览分辨率/帧率（来自目标配置，非实测）
  const previewResolution = rtRecording?.targetWidth && rtRecording?.targetHeight
    ? `${rtRecording.targetWidth}x${rtRecording.targetHeight}`
    : undefined;
  const previewFps = rtRecording?.targetFps ?? undefined;

  // ── 初始加载 ──
  const loadFieldSession = useCallback(async () => {
    try {
      const fs = await getFieldSession(sessionId);
      setFieldSession(fs);
      const saved = sessionStorage.getItem(`capture.analysisIntent.${sessionId}`);
      if (saved) setAnalysisIntent(saved);
      const slots = sessionStorage.getItem(`capture.slots.${sessionId}`);
      if (slots) {
        const p = JSON.parse(slots);
        if (p.cam_1) cameraSetup.selectSlot("cam_1", p.cam_1);
        if (p.cam_2) cameraSetup.selectSlot("cam_2", p.cam_2);
      }
      const cid = sessionStorage.getItem(`capture.selectedCameraId.${sessionId}`);
      if (cid) cameraSetup.setSelectedCameraId(cid);
      const savedStorageRoot = sessionStorage.getItem(`capture.storageRoot.${sessionId}`);
      if (savedStorageRoot) setStorageRoot(savedStorageRoot);
    } catch { setFieldSession(null); }
    finally { setLoading(false); }
  }, [sessionId]);

  useEffect(() => { loadFieldSession(); }, [loadFieldSession]);

  useEffect(() => {
    void getDefaultStorageLocation()
      .then((result) => setDefaultStorageRoot(result.storage_root))
      .catch(() => setDefaultStorageRoot(""));
  }, []);

  // ── Runtime 恢复后同步摄像头选择 ──
  useEffect(() => {
    if (runtime.phase !== "recording" || !runtime.session) return;
    for (const track of runtime.session.tracks) {
      if (track.slot === "single") {
        cameraSetup.setSelectedCameraId(track.cameraId);
      } else if (track.slot === "cam_1" || track.slot === "cam_2") {
        cameraSetup.selectSlot(track.slot, track.cameraId);
      }
    }
  }, [runtime.phase, runtime.session?.sourceSessionId]);

  const scoringMode = liveCoding.liveCodingState?.scoring_mode ?? "none";
  const isMatchSingles = fieldSession?.capture_mode === "match" && scoringMode === "side_out_singles_v1";
  const [pendingInitialServer, setPendingInitialServer] = useState<boolean>(false);
  const [mergeStatus, setMergeStatus] = useState<string | null>(null);
  const [mergeDetail, setMergeDetail] = useState<string | null>(null);
  const [timelineWindow, setTimelineWindow] = useState<TimelineWindowMode>("full");
  const [timelineDensity, setTimelineDensity] = useState<TimelineDensity>("compact");
  const mergePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 停止后轮询合并状态
  const pollMergeStatus = useCallback(async (takeId: string) => {
    if (mergePollRef.current) return;
    mergePollRef.current = setInterval(async () => {
      try {
        const { getMergeStatus } = await import("../services/analysisClient");
        const status = await getMergeStatus(takeId);
        setMergeStatus(status.status);
        setMergeDetail(status.detail ?? null);
        if (status.status === "completed" || status.status === "failed") {
          if (mergePollRef.current) {
            clearInterval(mergePollRef.current);
            mergePollRef.current = null;
          }
        }
      } catch {
        // 轮询失败不处理
      }
    }, 2000);
  }, []);

  useEffect(() => {
    return () => {
      if (mergePollRef.current) {
        clearInterval(mergePollRef.current);
      }
    };
  }, []);

  // ── 加载中 / Hydrating ──
  if (loading || runtime.isHydrating) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] gap-3">
        <Loader2 size={20} className="animate-spin text-slate-400" />
        <p className="text-slate-400">{loading ? "加载中…" : "检测活跃录制…"}</p>
      </div>
    );
  }
  if (!fieldSession) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-slate-500">采集任务未找到</p>
        <button className="quiet-button px-4 py-2" onClick={() => onNavigate("/capture")} type="button">返回采集任务列表</button>
      </div>
    );
  }

  // ── 摄像机选择区域 ──
  const renderCameraSelector = () => {
    if (mode === "single") {
      return (
        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-500">选择摄像头</label>
          <select
            ref={cameraSelectRef}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            value={cameraSetup.selectedCameraId}
            onChange={e => cameraSetup.setSelectedCameraId(e.target.value)}
            disabled={runtime.isRecording}
          >
            <option value="">-- 选择摄像头 --</option>
            {cameraSetup.cameras.map(c => (
              <option key={c.camera_id} value={c.camera_id}>{c.name ?? c.camera_id}</option>
            ))}
          </select>
        </div>
      );
    }
    return (
      <div className="flex flex-wrap items-center gap-2">
        {(["cam_1", "cam_2"] as const).map(slot => (
          <div key={slot} className="flex min-w-0 flex-1 items-center gap-2">
            <label className="shrink-0 text-xs font-bold text-slate-500">{slot === "cam_1" ? "底线 A" : "底线 B"}</label>
            <button
              className="min-w-0 flex-1 truncate rounded-lg border border-slate-300 px-2.5 py-1.5 text-left text-xs"
              onClick={() => cameraSetup.setSlotSelecting(slot)}
              disabled={runtime.isRecording}
              type="button"
            >
              {cameraSetup.selectedSlots[slot]
                ? (cameraSetup.cameras.find(c => c.camera_id === cameraSetup.selectedSlots[slot])?.name ?? cameraSetup.selectedSlots[slot])
                : `选择 ${slot === "cam_1" ? "A" : "B"} 机位摄像头`}
            </button>
          </div>
        ))}
        {/* Slot 选择弹窗 */}
        {cameraSetup.slotSelecting && (
          <div className="basis-full rounded-lg border border-slate-200 p-2 space-y-1 max-h-32 overflow-y-auto">
            {cameraSetup.cameras.filter(c => c.camera_id !== cameraSetup.selectedSlots[cameraSetup.slotSelecting === "cam_1" ? "cam_2" : "cam_1"]).map(c => (
              <button
                key={c.camera_id}
                className="w-full text-left px-3 py-1.5 rounded-lg hover:bg-slate-100 text-sm"
                onClick={() => cameraSetup.selectSlot(cameraSetup.slotSelecting!, c.camera_id)}
                type="button"
              >
                {c.name ?? c.camera_id}
              </button>
            ))}
          </div>
        )}
        {/* 预检 */}
        {isDualMode && (
          <button
            className="shrink-0 rounded-lg border border-[#3B82F6] px-2.5 py-1.5 text-xs font-bold text-[#3B82F6] transition hover:bg-[#EFF6FF] disabled:opacity-50"
            onClick={preflight.runTest}
            disabled={!cameraSetup.isReady || preflight.preflightState.status === "running" || runtime.isRecording}
            type="button"
          >
            {preflight.preflightState.status === "running" ? <RefreshCw size={14} className="inline animate-spin mr-1" /> : null}
            {preflight.preflightState.status === "running" ? "测试中…" : "短录测试"}
          </button>
        )}
        {preflight.preflightState.status === "passed" && (
          <p className="shrink-0 text-xs text-[#22C55E]">测试通过</p>
        )}
        {preflight.preflightState.status === "failed" && (
          <p className="basis-full text-xs text-[#FF4D4F]">测试失败: {preflight.preflightState.error}</p>
        )}
      </div>
    );
  };

  const isRecording = runtime.phase === "recording";
  const activeStorageRoot = storageRoot || defaultStorageRoot;
  const storageLocationLabel = storageRoot ? "自定义位置" : "默认位置";

  return (
    <CaptureWorkspaceLayout>
      {/* 标题区：标题 + 场地/模式 + 录制状态 + 存储摘要 + 设备入口 */}
      <div className="flex items-center justify-between rounded-xl px-4 py-2" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)", minHeight: 52 }}>
        <div className="flex items-center gap-3 min-w-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold truncate" style={{ color: "var(--capture-text-primary)" }}>{fieldSession.title || "现场采集"}</span>
              {isRecording && (
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: "var(--capture-brand-soft)", color: "var(--capture-brand-primary)" }}>
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ background: "var(--capture-status-recording)" }} />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full" style={{ background: "var(--capture-status-recording)" }} />
                  </span>
                  录制中
                </span>
              )}
            </div>
            <p className="text-xs truncate" style={{ color: "var(--capture-text-muted)" }}>{fieldSession.court_name} · {captureModeLabel[fieldSession.capture_mode] ?? fieldSession.capture_mode}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {storageSummary && (
            <span className="text-xs truncate max-w-[220px]" style={{ color: "var(--capture-text-muted)" }} title={storageSummary}>
              {storageSummary}
            </span>
          )}
          <button
            className="rounded-lg p-1.5 transition disabled:opacity-50"
            style={{ border: "1px solid var(--capture-border-default)", color: "var(--capture-text-secondary)" }}
            onClick={() => void handlePickStorage()}
            disabled={runtime.isRecording || storagePickerBusy}
            type="button"
            aria-label="选择录制保存位置"
            title="选择录制保存位置"
          >
            {storagePickerBusy ? <Loader2 size={14} className="animate-spin" /> : <FolderOpen size={14} />}
          </button>
          <button className="rounded-lg px-2.5 py-1.5 text-xs transition" style={{ border: "1px solid var(--capture-border-default)", color: "var(--capture-text-secondary)" }} onClick={() => setDrawerOpen(!drawerOpen)} type="button" aria-label="设备管理">
            <Camera size={14} className="inline mr-1" />设备
          </button>
          {runtime.isStopped && (
            <button className="rounded-lg px-2.5 py-1.5 text-xs transition" style={{ border: "1px solid var(--capture-border-default)", color: "var(--capture-text-secondary)" }} onClick={handleReset} type="button">新录制</button>
          )}
        </div>
      </div>

      {/* 录制控制条：时长 / 文件大小 / 帧率 / 码率 / 开始停止取消标记 */}
      <RecordingControlPanel
        vm={recordingControlVm}
        canStart={canStart}
        onStart={handleStart}
        onStop={handleStop}
        onMark={() => liveCoding.addTimelineEvent({ type: "add_note", payload: { highlight: true } } as any)}
        onCancel={handleCancel}
        error={runtime.error || undefined}
        belowControls={
          <div className="mt-2 space-y-2">
            <div className="flex min-w-0 items-center gap-3 rounded-lg px-3 py-2" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)" }}>
              <FolderOpen size={15} className="shrink-0" style={{ color: "var(--capture-text-muted)" }} />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold" style={{ color: "var(--capture-text-secondary)" }}>录制保存位置 · {storageLocationLabel}</p>
                <p className="truncate text-xs" style={{ color: "var(--capture-text-muted)" }} title={activeStorageRoot}>{activeStorageRoot || "读取默认位置中…"}</p>
              </div>
              {storageRoot && (
                <button className="shrink-0 text-xs" style={{ color: "var(--capture-text-secondary)" }} onClick={handleUseDefaultStorage} disabled={runtime.isRecording || storagePickerBusy} type="button">恢复默认</button>
              )}
              <button
                className="shrink-0 rounded-lg px-2.5 py-1.5 text-xs transition disabled:opacity-50"
                style={{ border: "1px solid var(--capture-border-default)", color: "var(--capture-text-secondary)" }}
                onClick={() => void handlePickStorage()}
                disabled={runtime.isRecording || storagePickerBusy}
                type="button"
              >
                {storagePickerBusy ? "打开中…" : "选择位置"}
              </button>
            </div>
            {isDualMode && mergeStatus && mergeStatus !== "completed" && (
              <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--capture-brand-soft)", border: "1px solid var(--capture-brand-primary)" }}>
                {mergeStatus === "not_started" && "等待合并…"}
                {mergeStatus === "pending" && "视频合并已提交后台…"}
                {mergeStatus === "merging" && "视频合并中…"}
                {mergeStatus === "failed" && "视频合并失败，可尝试重新合并"}
                {mergeStatus === "failed" && mergeDetail && (
                  <p className="mt-1 break-words text-xs opacity-80">{mergeDetail}</p>
                )}
              </div>
            )}
            {runtime.isStopped && runtime.result && (
              <div className="rounded-xl p-5 space-y-3" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)", boxShadow: "var(--capture-shadow-card)" }}>
                <h3 className="text-lg font-black" style={{ color: "var(--capture-text-primary)" }}>
                  {runtime.phase === "completed" ? "录制已完成" : runtime.phase === "partial" ? "录制部分完成" : "录制结束"}
                </h3>
                {runtime.session?.sessionDir && (
                  <p className="text-xs" style={{ color: "var(--capture-text-muted)" }} title={runtime.session.sessionDir}>会话目录：{runtime.session.sessionDir}</p>
                )}
                {runtime.result.tracks.map(track => (
                  <div key={track.trackId ?? track.slot} className="text-sm" style={{ color: "var(--capture-text-secondary)" }}>
                    {track.slot}: {track.status} | {track.durationMs ? formatElapsed(track.durationMs) : ""} | 片段 {track.fragmentCount}
                  </div>
                ))}
                {runtime.result.analysisAvailable && runtime.result.defaultAnalysisVideoId && (
                  <button className="rounded-lg px-4 py-2 text-sm font-bold text-white" style={{ background: "var(--capture-brand-primary)" }}
                    onClick={() => onNavigate(`/upload?videoId=${runtime.result!.defaultAnalysisVideoId}&source=recording&sessionId=${runtime.session?.sourceSessionId ?? sessionId}&fps=${runtime.session?.fps ?? 60}`)} type="button">
                    创建分析任务
                  </button>
                )}
                {!runtime.result.analysisAvailable && runtime.result.analysisBlockedReason && (
                  <p className="text-sm" style={{ color: "var(--capture-status-warning)" }}>分析不可用：{runtime.result.analysisBlockedReason}</p>
                )}
                {liveCoding.outboxHealth === "pending" && (
                  <div className="flex items-center gap-2 text-sm" style={{ color: "var(--capture-status-warning)" }}>
                    <span>有事件待同步</span>
                    <button onClick={liveCoding.retrySync} className="underline text-xs" type="button">重新同步</button>
                  </div>
                )}
                {runtime.result.warnings.length > 0 && runtime.result.warnings.map((w, i) => (
                  <p key={i} className="text-xs" style={{ color: "var(--capture-status-warning)" }}>⚠ {w}</p>
                ))}
              </div>
            )}
          </div>
        }
      />

      {/* Runtime status 错误提示（不阻塞录制控制） */}
      {runtimeStatus.state.error && runtimeStatus.state.snapshot && (
        <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "var(--capture-brand-soft)", border: "1px solid var(--capture-status-warning)", color: "var(--capture-status-warning)" }}>
          运行状态更新失败：{runtimeStatus.state.error}（最后更新于 {runtimeStatus.state.lastSuccessAt ? new Date(runtimeStatus.state.lastSuccessAt).toLocaleTimeString() : "—"}）
        </div>
      )}

      {/* Main workspace: Single or Dual */}
      {isDualMode ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            {cameraSetup.previewTracks.map(track => {
              const trackStatus = rtSnapshot?.tracks.find(t => t.slot === track.slot);
              const previewState: "idle" | "connecting" | "ready" | "failed" =
                trackStatus?.error ? "failed"
                : trackStatus?.phase === "recording" || trackStatus?.phase === "starting" ? "ready"
                : runtime.phase === "recording" ? "connecting"
                : "ready";
              return (
                <div key={track.slot} style={{ maxHeight: 330 }}>
                  <CameraPreviewCard
                    vm={{
                      slot: track.slot,
                      cameraId: track.cameraId,
                      label: track.slot === "cam_1" ? "机位 A" : "机位 B",
                      previewUrl: getCameraPreviewUrl(track.cameraId) ?? "",
                      resolution: previewResolution,
                      fps: previewFps,
                      status: previewState,
                    }}
                    previewKey={previewKey}
                  />
                </div>
              );
            })}
          </div>
          <div className="rounded-xl p-3" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)" }}>
            {renderCameraSelector()}
          </div>
          {(runtime.phase === "recording" || runtime.phase === "stopping" || runtime.phase === "recovering") && (
            <CompactScoreStrip liveState={liveCoding.liveCodingState} />
          )}
        </div>
      ) : (
        <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div style={{ height: "clamp(320px, 42vh, 430px)" }}>
            <CameraPreviewCard
              vm={cameraSetup.previewTracks.length > 0 ? {
                slot: cameraSetup.previewTracks[0].slot,
                cameraId: cameraSetup.previewTracks[0].cameraId,
                label: "单摄",
                previewUrl: getCameraPreviewUrl(cameraSetup.previewTracks[0].cameraId) ?? "",
                resolution: previewResolution,
                fps: previewFps,
                status: "ready" as const,
              } : { slot: "empty", cameraId: "", label: "预览", previewUrl: "", status: "idle" }}
              previewKey={previewKey}
              fillContainer
            />
          </div>
          <aside className="flex flex-col gap-3 self-stretch">
            <div className="rounded-xl p-3" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)" }}>
              {renderCameraSelector()}
            </div>
            {(runtime.phase === "recording" || runtime.phase === "stopping" || runtime.phase === "recovering") && (
              <ScoreBoard
                liveState={liveCoding.liveCodingState}
                openRallyExists={liveCoding.liveCodingState?.current_rally_segment_id != null}
                timelineEvents={liveCoding.timelineEvents}
                showInitialServerSelector={pendingInitialServer}
                onInitialServerSelect={(server) => {
                  setPendingInitialServer(false);
                  const gameEvent = liveCoding.quickEvents.find((e: { type: string }) => e.type === "start_game");
                  if (gameEvent) liveCoding.addTimelineEvent({ ...gameEvent, payload: { initial_server_team: server } });
                }}
              />
            )}
            {cameraSetup.previewTracks.length > 0 && (
              <CameraInfoCard
                cameraId={cameraSetup.previewTracks[0].cameraId}
                label="单摄"
                resolution={previewResolution}
                fps={previewFps}
              />
            )}
          </aside>
        </div>
      )}

      {/* Live Coding Panel */}
      {isRecording && (
        <div className="rounded-xl p-3 space-y-2" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)", boxShadow: "var(--capture-shadow-card)" }}>
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold" style={{ color: "var(--capture-text-primary)" }}>事件标注时间线</h3>
            <span className="text-[10px]" style={{ color: liveCoding.outboxHealth === "pending" ? "var(--capture-status-warning)" : "var(--capture-brand-primary)" }}>
              {liveCoding.outboxHealth === "pending" ? "● 同步中" : "● 已同步"}
            </span>
          </div>
          <EventActionToolbar
            events={liveCoding.quickEvents.filter(
              e => isMatchSingles || (e.type !== "rally_result_a" && e.type !== "rally_result_b" && e.type !== "rally_replay")
            ).map(e => {
              const liveSegmentIds = new Set([
                liveCoding.liveCodingState?.current_set_segment_id,
                liveCoding.liveCodingState?.current_game_segment_id,
                liveCoding.liveCodingState?.current_rally_segment_id,
              ].filter((id): id is string => Boolean(id)));
              const isActiveSegment = (segmentId: string): boolean => liveSegmentIds.has(segmentId)
                || liveCoding.segments.some(seg => seg.parent_segment_id === segmentId && isActiveSegment(seg.id));
              const activeSegmentByType: Record<"set" | "game" | "rally", boolean> = {
                set: Boolean(liveCoding.liveCodingState?.current_set_segment_id),
                game: Boolean(liveCoding.liveCodingState?.current_game_segment_id),
                rally: Boolean(liveCoding.liveCodingState?.current_rally_segment_id),
              };
              const hasOpenSegment = (segType: "set" | "game" | "rally") => activeSegmentByType[segType]
                || liveCoding.segments.some(seg => seg.segment_type === segType && (seg.status === "open" || isActiveSegment(seg.id)));
              if (e.type === "start_set" && hasOpenSegment("set")) return { ...e, type: "end_set" as const, label: "盘结束", note: "结束当前的一盘" };
              if (e.type === "start_game" && hasOpenSegment("game")) return { ...e, type: "end_game" as const, label: "局结束", note: "结束当前的一局" };
              if (e.type === "start_next_rally" && hasOpenSegment("rally")) return { ...e, type: "end_rally" as const, label: "分结束", note: "结束当前的一分" };
              return e;
            })}
            isPending={(type) => liveCoding.outboxItems.some(i =>
              i.action === type && (i.status === "pending" || i.status === "sending")
            )}
            onAction={(event) => {
              if (event.type === "start_game" && isMatchSingles) setPendingInitialServer(true);
              liveCoding.addTimelineEvent(event as any);
            }}
          />
          <MiniTimeline
            segments={liveCoding.segments}
            events={liveCoding.timelineEvents}
            liveState={liveCoding.liveCodingState}
            totalDurationMs={runtime.elapsedMs}
            elapsedMs={runtime.elapsedMs}
            showDurationHint={runtime.phase === "recording"}
            staticMode
            playing={runtime.phase === "recording"}
            compact
            windowMode={timelineWindow}
            onWindowModeChange={setTimelineWindow}
            density={timelineDensity}
            onDensityChange={setTimelineDensity}
          />
        </div>
      )}

      {/* Bottom row: 最近事件 / 系统状态 / 快捷操作 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <RecentEventsCard
          events={liveCoding.timelineEvents.slice(-5).map(e => ({
            id: e.id,
            label: formatTimelineEventLabel(e, liveCoding.segments),
            timestamp: formatElapsed(e.timestamp_ms),
            type: e.event_type,
          }))}
        />
        <SystemStatusCard
          snapshot={runtimeStatus.state.snapshot}
          isLoading={runtimeStatus.state.isLoading}
          error={runtimeStatus.state.error}
          lastSuccessAt={runtimeStatus.state.lastSuccessAt}
        />
        <div className="rounded-xl p-4" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)", boxShadow: "var(--capture-shadow-card)" }}>
          <h3 className="text-sm font-bold mb-3" style={{ color: "var(--capture-text-primary)" }}>快捷操作</h3>
          <div className="grid grid-cols-3 gap-2">
            <button className="flex flex-col items-center gap-1 rounded-lg p-2 text-xs transition" style={{ background: "var(--capture-surface-page)" }} onClick={() => liveCoding.addTimelineEvent({ type: "add_note", payload: { highlight: true } } as any)} type="button" aria-label="重点标记" disabled={!isRecording}>
              <span style={{ color: "var(--capture-timeline-highlight)" }}>◆</span>
              <span style={{ color: "var(--capture-text-secondary)" }}>重点标记</span>
            </button>
            <button className="flex flex-col items-center gap-1 rounded-lg p-2 text-xs transition" style={{ background: "var(--capture-surface-page)" }} onClick={() => {
              cameraSelectRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
              cameraSelectRef.current?.focus();
            }} type="button" aria-label="切换摄像头" disabled={runtime.isRecording}>
              <RefreshCw size={16} style={{ color: "var(--capture-text-muted)" }} />
              <span style={{ color: "var(--capture-text-secondary)" }}>切换摄像头</span>
            </button>
            <button className="flex flex-col items-center gap-1 rounded-lg p-2 text-xs transition" style={{ background: "var(--capture-surface-page)" }} type="button" aria-label="快捷键">
              <span style={{ color: "var(--capture-text-muted)" }}>⌨</span>
              <span style={{ color: "var(--capture-text-secondary)" }}>快捷键</span>
            </button>
          </div>
        </div>
      </div>

      {/* Device drawer */}
      {drawerOpen && (
        <div className="fixed inset-y-0 right-0 w-96 z-50 p-6 overflow-y-auto" style={{ background: "var(--capture-surface-card)", borderLeft: "1px solid var(--capture-border-default)", boxShadow: "var(--capture-shadow-card)" }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold" style={{ color: "var(--capture-text-primary)" }}>设备管理</h3>
            <button onClick={() => setDrawerOpen(false)} type="button"><X size={20} /></button>
          </div>
          <div className="flex gap-2 mb-4">
            <button className={`px-3 py-1.5 rounded-lg text-sm font-bold ${drawerTab === "list" ? "text-white" : ""}`}
              style={drawerTab === "list" ? { background: "var(--capture-text-primary)" } : { background: "var(--capture-surface-page)" }}
              onClick={() => setDrawerTab("list")} type="button">列表</button>
            <button className={`px-3 py-1.5 rounded-lg text-sm font-bold ${drawerTab === "register" ? "text-white" : ""}`}
              style={drawerTab === "register" ? { background: "var(--capture-text-primary)" } : { background: "var(--capture-surface-page)" }}
              onClick={() => setDrawerTab("register")} type="button">注册</button>
          </div>
          {drawerTab === "list" ? (
            <div className="space-y-2">
              {cameraSetup.cameras.map(c => (
                <div key={c.camera_id} className="flex items-center justify-between rounded-xl p-3" style={{ border: "1px solid var(--capture-border-default)" }}>
                  {editingCameraId === c.camera_id ? (
                    <div className="w-full space-y-2">
                      <input aria-label="摄像头 ID" className="w-full rounded-lg px-2.5 py-1.5 text-sm" style={{ border: "1px solid var(--capture-border-default)" }}
                        value={editingCameraForm.camera_id} onChange={e => setEditingCameraForm(f => ({ ...f, camera_id: e.target.value }))} />
                      <input aria-label="摄像头名称" className="w-full rounded-lg px-2.5 py-1.5 text-sm" style={{ border: "1px solid var(--capture-border-default)" }}
                        value={editingCameraForm.name} onChange={e => setEditingCameraForm(f => ({ ...f, name: e.target.value }))} />
                      <div className="flex justify-end gap-2">
                        <button className="px-2.5 py-1 text-xs rounded-lg" style={{ border: "1px solid var(--capture-border-default)" }} onClick={() => setEditingCameraId(null)} type="button">取消</button>
                        <button className="px-2.5 py-1 text-xs rounded-lg text-white" style={{ background: "var(--capture-brand-primary)" }} disabled={savingCamera || runtime.isRecording} onClick={() => void handleUpdateCamera(c)} type="button">
                          {savingCamera ? "保存中..." : "保存"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="min-w-0 text-sm">
                        <p className="font-bold truncate" style={{ color: "var(--capture-text-primary)" }}>{c.name ?? c.camera_id}</p>
                        <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>ID：{c.camera_id}</p>
                        <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>{c.stream_url}</p>
                        {cameraSetup.probeResults[c.camera_id]?.online ? (
                          <p className="mt-1 text-xs font-medium" style={{ color: "var(--capture-brand-primary)" }}>
                            可用{cameraSetup.probeResults[c.camera_id].resolution ? ` · ${cameraSetup.probeResults[c.camera_id].resolution}` : ""}
                          </p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <button className="p-1.5 rounded-lg hover:bg-gray-100" disabled={runtime.isRecording} onClick={() => startEditingCamera(c)} type="button"><Pencil size={14} /></button>
                        <button className="p-1.5 rounded-lg hover:bg-red-50" disabled={runtime.isRecording} onClick={() => void handleDeleteCamera(c)} type="button"><Trash2 size={14} /></button>
                      </div>
                    </>
                  )}
                </div>
              ))}
              <button className="w-full rounded-xl border py-2 text-sm" style={{ borderColor: "var(--capture-border-default)", color: "var(--capture-text-muted)" }} onClick={() => setDrawerTab("register")} type="button">
                <PlusCircle size={14} className="inline mr-1" />注册新设备
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <input className="w-full rounded-xl px-3 py-2 text-sm" style={{ border: "1px solid var(--capture-border-default)" }} placeholder="摄像头 ID" value={newCameraForm.camera_id} onChange={e => setNewCameraForm(f => ({ ...f, camera_id: e.target.value }))} />
              <input className="w-full rounded-xl px-3 py-2 text-sm" style={{ border: "1px solid var(--capture-border-default)" }} placeholder="名称" value={newCameraForm.name} onChange={e => setNewCameraForm(f => ({ ...f, name: e.target.value }))} />
              <input className="w-full rounded-xl px-3 py-2 text-sm" style={{ border: "1px solid var(--capture-border-default)" }} placeholder="RTSP 地址" value={newCameraForm.stream_url} onChange={e => setNewCameraForm(f => ({ ...f, stream_url: e.target.value }))} />
              <button className="w-full rounded-xl py-2.5 text-sm font-bold text-white" style={{ background: "var(--capture-brand-primary)" }} onClick={async () => {
                try { await createCamera(newCameraForm as any); cameraSetup.loadCameras(); setDrawerTab("list"); } catch { /* ignore */ }
              }} type="button">注册</button>
            </div>
          )}
        </div>
      )}
    </CaptureWorkspaceLayout>
  );
}
