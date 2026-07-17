import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera, CheckCircle2, Clock, FolderOpen, Loader2, MapPin, Pencil, Play, PlusCircle,
  RefreshCw, Square, Trash2, Upload, Users, Wifi, WifiOff, X,
} from "lucide-react";
import type { AppPath, FieldSession, CameraInfo, ProbeResult, RecordingSession, SyncRecordingSession, SessionTimelineEvent, CaptureStopResult } from "../types/report";
import {
  getFieldSession, startFieldSession, completeFieldSession,
  listCameras, createCamera, deleteCamera, probeCamera, updateCamera,
  getCameraPreviewUrl, cancelRecording, cancelSyncRecording, pickStorageLocation,
} from "../services/analysisClient";
import { useCaptureRuntime } from "../hooks/useCaptureRuntime";
import { MiniTimeline } from "../components/MiniTimeline";
import { ScoreBoard } from "../components/ScoreBoard";
import { useCameraSetup } from "../hooks/useCameraSetup";
import { useCapturePreflight } from "../hooks/useCapturePreflight";
import { useLiveCoding } from "../hooks/useLiveCoding";

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
  const [storagePickerBusy, setStoragePickerBusy] = useState(false);             // 目录选择器中

  const [drawerOpen, setDrawerOpen] = useState(false);                           // 设备抽屉打开
  const [previewKey, setPreviewKey] = useState(0);                               // 预览图刷新 key
  const [drawerTab, setDrawerTab] = useState<"list" | "register">("list");       // 设备列表/注册标签
  const [newCameraForm, setNewCameraForm] = useState({ camera_id: "", name: "", stream_url: "", protocol: "rtsp" as const });
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null);    // 正在编辑的摄像头 ID
  const [editingCameraForm, setEditingCameraForm] = useState({ camera_id: "", name: "" });
  const [savingCamera, setSavingCamera] = useState(false);                        // 正在保存摄像头

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
      if (!result.canceled) setStorageRoot(result.storage_root);
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
    if (takeId) {
      pollMergeStatus(takeId);
    }
    setPreviewKey(k => k + 1);
  };

  const handleCancel = async () => { await runtime.cancel(); };
  const handleReset = () => {
    setStorageRoot("");
    runtime.reset();
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
    } catch { setFieldSession(null); }
    finally { setLoading(false); }
  }, [sessionId]);

  useEffect(() => { loadFieldSession(); }, [loadFieldSession]);

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
  const mergePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 停止后轮询合并状态
  const pollMergeStatus = useCallback(async (takeId: string) => {
    if (mergePollRef.current) return;
    mergePollRef.current = setInterval(async () => {
      try {
        const { getMergeStatus } = await import("../services/analysisClient");
        const status = await getMergeStatus(takeId);
        setMergeStatus(status.status);
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

  const elapsedDisplay = formatElapsed(runtime.elapsedMs);

  // ── 摄像机选择区域 ──
  const renderCameraSelector = () => {
    if (mode === "single") {
      return (
        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-500">选择摄像头</label>
          <select
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

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-5">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-black text-[#14241B]">{fieldSession.title || "现场采集"}</h1>
          <p className="text-sm text-slate-500">{fieldSession.court_name} · {captureModeLabel[fieldSession.capture_mode] ?? fieldSession.capture_mode}</p>
        </div>
        <div className="flex gap-2">
          <button className="quiet-button px-3 py-1.5 text-sm" onClick={() => setDrawerOpen(!drawerOpen)} type="button">
            <Camera size={16} className="inline mr-1" />设备
          </button>
          {runtime.isStopped && (
            <button className="quiet-button px-3 py-1.5 text-sm" onClick={handleReset} type="button">
              新录制
            </button>
          )}
        </div>
      </div>

      {/* 控制栏 */}
      <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-3 h-3 rounded-full ${runtime.phase === "recording" ? "bg-[#FF4D4F] animate-pulse" : runtime.phase === "stopping" || runtime.phase === "recovering" ? "bg-[#E8A838]" : runtime.phase === "hydrating" ? "bg-[#3B82F6]" : runtime.phase === "hydration_failed" ? "bg-[#FF4D4F]" : "bg-slate-300"}`} />
            <span className="text-sm font-bold text-[#14241B]">
              {runtime.phase === "idle" ? "就绪" :
               runtime.phase === "starting" ? "启动中…" :
               runtime.phase === "hydrating" ? "检测恢复中…" :
               runtime.phase === "recording" ? `录制中 ${elapsedDisplay}` :
               runtime.phase === "stopping" ? "停止中…" :
               runtime.phase === "recovering" ? (runtime.recoveryTimedOut ? "恢复超时" : "恢复中…") :
               runtime.phase === "completed" || runtime.phase === "partial" ? `已完成 ${elapsedDisplay}` :
               runtime.phase === "failed" ? "失败" :
               runtime.phase === "canceled" ? "已取消" :
               runtime.phase === "hydration_failed" ? "恢复失败" : "就绪"}
            </span>
          </div>
          <div className="flex gap-2">
            {runtime.phase === "idle" && (
              <button className="flex items-center gap-2 rounded-xl bg-[#22C55E] px-5 py-2.5 text-white font-bold hover:bg-[#168A34] transition disabled:opacity-50" onClick={handleStart} disabled={!canStart} type="button">
                <Play size={16} fill="currentColor" />开始录制
              </button>
            )}
            {(runtime.phase === "recording" || runtime.phase === "stopping") && (
              <>
                <button className="flex items-center gap-2 rounded-xl bg-[#FF4D4F] px-5 py-2.5 text-white font-bold hover:bg-[#E04344] transition" onClick={handleStop} type="button">
                  <Square size={16} fill="currentColor" />停止
                </button>
                <button className="flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 transition" onClick={handleCancel} type="button">取消</button>
              </>
            )}
            {runtime.phase === "recovering" && !runtime.recoveryTimedOut && (
              <button className="flex items-center gap-2 rounded-xl bg-[#3B82F6] px-5 py-2.5 text-white font-bold" onClick={() => runtime.recover()} type="button">
                <RefreshCw size={16} />重试恢复
              </button>
            )}
            {runtime.phase === "recovering" && runtime.recoveryTimedOut && (
              <>
                <button className="flex items-center gap-2 rounded-xl bg-[#FF4D4F] px-5 py-2.5 text-white font-bold" onClick={handleStop} type="button">
                  <Square size={16} fill="currentColor" />再次停止
                </button>
                <button className="flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 transition" onClick={handleCancel} type="button">取消录制</button>
              </>
            )}
            {runtime.phase === "hydration_failed" && (
              <button className="flex items-center gap-2 rounded-xl bg-[#3B82F6] px-5 py-2.5 text-white font-bold" onClick={() => runtime.hydrate()} type="button">
                <RefreshCw size={16} />重试
              </button>
            )}
          </div>
        </div>
        {runtime.phase === "hydration_failed" && runtime.hydrationError && (
          <p className="text-xs text-[#FF4D4F] mt-2">{runtime.hydrationError}</p>
        )}
        {runtime.error && <p className="text-xs text-[#FF4D4F] mt-2">{runtime.error}</p>}
      </div>

      <div className="mt-4 rounded-2xl border border-[#DDE9D6] bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-bold text-[#14241B]">录制保存位置</p>
            <p className="mt-1 truncate text-xs text-slate-500" title={storageRoot || "当前标准位置"}>
              {storageRoot || "当前标准位置"}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            {storageRoot && !runtime.isRecording && (
              <button className="quiet-button px-3 py-2 text-sm" onClick={() => setStorageRoot("")} type="button">
                恢复默认
              </button>
            )}
            <button className="quiet-button flex items-center gap-2 px-3 py-2 text-sm" disabled={runtime.isRecording || storagePickerBusy} onClick={() => void handlePickStorage()} type="button">
              <FolderOpen size={16} />{storagePickerBusy ? "选择中…" : "选择位置"}
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-400">仅对下一次录制生效；重新进入本页面时恢复标准位置。</p>
      </div>

      {/* 预览 + 计分板 */}
      <div className={isDualMode ? "space-y-3" : "grid grid-cols-1 gap-6 lg:grid-cols-3"}>
        {isDualMode && (
          <div className="rounded-xl border border-[#DDE9D6] bg-white px-3 py-2">
            {renderCameraSelector()}
          </div>
        )}
        <div className={isDualMode ? "" : "lg:col-span-2"}>
          <div className={`grid ${cameraSetup.previewTracks.length === 1 ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2"} gap-3`}>
            {cameraSetup.previewTracks.length === 0 ? (
              <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 aspect-video flex items-center justify-center">
                <p className="text-slate-400 text-sm">选择摄像头后显示预览</p>
              </div>
            ) : cameraSetup.previewTracks.map(track => (
              <div key={track.slot} className="relative aspect-video overflow-hidden rounded-xl border border-slate-200 bg-black">
                <img
                  key={previewKey}
                  src={getCameraPreviewUrl(track.cameraId) ?? ""}
                  className="w-full h-full object-contain"
                  alt={track.slot}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
                <span className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-0.5 rounded">
                  {track.slot === "single" ? "单摄" : track.slot === "cam_1" ? "机位 A" : "机位 B"}
                </span>
              </div>
            ))}
          </div>
        </div>
        {!isDualMode && <div className="space-y-4">
          {renderCameraSelector()}
        </div>}
        {/* 计分板 sidebar */}
        {(runtime.phase === "recording" || runtime.phase === "stopping" || runtime.phase === "recovering" || runtime.phase === "completed" || runtime.phase === "partial") && (
          <div className="lg:col-span-1">
            <ScoreBoard
              liveState={liveCoding.liveCodingState}
              openRallyExists={liveCoding.liveCodingState?.current_rally_segment_id != null}
              showInitialServerSelector={pendingInitialServer}
              onInitialServerSelect={(server) => {
                setPendingInitialServer(false);
                const gameEvent = liveCoding.quickEvents.find((e: { type: string }) => e.type === "start_game");
                if (gameEvent) {
                  liveCoding.addTimelineEvent({
                    ...gameEvent,
                    payload: { initial_server_team: server },
                  });
                }
              }}
            />
            {liveCoding.outboxHealth === "pending" && (
              <p className="text-xs text-amber-600 mt-2">有 {liveCoding.outboxItems.filter(i => i.status !== "synced").length} 条事件待同步</p>
            )}
          </div>
        )}
      </div>

      {/* Live Coding */}
      {(runtime.phase === "recording" || runtime.phase === "stopping" || runtime.phase === "recovering") && (
        <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
          {liveCoding.quickEvents.length > 0 && !isMatchSingles && (
            <p className="text-xs text-slate-500 mb-2">当前模式 (match singles)：使用结果按钮记录比分</p>
          )}
          <div className="flex flex-wrap gap-2">
            {(isMatchSingles ? liveCoding.quickEvents : liveCoding.quickEvents.filter(
              e => e.type !== "rally_result_a" && e.type !== "rally_result_b" && e.type !== "rally_replay"
            )).map(event => {
              const liveSegmentIds = new Set([
                liveCoding.liveCodingState?.current_set_segment_id,
                liveCoding.liveCodingState?.current_game_segment_id,
                liveCoding.liveCodingState?.current_rally_segment_id,
              ].filter((id): id is string => Boolean(id)));
              const isActiveSegment = (segmentId: string): boolean => liveSegmentIds.has(segmentId)
                || liveCoding.segments.some(segment =>
                  segment.parent_segment_id === segmentId && isActiveSegment(segment.id));
              const hasOpenSegment = (segmentType: "set" | "game" | "rally") =>
                liveCoding.segments.some(segment =>
                  segment.segment_type === segmentType
                  && (segment.status === "open" || isActiveSegment(segment.id)));
              let buttonEvent = event;
              if (event.type === "start_set" && hasOpenSegment("set")) {
                buttonEvent = { ...event, type: "end_set", label: "盘结束", note: "结束当前的一盘" };
              } else if (event.type === "start_game" && hasOpenSegment("game")) {
                buttonEvent = { ...event, type: "end_game", label: "局结束", note: "结束当前的一局" };
              } else if (event.type === "start_next_rally" && hasOpenSegment("rally") && !isMatchSingles) {
                buttonEvent = { ...event, type: "end_rally", label: "分结束", note: "结束当前的一分" };
              }
              const colorMap: Record<string, string> = {
                rally_result_a: "bg-[#F0FDF4] border-[#22C55E] text-[#22C55E]",
                rally_result_b: "bg-[#EFF6FF] border-[#3B82F6] text-[#3B82F6]",
                rally_replay: "bg-slate-50 border-slate-300 text-slate-500",
                start_set: "bg-[#FFF7ED] border-[#F97316] text-[#F97316]",
                end_set: "bg-slate-50 border-[#F97316] text-[#F97316]",
                start_game: "bg-[#EFF6FF] border-[#3B82F6] text-[#3B82F6]",
                end_game: "bg-slate-50 border-[#3B82F6] text-[#3B82F6]",
                start_next_rally: "bg-[#F0FDF4] border-[#22C55E] text-[#22C55E]",
                end_rally: "bg-slate-50 border-slate-300 text-slate-500",
                start_timeout: "bg-[#FFF7ED] border-[#F97316] text-[#F97316]",
                change_side: "bg-[#FAF5FF] border-[#A855F7] text-[#A855F7]",
                add_note: "bg-[#EFF6FF] border-[#3B82F6] text-[#3B82F6]",
                undo: "bg-red-50 border-red-300 text-red-500",
              };
              const isPending = liveCoding.outboxItems.some(
                i => i.status === "pending" && i.actionType === event.type
              );
              return (
                <button
                  key={event.type}
                  className={`rounded-xl border px-3 py-1.5 text-xs font-bold transition ${colorMap[buttonEvent.type] ?? "bg-slate-50 border-slate-300 text-slate-500"} ${isPending ? "opacity-50 cursor-wait" : ""}`}
                  onClick={() => {
                    if (buttonEvent.type === "start_game" && isMatchSingles) {
                      setPendingInitialServer(true);
                    }
                    liveCoding.addTimelineEvent(buttonEvent);
                  }}
                  disabled={isPending}
                  type="button"
                >
                  {buttonEvent.label}
                </button>
              );
            })}
          </div>
          {liveCoding.outboxHealth === "pending" && (
            <p className="text-xs text-amber-600 mt-2">有 {liveCoding.outboxItems.filter(i => i.status !== "synced").length} 条事件待同步</p>
          )}
        </div>
      )}

      {/* MiniTimeline */}
      {runtime.phase === "recording" || runtime.phase === "stopping" || runtime.phase === "recovering" ? (
        <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
          <MiniTimeline
            segments={liveCoding.segments}
            events={liveCoding.timelineEvents}
            liveState={liveCoding.liveCodingState}
            totalDurationMs={runtime.elapsedMs}
            elapsedMs={runtime.elapsedMs}
            showDurationHint={runtime.phase === "recording"}
          />
        </div>
      ) : null}

      {/* 合并状态提示 */}
      {mergeStatus && mergeStatus !== "completed" && (
        <div className="rounded-xl border border-[#E8A838]/30 bg-[#FFF7ED] p-3 text-sm">
          {mergeStatus === "not_started" && "⏳ 等待合并…"}
          {mergeStatus === "pending" && "⏳ 视频合并已提交后台…"}
          {mergeStatus === "merging" && "⏳ 视频合并中…"}
          {mergeStatus === "failed" && "❌ 视频合并失败，可尝试重新合并"}
        </div>
      )}

      {/* 完成面板 */}
      {runtime.isStopped && runtime.result && (
        <div className="rounded-2xl border border-[#22C55E]/30 bg-[#22C55E]/8 p-6 space-y-3">
          <h3 className="text-lg font-black text-[#14241B]">
            {runtime.phase === "completed" ? "录制已完成" : runtime.phase === "partial" ? "录制部分完成" : "录制结束"}
          </h3>
          {runtime.session?.sessionDir && (
            <p className="text-xs text-slate-500" title={runtime.session.sessionDir}>
              会话目录：{runtime.session.sessionDir}
            </p>
          )}
          {runtime.result.tracks.map(track => (
            <div key={track.trackId ?? track.slot} className="text-sm text-slate-600">
              {track.slot}: {track.status} | {track.durationMs ? formatElapsed(track.durationMs) : ""} | 片段 {track.fragmentCount}
            </div>
          ))}
          {runtime.result.analysisAvailable && runtime.result.defaultAnalysisVideoId && (
            <button
              className="rounded-xl bg-[#22C55E] px-4 py-2 text-sm font-bold text-white"
              onClick={() => onNavigate(`/upload?videoId=${runtime.result!.defaultAnalysisVideoId}&source=recording&sessionId=${runtime.session?.sourceSessionId ?? sessionId}&fps=${runtime.session?.fps ?? 60}`)}
              type="button"
            >
              创建分析任务
            </button>
          )}
          {!runtime.result.analysisAvailable && runtime.result.analysisBlockedReason && (
            <p className="text-sm text-[#E8A838]">分析不可用：{runtime.result.analysisBlockedReason}</p>
          )}
          {liveCoding.outboxHealth === "pending" && (
            <div className="flex items-center gap-2 text-amber-600 text-sm">
              <span>有事件待同步</span>
              <button onClick={liveCoding.retrySync} className="underline text-xs" type="button">重新同步</button>
            </div>
          )}
          {runtime.result.warnings.length > 0 && runtime.result.warnings.map((w, i) => (
            <p key={i} className="text-xs text-[#E8A838]">⚠ {w}</p>
          ))}
        </div>
      )}

      {/* 设备抽屉 */}
      {drawerOpen && (
        <div className="fixed inset-y-0 right-0 w-96 bg-white border-l border-slate-200 shadow-xl z-50 p-6 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-black text-[#14241B]">设备管理</h3>
            <button onClick={() => setDrawerOpen(false)} type="button"><X size={20} /></button>
          </div>
          <div className="flex gap-2 mb-4">
            <button className={`px-3 py-1.5 rounded-lg text-sm font-bold ${drawerTab === "list" ? "bg-[#14241B] text-white" : "bg-slate-100"}`} onClick={() => setDrawerTab("list")} type="button">列表</button>
            <button className={`px-3 py-1.5 rounded-lg text-sm font-bold ${drawerTab === "register" ? "bg-[#14241B] text-white" : "bg-slate-100"}`} onClick={() => setDrawerTab("register")} type="button">注册</button>
          </div>
          {drawerTab === "list" ? (
            <div className="space-y-2">
              {cameraSetup.cameras.map(c => (
                <div key={c.camera_id} className="flex items-center justify-between rounded-xl border border-slate-200 p-3">
                  {editingCameraId === c.camera_id ? (
                    <div className="w-full space-y-2">
                      <input
                        aria-label="摄像头 ID"
                        className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
                        value={editingCameraForm.camera_id}
                        onChange={e => setEditingCameraForm(f => ({ ...f, camera_id: e.target.value }))}
                      />
                      <input
                        aria-label="摄像头名称"
                        className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
                        value={editingCameraForm.name}
                        onChange={e => setEditingCameraForm(f => ({ ...f, name: e.target.value }))}
                      />
                      <div className="flex justify-end gap-2">
                        <button className="quiet-button px-2.5 py-1 text-xs" onClick={() => setEditingCameraId(null)} type="button">取消</button>
                        <button className="green-button px-2.5 py-1 text-xs" disabled={savingCamera || runtime.isRecording} onClick={() => void handleUpdateCamera(c)} type="button">
                          {savingCamera ? "保存中..." : "保存"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="min-w-0 text-sm">
                        <p className="font-bold truncate">{c.name ?? c.camera_id}</p>
                        <p className="text-xs text-slate-500 truncate">ID：{c.camera_id}</p>
                        <p className="text-xs text-slate-500 truncate">{c.stream_url}</p>
                        {cameraSetup.probeLoading[c.camera_id] ? (
                          <p className="mt-1 text-xs text-slate-400">正在检测连接...</p>
                        ) : cameraSetup.probeResults[c.camera_id] ? (
                          cameraSetup.probeResults[c.camera_id].online ? (
                            <p className="mt-1 text-xs font-medium text-[#168A34]">
                              可用{cameraSetup.probeResults[c.camera_id].resolution ? ` · ${cameraSetup.probeResults[c.camera_id].resolution}` : ""}{cameraSetup.probeResults[c.camera_id].latency_ms != null ? ` · ${cameraSetup.probeResults[c.camera_id].latency_ms}ms` : ""}
                            </p>
                          ) : (
                            <p className="mt-1 text-xs font-medium text-[#C92A2A]">不可用：{cameraSetup.probeResults[c.camera_id].error_message || "无法读取视频流"}</p>
                          )
                        ) : cameraSetup.probeErrors[c.camera_id] ? (
                          <p className="mt-1 text-xs font-medium text-[#C92A2A]">检测失败：{cameraSetup.probeErrors[c.camera_id]}</p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <button className="p-1.5 rounded-lg hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40" disabled={runtime.isRecording || cameraSetup.probeLoading[c.camera_id]} onClick={() => void cameraSetup.runProbe(c.camera_id)} title="检测连接是否可用" type="button">
                          <Wifi size={14} />
                        </button>
                        <button className="p-1.5 rounded-lg hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40" disabled={runtime.isRecording} onClick={() => startEditingCamera(c)} title="修改设备 ID 和名称" type="button">
                          <Pencil size={14} />
                        </button>
                        <button className="p-1.5 rounded-lg text-[#C92A2A] hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40" disabled={runtime.isRecording} onClick={() => void handleDeleteCamera(c)} title={runtime.isRecording ? "录制中无法删除设备" : "删除设备"} type="button">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
              <button className="w-full rounded-xl border border-dashed border-slate-300 py-2 text-sm text-slate-500 hover:bg-slate-50" onClick={() => setDrawerTab("register")} type="button">
                <PlusCircle size={14} className="inline mr-1" />注册新设备
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <input className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" placeholder="摄像头 ID" value={newCameraForm.camera_id} onChange={e => setNewCameraForm(f => ({ ...f, camera_id: e.target.value }))} />
              <input className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" placeholder="名称" value={newCameraForm.name} onChange={e => setNewCameraForm(f => ({ ...f, name: e.target.value }))} />
              <input className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" placeholder="RTSP 地址" value={newCameraForm.stream_url} onChange={e => setNewCameraForm(f => ({ ...f, stream_url: e.target.value }))} />
              <button className="w-full rounded-xl bg-[#22C55E] py-2.5 text-sm font-bold text-white" onClick={async () => {
                try { await createCamera(newCameraForm as any); cameraSetup.loadCameras(); setDrawerTab("list"); } catch { /* ignore */ }
              }} type="button">注册</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
