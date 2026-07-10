import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Camera,
  CheckCircle2,
  Clock,
  MapPin,
  Pause,
  Play,
  PlusCircle,
  RefreshCw,
  Square,
  Trash2,
  Upload,
  Users,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import type { AppPath, CameraInfo, FieldSession, ProbeResult, RecordingSession, RecordingStartRequest, SessionTimelineEvent, TimelineEventCreate, SyncRecordingSession, SyncTestResult, SyncStopResponse } from "../types/report";
import {
  getFieldSession,
  updateFieldSession,
  startFieldSession,
  completeFieldSession,
  listCameras,
  createCamera,
  deleteCamera,
  probeCamera,
  startRecording,
  stopRecording,
  listTimelineEvents,
  createTimelineEvent,
  listRecordings,
  getCameraPreviewUrl,
  startSyncRecording,
  stopSyncRecording,
  cancelSyncRecording,
  runSyncTest,
  getActiveSyncRecording,
} from "../services/analysisClient";
import { quickEventsForMode, type QuickEventDef } from "../services/timelineQuickEvents";
import { createOutboxItem, enqueueItem, createOutboxSender, MATCH_QUICK_EVENTS, type CodingOutboxItem } from "../services/codingOutbox";
import { getLiveCodingState, executeCodingAction, listSegments, type LiveCodingState, type CaptureSegmentSummary } from "../services/analysisClient";
import type { CodingActionType } from "../types/report";
import { MiniTimeline } from "../components/MiniTimeline";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;
type ConsoleState = "preview" | "recording" | "stopped";
type DualConsoleState = "setup" | "testing" | "recording" | "stopped";

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

export function CaptureConsolePage({ sessionId, onNavigate }: { sessionId: string; onNavigate: NavigateFn }) {
  // Field Session 数据
  const [fieldSession, setFieldSession] = useState<FieldSession | null>(null);
  const [loading, setLoading] = useState(true);

  // 控制台状态
  const [consoleState, setConsoleState] = useState<ConsoleState>("preview");
  const [activeRecording, setActiveRecording] = useState<RecordingSession | null>(null);
  const [completedRecording, setCompletedRecording] = useState<RecordingSession | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const elapsedTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // 摄像头与预览
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "displaying" | "failed">("idle");
  const [previewKey, setPreviewKey] = useState(0);
  const previewUrl = useMemo(() => getCameraPreviewUrl(selectedCameraId || undefined), [selectedCameraId]);

  // 设备抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResult>>({});
  const [drawerTab, setDrawerTab] = useState<"list" | "register">("list");
  const [newCameraForm, setNewCameraForm] = useState({ camera_id: "", name: "", stream_url: "", protocol: "rtsp" as const });

  // 时间线事件
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);

  // analysisIntent（从 sessionStorage 恢复）
  const [analysisIntent, setAnalysisIntent] = useState<string>("ask_after_recording");
  const [recordingFps, setRecordingFps] = useState<number>(60);

  // ── 实时编码状态 ──
  const [captureTakeId, setCaptureTakeId] = useState<string | null>(null);
  const [liveCodingState, setLiveCodingState] = useState<LiveCodingState | null>(null);
  const [outboxItems, setOutboxItems] = useState<CodingOutboxItem[]>([]);
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const outboxSenderRef = useRef<ReturnType<typeof createOutboxSender> | null>(null);
  const lastActionTimeRef = useRef<number>(0);

  // ── 双摄同步录制状态 ──
  const isDualMode = fieldSession?.camera_setup === "dual";
  const [dualState, setDualState] = useState<DualConsoleState>("setup");
  const [selectedSlots, setSelectedSlots] = useState<{ cam_1: string; cam_2: string }>(() => {
    try {
      const stored = sessionStorage.getItem(`capture.slots.${sessionId}`);
      if (stored) return JSON.parse(stored);
    } catch { /* ignore */ }
    return { cam_1: "", cam_2: "" };
  });
  const [slotSelecting, setSlotSelecting] = useState<"cam_1" | "cam_2" | null>(null);
  const [dualTestResult, setDualTestResult] = useState<SyncTestResult | null>(null);
  const [activeSyncSession, setActiveSyncSession] = useState<SyncRecordingSession | null>(null);
  const [dualStopResponse, setDualStopResponse] = useState<SyncStopResponse | null>(null);
  const [dualElapsedSec, setDualElapsedSec] = useState(0);
  const [dualSegmentIndex, setDualSegmentIndex] = useState(0);
  const dualElapsedTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // ====== 加载 Field Session ======
  const loadFieldSession = useCallback(async () => {
    try {
      const fs = await getFieldSession(sessionId);
      setFieldSession(fs);

      // 恢复 analysisIntent
      try {
        const stored = sessionStorage.getItem(`capture.analysisIntent.${sessionId}`);
        if (stored) setAnalysisIntent(stored);
      } catch { /* ignore */ }

      // 恢复双摄槽位选择
      try {
        const slots = sessionStorage.getItem(`capture.slots.${sessionId}`);
        if (slots) setSelectedSlots(JSON.parse(slots));
      } catch { /* ignore */ }

      // 恢复 selectedCameraId
      try {
        const camId = sessionStorage.getItem(`capture.selectedCameraId.${sessionId}`);
        if (camId) setSelectedCameraId(camId);
      } catch { /* ignore */ }
    } catch {
      setFieldSession(null);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // ====== 加载摄像头列表 ======
  const loadCameras = useCallback(async () => {
    try {
      const cam = await listCameras();
      setCameras(cam);
    } catch { /* ignore */ }
  }, []);

  // ====== 加载时间线事件 ======
  const loadTimelineEvents = useCallback(async () => {
    try {
      const events = await listTimelineEvents(sessionId);
      setTimelineEvents(events);
    } catch {
      setTimelineEvents([]);
    }
  }, [sessionId]);

  const loadSegmentsData = useCallback(async () => {
    if (!captureTakeId) return;
    try {
      const segs = await listSegments(captureTakeId);
      setSegments(segs ?? []);
    } catch { /* ignore */ }
  }, [captureTakeId]);

  useEffect(() => {
    void loadFieldSession();
    void loadCameras();
    void loadTimelineEvents();
  }, [loadFieldSession, loadCameras, loadTimelineEvents]);

  // 摄像头切换时重置预览
  useEffect(() => {
    if (!selectedCameraId) {
      setPreviewStatus("idle");
    } else {
      setPreviewStatus("loading");
      setPreviewKey((k) => k + 1);
    }
  }, [selectedCameraId]);

  // 录制计时器 + 定期刷新事件/segments
  useEffect(() => {
    if (consoleState === "recording") {
      elapsedTimer.current = setInterval(() => {
        setElapsedSec((s) => s + 1);
      }, 1000);
      const pollTimer = setInterval(() => {
        loadTimelineEvents();
        void loadSegmentsData();
      }, 5000);
      return () => {
        clearInterval(pollTimer);
        if (elapsedTimer.current) clearInterval(elapsedTimer.current);
      };
    } else {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current);
    }
    return () => {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current);
    };
  }, [consoleState, loadTimelineEvents, loadSegmentsData]);

  // 双摄录制计时器 + 已选槽位持久化
  useEffect(() => {
    if (dualState === "recording") {
      dualElapsedTimer.current = setInterval(() => {
        setDualElapsedSec((s) => s + 1);
      }, 1000);
    } else {
      if (dualElapsedTimer.current) clearInterval(dualElapsedTimer.current);
    }
    return () => {
      if (dualElapsedTimer.current) clearInterval(dualElapsedTimer.current);
    };
  }, [dualState]);

  // 持久化槽位选择
  useEffect(() => {
    try {
      sessionStorage.setItem(`capture.slots.${sessionId}`, JSON.stringify(selectedSlots));
    } catch { /* ignore */ }
  }, [selectedSlots, sessionId]);

  // 双摄录制中轮询会话状态
  useEffect(() => {
    if (dualState !== "recording" || !activeSyncSession) return;
    const timer = setInterval(async () => {
      try {
        const session = await getActiveSyncRecording();
        if (session && session.status !== "recording") {
          // 录制已结束（可能异常退出）
          setActiveSyncSession(session);
          setDualState("stopped");
          setDualStopResponse({
            session,
            default_analysis_video_id: session.default_analysis_video_id,
            analysis_available: !!session.default_analysis_video_id,
            analysis_blocked_reason: session.error_message ?? undefined,
          });
        } else if (session) {
          setActiveSyncSession(session);
          setDualSegmentIndex(session.segments.length);
        }
      } catch { /* polling error - ignore */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [dualState, activeSyncSession?.session_id]);

  // ====== 操作函数 ======
  const handleProbe = async (cameraId: string) => {
    try {
      const result = await probeCamera(cameraId);
      setProbeResults((prev) => ({ ...prev, [cameraId]: result }));
    } catch { /* ignore */ }
  };

  const handleDeleteCamera = async (cameraId: string) => {
    try {
      await deleteCamera(cameraId);
      setCameras((prev) => prev.filter((c) => c.camera_id !== cameraId));
      if (selectedCameraId === cameraId) setSelectedCameraId("");
    } catch { /* ignore */ }
  };

  const handleRegisterCamera = async () => {
    try {
      await createCamera(newCameraForm);
      setNewCameraForm({ camera_id: "", name: "", stream_url: "", protocol: "rtsp" });
      setDrawerTab("list");
      await loadCameras();
    } catch { /* ignore */ }
  };

  const handleStartRecording = async () => {
    if (!selectedCameraId) return;

    try {
      // 先 startFieldSession
      if (fieldSession && fieldSession.status !== "live") {
        const updated = await startFieldSession(sessionId);
        setFieldSession(updated);
      }

      const payload: RecordingStartRequest = {
        camera_id: selectedCameraId,
        field_session_id: sessionId,
        court_name: fieldSession?.court_name || "",
        match_format: (fieldSession?.match_format || "doubles") as "singles" | "doubles",
        fps: recordingFps,
        auto_analyze_after_stop: analysisIntent === "auto_analyze",
      };

      const recording = await startRecording(payload);
      setActiveRecording(recording);
      setConsoleState("recording");
      setElapsedSec(0);
      setPreviewStatus("idle");

      // 设置 capture_take_id 并初始化 outbox
      if (recording.capture_take_id) {
        setCaptureTakeId(recording.capture_take_id);
        try {
          const state = await getLiveCodingState(recording.capture_take_id);
          setLiveCodingState(state);
        } catch { /* live-state 可能暂不存在，稍后初始化 */ }
      }
    } catch { /* ignore */ }
  };

  const handleStopRecording = async () => {
    if (!activeRecording) return;
    try {
      setPreviewStatus("loading");
      const stopped = await stopRecording(activeRecording.session_id);
      setCompletedRecording(stopped);
      setConsoleState("stopped");
      setActiveRecording(null);
      setPreviewKey((k) => k + 1); // 恢复预览
    } catch { /* ignore */ }
  };

  const handleAddTimelineEvent = async (event: QuickEventDef) => {
    const takeId = captureTakeId ?? activeRecording?.capture_take_id;
    if (!takeId) return;

    // 误双击抑制：400ms
    const now = Date.now();
    if (now - lastActionTimeRef.current < 400) return;
    lastActionTimeRef.current = now;

    const timestampMs = elapsedSec * 1000;
    const action = (event.type ?? "add_note") as CodingActionType;

    // 乐观更新 liveCodingState
    if (liveCodingState) {
      const optimistic = { ...liveCodingState };
      if (action === "start_next_rally" && !optimistic.non_play) {
        optimistic.rally_ordinal += 1;
      } else if (action === "start_game") {
        optimistic.game_ordinal += 1;
        optimistic.rally_ordinal = 0;
      } else if (action === "start_set") {
        optimistic.set_ordinal += 1;
        optimistic.game_ordinal = 0;
        optimistic.rally_ordinal = 0;
      } else if (action === "toggle_non_play") {
        optimistic.non_play = !optimistic.non_play;
      } else if (action === "undo") {
        optimistic.rally_ordinal = Math.max(0, optimistic.rally_ordinal - 1);
      }
      setLiveCodingState(optimistic);
    }

    const item = createOutboxItem(takeId, action, timestampMs, event.payload);
    enqueueItem(item);
    setOutboxItems((prev) => [...prev, item]);
    outboxSenderRef.current?.flush();
  };

  const handleCloseComplete = () => {
    setConsoleState("preview");
    setCompletedRecording(null);
    setPreviewKey((k) => k + 1);
  };

  // ── 双摄操作函数 ──
  const handleDualTest = async () => {
    if (!selectedSlots.cam_1 || !selectedSlots.cam_2) return;
    setDualState("testing");
    try {
      const result = await runSyncTest({
        cam_1_id: selectedSlots.cam_1,
        cam_2_id: selectedSlots.cam_2,
        duration: 5,
      });
      setDualTestResult(result);
    } catch { /* ignore */ }
    setDualState("setup");
  };

  const handleDualStartRecording = async () => {
    if (!selectedSlots.cam_1 || !selectedSlots.cam_2) return;
    try {
      if (fieldSession && fieldSession.status !== "live") {
        const updated = await startFieldSession(sessionId);
        setFieldSession(updated);
      }

      const session = await startSyncRecording({
        cam_1_id: selectedSlots.cam_1,
        cam_2_id: selectedSlots.cam_2,
        field_session_id: sessionId,
        court_name: fieldSession?.court_name || "",
        match_format: (fieldSession?.match_format || "doubles") as "singles" | "doubles",
        cam_1_angle: "baseline_high",
        cam_2_angle: "baseline_high",
        fps: recordingFps,
        auto_analyze_after_stop: analysisIntent === "auto_analyze",
      });
      setActiveSyncSession(session);
      setDualState("recording");
      setDualElapsedSec(0);
      setDualSegmentIndex(0);
    } catch { /* ignore */ }
  };

  const handleDualStopRecording = async () => {
    if (!activeSyncSession) return;
    try {
      const response = await stopSyncRecording(activeSyncSession.session_id);
      setDualState("stopped");
      setDualStopResponse(response);
      setActiveSyncSession(response.session);
    } catch { /* ignore */ }
  };

  const handleDualCloseComplete = () => {
    setDualState("setup");
    setDualStopResponse(null);
    setActiveSyncSession(null);
    setDualTestResult(null);
  };

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };

  const formatMs = (ms: number) => {
    const totalSec = Math.floor(ms / 1000);
    return formatElapsed(totalSec);
  };

  const quickEvents = useMemo(
    () => quickEventsForMode(fieldSession?.capture_mode || "practice"),
    [fieldSession?.capture_mode],
  );

  const currentCamera = cameras.find((c) => c.camera_id === selectedCameraId);
  const isOnline = selectedCameraId ? (probeResults[selectedCameraId]?.online ?? null) : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-slate-400">加载采集任务…</p>
      </div>
    );
  }

  if (!fieldSession) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-slate-500">采集任务未找到</p>
        <button className="quiet-button px-4 py-2" onClick={() => onNavigate("/capture")} type="button">
          返回采集任务列表
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 py-6 lg:py-8">
      {/* 顶部信息栏 */}
      <div className="flex flex-wrap items-center gap-4 mb-6">
        <button className="quiet-button p-2" onClick={() => onNavigate("/capture")} type="button" title="返回">
          <ArrowLeft2 size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-black text-[#14241B] truncate">
            {fieldSession.title || "采集控制台"}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-slate-500">
            {fieldSession.court_name && (
              <span className="inline-flex items-center gap-1"><MapPin size={14} /> {fieldSession.court_name}</span>
            )}
            <span className="inline-flex items-center gap-1">
              {captureModeLabel[fieldSession.capture_mode] ?? fieldSession.capture_mode}
            </span>
            <span className="inline-flex items-center gap-1">
              <Users size={14} /> {matchFormatLabel[fieldSession.match_format] ?? fieldSession.match_format}
            </span>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
              fieldSession.status === "live"
                ? "bg-[#22C55E]/12 text-[#168A34]"
                : "bg-slate-100 text-slate-500"
            }`}>
              {statusLabel[fieldSession.status] ?? fieldSession.status}
            </span>
          </div>
        </div>
      </div>

      {/* 主体：左预览 + 右控制 */}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* 左侧预览区 */}
        <div className="space-y-4">

          {/* === 双摄双路预览 === */}
          {isDualMode ? (
            <div className="grid grid-cols-2 gap-3">
              {/* 底线机位 A */}
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-xs text-[#2F80ED] font-bold">
                  <Camera size={12} /> 底线机位 A
                  {selectedSlots.cam_1 && probeResults[selectedSlots.cam_1]?.online === true && (
                    <Wifi size={10} className="text-[#22C55E]" />
                  )}
                </div>
                <div className="relative aspect-video rounded-xl border border-[#DDE9D6] bg-[#0F172A] overflow-hidden">
                  {selectedSlots.cam_1 && getCameraPreviewUrl(selectedSlots.cam_1) && dualState !== "recording" ? (
                    <img
                      key={`dual-preview-cam1-${previewKey}`}
                      src={getCameraPreviewUrl(selectedSlots.cam_1)}
                      alt="底线机位 A 预览"
                      className="h-full w-full object-contain"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                        (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                      }}
                    />
                  ) : null}
                  {(!selectedSlots.cam_1 || dualState === "recording") && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                      <Camera size={24} className="text-white/30" />
                      <p className="text-white/50 text-xs">
                        {dualState === "recording" ? "录制中" : "未选择摄像头"}
                      </p>
                    </div>
                  )}
                  <div className="hidden absolute inset-0 flex items-center justify-center bg-[#0F172A]">
                    <p className="text-white/50 text-xs">预览加载失败</p>
                  </div>
                </div>
              </div>

              {/* 底线机位 B */}
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-xs text-[#168A34] font-bold">
                  <Camera size={12} /> 底线机位 B
                  {selectedSlots.cam_2 && probeResults[selectedSlots.cam_2]?.online === true && (
                    <Wifi size={10} className="text-[#22C55E]" />
                  )}
                </div>
                <div className="relative aspect-video rounded-xl border border-[#DDE9D6] bg-[#0F172A] overflow-hidden">
                  {selectedSlots.cam_2 && getCameraPreviewUrl(selectedSlots.cam_2) && dualState !== "recording" ? (
                    <img
                      key={`dual-preview-cam2-${previewKey}`}
                      src={getCameraPreviewUrl(selectedSlots.cam_2)}
                      alt="底线机位 B 预览"
                      className="h-full w-full object-contain"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                        (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                      }}
                    />
                  ) : null}
                  {(!selectedSlots.cam_2 || dualState === "recording") && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                      <Camera size={24} className="text-white/30" />
                      <p className="text-white/50 text-xs">
                        {dualState === "recording" ? "录制中" : "未选择摄像头"}
                      </p>
                    </div>
                  )}
                  <div className="hidden absolute inset-0 flex items-center justify-center bg-[#0F172A]">
                    <p className="text-white/50 text-xs">预览加载失败</p>
                  </div>
                </div>
              </div>

              {/* 录制中指示 */}
              {dualState === "recording" && (
                <div className="col-span-2 flex items-center justify-center gap-2 rounded-full bg-[#FF4D4F]/90 px-3 py-1.5 text-white text-sm font-bold">
                  <span className="grid size-2 rounded-full bg-white animate-pulse" />
                  录制中 {formatElapsed(dualElapsedSec)}
                </div>
              )}
            </div>
          ) : (
            <div className="relative aspect-video rounded-2xl border border-[#DDE9D6] bg-[#0F172A] overflow-hidden">
              {/* 单摄预览 */}
            {previewStatus === "loading" && (
              <div className="absolute inset-0 flex items-center justify-center">
                <RefreshCw size={24} className="animate-spin text-white/50" />
              </div>
            )}
            {previewStatus === "failed" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <WifiOff size={32} className="text-white/40" />
                <p className="text-white/60 text-sm">无法加载预览</p>
                <button
                  className="rounded-lg bg-white/10 px-3 py-1.5 text-xs text-white font-medium hover:bg-white/20"
                  onClick={() => { setPreviewStatus("loading"); setPreviewKey((k) => k + 1); }}
                  type="button"
                >
                  重试
                </button>
              </div>
            )}
            {!selectedCameraId && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <Camera size={40} className="text-white/30" />
                <p className="text-white/50 text-sm">请在右侧设备区选择摄像头</p>
                <button
                  className="rounded-xl bg-white/10 px-4 py-2 text-sm text-white font-medium hover:bg-white/20"
                  onClick={() => setDrawerOpen(true)}
                  type="button"
                >
                  选择摄像头
                </button>
              </div>
            )}
            {selectedCameraId && previewUrl && previewStatus !== "failed" && (
              <img
                key={previewKey}
                src={previewUrl}
                alt="摄像头预览"
                className="h-full w-full object-contain"
                onLoad={() => setPreviewStatus("displaying")}
                onError={() => setPreviewStatus("failed")}
              />
            )}

            {/* 录制中指示 */}
            {consoleState === "recording" && (
              <div className="absolute top-4 left-4 flex items-center gap-2 rounded-full bg-[#FF4D4F]/90 px-3 py-1.5 text-white text-sm font-bold">
                <span className="grid size-2 rounded-full bg-white animate-pulse" />
                录制中 {formatElapsed(elapsedSec)}
              </div>
            )}
            </div>
          )}
        </div>

        {/* 右侧：设备状态 + 录制控制 */}
        <div className="space-y-4">
          {isDualMode ? (
            <>
              {/* === 双摄控制台 === */}
              {/* 机位槽位卡片 */}
              <div className="sport-card p-4">
                <h3 className="text-sm font-bold text-[#14241B] mb-3">双摄机位</h3>

                {/* 底线机位 A */}
                <SlotCard
                  role="cam_1"
                  label="底线机位 A"
                  cameraId={selectedSlots.cam_1}
                  cameras={cameras}
                  probeResults={probeResults}
                  onSelect={() => { setSlotSelecting("cam_1"); setDrawerOpen(true); }}
                  onProbe={handleProbe}
                />

                {/* 底线机位 B */}
                <SlotCard
                  role="cam_2"
                  label="底线机位 B"
                  cameraId={selectedSlots.cam_2}
                  cameras={cameras}
                  probeResults={probeResults}
                  onSelect={() => { setSlotSelecting("cam_2"); setDrawerOpen(true); }}
                  onProbe={handleProbe}
                />
              </div>

              {/* 双摄录制控制 */}
              <div className="sport-card p-4">
                <h3 className="text-sm font-bold text-[#14241B] mb-3">同步录制控制</h3>
                <label className="mb-3 block text-xs font-bold text-slate-500">
                  视频帧率
                  <select
                    className="field-input mt-1"
                    disabled={dualState !== "setup"}
                    onChange={(event) => setRecordingFps(Number(event.target.value))}
                    value={recordingFps}
                  >
                    {[24, 25, 30, 50, 60].map((fps) => (
                      <option key={fps} value={fps}>{fps} fps</option>
                    ))}
                  </select>
                </label>

                {/* 短录测试 */}
                {(dualState === "setup" || dualState === "testing") && (
                  <div className="mb-3">
                    <button
                      className="w-full rounded-xl border border-[#2F80ED]/30 bg-[#2F80ED]/5 py-2.5 text-sm font-bold text-[#2F80ED] hover:bg-[#2F80ED]/10 transition disabled:opacity-40"
                      onClick={handleDualTest}
                      disabled={!selectedSlots.cam_1 || !selectedSlots.cam_2 || dualState === "testing"}
                      type="button"
                    >
                      <RefreshCw size={14} className={`inline mr-1 ${dualState === "testing" ? "animate-spin" : ""}`} />
                      {dualState === "testing" ? "测试中…" : "短录测试 (5秒)"}
                    </button>
                    {dualTestResult && (
                      <TestResultCard result={dualTestResult} />
                    )}
                  </div>
                )}

                {/* 开始录制按钮 */}
                {dualState === "setup" && (
                  <button
                    className="green-button w-full flex items-center justify-center gap-2 py-3"
                    onClick={handleDualStartRecording}
                    disabled={!selectedSlots.cam_1 || !selectedSlots.cam_2}
                    type="button"
                  >
                    <Play size={18} fill="currentColor" />
                    开始同步录制
                  </button>
                )}

                {/* 录制中 */}
                {dualState === "recording" && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-center gap-2 rounded-xl bg-[#FF4D4F]/10 py-2 px-3">
                      <span className="grid size-2 rounded-full bg-[#FF4D4F] animate-pulse" />
                      <span className="text-sm font-bold text-[#FF4D4F]">
                        同步录制中 {formatElapsed(dualElapsedSec)}
                      </span>
                    </div>
                    {activeSyncSession && (
                      <div className="text-xs text-slate-500 space-y-1 px-1">
                        <div className="flex justify-between">
                          <span>当前分段</span>
                          <span className="font-bold">{dualSegmentIndex || 1}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>已保存分段</span>
                          <span className="font-bold">{activeSyncSession.segments?.length ?? 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>重启次数</span>
                          <span className="font-bold">{activeSyncSession.total_restarts}</span>
                        </div>
                        {activeSyncSession.error_message && (
                          <p className="text-[#FF4D4F] truncate">错误: {activeSyncSession.error_message}</p>
                        )}
                      </div>
                    )}
                    <button
                      className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-[#FF4D4F] text-white font-bold hover:bg-[#E04344] transition"
                      onClick={handleDualStopRecording}
                      type="button"
                    >
                      <Square size={18} fill="currentColor" />
                      停止录制
                    </button>
                  </div>
                )}

                {/* 录制完成 */}
                {dualState === "stopped" && dualStopResponse && (
                  <div className="rounded-xl bg-[#22C55E]/10 p-4 text-center space-y-2">
                    <CheckCircle2 size={24} className="mx-auto text-[#168A34]" />
                    <p className="text-sm font-bold text-[#168A34]">同步录制已完成</p>
                    <div className="text-xs text-slate-600 space-y-1">
                      <p>时长: {formatElapsed(dualElapsedSec)}</p>
                      {dualStopResponse.analysis_available ? (
                        <p className="text-[#168A34]">分析就绪</p>
                      ) : (
                        <p className="text-[#E8A838]">{dualStopResponse.analysis_blocked_reason ?? "分析不可用"}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
          {/* 设备状态区 */}
          <div className="sport-card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-[#14241B]">设备状态</h3>
            </div>
            {currentCamera ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  {isOnline === true ? (
                    <Wifi size={14} className="text-[#22C55E]" />
                  ) : isOnline === false ? (
                    <WifiOff size={14} className="text-[#FF4D4F]" />
                  ) : (
                    <WifiOff size={14} className="text-slate-300" />
                  )}
                  <span className="text-sm font-bold text-[#14241B]">{currentCamera.name}</span>
                  <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                    isOnline === true
                      ? "bg-[#22C55E]/12 text-[#168A34]"
                      : isOnline === false
                        ? "bg-[#FF4D4F]/12 text-[#C92A2A]"
                        : "bg-slate-100 text-slate-400"
                  }`}>
                    {isOnline === true ? "已连接" : isOnline === false ? "离线" : "未检测"}
                  </span>
                </div>
                <p className="text-xs text-slate-400 truncate">{currentCamera.stream_url}</p>
                <div className="flex gap-2 pt-1">
                  <button
                    className="text-xs font-medium text-[#2F80ED] hover:underline"
                    onClick={() => handleProbe(selectedCameraId)}
                    type="button"
                  >
                    <RefreshCw size={12} className="inline mr-1" />重新探测
                  </button>
                  <button
                    className="text-xs font-medium text-slate-500 hover:underline"
                    onClick={() => setDrawerOpen(true)}
                    type="button"
                  >
                    更换摄像头
                  </button>
                </div>
              </div>
            ) : (
              <div className="py-3 text-center">
                <p className="text-sm text-slate-400 mb-2">未选择摄像头</p>
                <button
                  className="text-sm font-bold text-[#2F80ED] hover:underline"
                  onClick={() => setDrawerOpen(true)}
                  type="button"
                >
                  选择摄像头
                </button>
              </div>
            )}
          </div>

          {/* 录制控制区 */}
          <div className="sport-card p-4">
            <h3 className="text-sm font-bold text-[#14241B] mb-3">录制控制</h3>
            <label className="mb-3 block text-xs font-bold text-slate-500">
              视频帧率
              <select
                className="field-input mt-1"
                disabled={consoleState !== "preview"}
                onChange={(event) => setRecordingFps(Number(event.target.value))}
                value={recordingFps}
              >
                {[24, 25, 30, 50, 60].map((fps) => (
                  <option key={fps} value={fps}>{fps} fps</option>
                ))}
              </select>
            </label>
            {consoleState === "preview" && (
              <button
                className="green-button w-full flex items-center justify-center gap-2 py-3"
                onClick={handleStartRecording}
                disabled={!selectedCameraId}
                type="button"
              >
                <Play size={18} fill="currentColor" />
                开始录制
              </button>
            )}
            {consoleState === "recording" && (
              <button
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-[#FF4D4F] text-white font-bold hover:bg-[#E04344] transition"
                onClick={handleStopRecording}
                type="button"
              >
                <Square size={18} fill="currentColor" />
                停止录制
              </button>
            )}
            {consoleState === "stopped" && (
              <div className="rounded-xl bg-[#22C55E]/10 p-4 text-center">
                <CheckCircle2 size={24} className="mx-auto text-[#168A34] mb-2" />
                <p className="text-sm font-bold text-[#168A34]">录制已完成</p>
              </div>
            )}
            {consoleState === "recording" && (
              <p className="text-xs text-slate-400 text-center mt-2">录制期间预览已暂停</p>
            )}
          </div>
            </>
          )}
        </div>
      </div>

      {/* 录制完成面板 */}
      {consoleState === "stopped" && completedRecording && (
        <div className="mt-6 rounded-2xl border border-[#22C55E]/30 bg-[#22C55E]/8 p-6">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-lg font-black text-[#14241B]">录制已完成</h3>
              <div className="mt-2 flex flex-wrap gap-3 text-sm text-slate-600">
                <span>时长：{formatElapsed(elapsedSec)}</span>
                <span>摄像头：{currentCamera?.name || selectedCameraId}</span>
                <span>场地：{fieldSession.court_name || "—"}</span>
              </div>
            </div>
            <button
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100"
              onClick={handleCloseComplete}
              type="button"
            >
              <X size={18} />
            </button>
          </div>

          <div className="mt-5 flex flex-wrap gap-3">
            {analysisIntent === "auto_analyze" && completedRecording.auto_analysis_job_id ? (
              <>
                <button
                  className="green-button inline-flex items-center gap-2 px-4 py-2.5 text-sm"
                  onClick={() => onNavigate(`/analysis/${completedRecording.auto_analysis_job_id}`)}
                  type="button"
                >
                  <SparklesIcon size={16} /> 查看分析进度
                </button>
              </>
            ) : (
              <>
                {analysisIntent !== "save_only" && completedRecording.video_id && (
                  <button
                    className="green-button inline-flex items-center gap-2 px-4 py-2.5 text-sm"
                    onClick={() => onNavigate(`/upload?videoId=${completedRecording.video_id}&source=recording&sessionId=${completedRecording.session_id}&fps=${completedRecording.fps}`)}
                    type="button"
                  >
                    <Upload size={16} /> 创建分析任务
                  </button>
                )}
              </>
            )}
            <button
              className="quiet-button inline-flex items-center gap-2 px-4 py-2.5 text-sm"
              onClick={handleCloseComplete}
              type="button"
            >
              <Play size={16} fill="currentColor" /> 继续采集
            </button>
          </div>
        </div>
      )}

      {/* 双摄录制完成面板 */}
      {dualState === "stopped" && dualStopResponse && (
        <div className="mt-6 rounded-2xl border border-[#22C55E]/30 bg-[#22C55E]/8 p-6">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-lg font-black text-[#14241B]">双摄同步录制已完成</h3>
              <div className="mt-2 flex flex-wrap gap-3 text-sm text-slate-600">
                <span>时长：{formatElapsed(dualElapsedSec)}</span>
                <span>分段数：{dualStopResponse.session.segments?.length ?? 0}</span>
                <span>重启次数：{dualStopResponse.session.total_restarts ?? 0}</span>
                <span>
                  底线机位 A：{cameras.find(c => c.camera_id === selectedSlots.cam_1)?.name ?? selectedSlots.cam_1}
                </span>
                <span>
                  底线机位 B：{cameras.find(c => c.camera_id === selectedSlots.cam_2)?.name ?? selectedSlots.cam_2}
                </span>
              </div>
            </div>
            <button
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100"
              onClick={handleDualCloseComplete}
              type="button"
            >
              <X size={18} />
            </button>
          </div>

          <div className="mt-5 flex flex-wrap gap-3">
            {dualStopResponse.analysis_available && dualStopResponse.default_analysis_video_id ? (
              <button
                className="green-button inline-flex items-center gap-2 px-4 py-2.5 text-sm"
                onClick={() => onNavigate(`/upload?videoId=${dualStopResponse.default_analysis_video_id}&source=recording&sessionId=${dualStopResponse.session.session_id}&fps=${dualStopResponse.session.fps}`)}
                type="button"
              >
                <Upload size={16} /> 创建分析任务
              </button>
            ) : (
              <p className="text-sm text-[#E8A838] py-2">
                分析不可用：{dualStopResponse.analysis_blocked_reason ?? "未知原因"}
              </p>
            )}
            <button
              className="quiet-button inline-flex items-center gap-2 px-4 py-2.5 text-sm"
              onClick={handleDualCloseComplete}
              type="button"
            >
              <Play size={16} fill="currentColor" /> 开始新录制
            </button>
          </div>
        </div>
      )}

      {/* 录制中：实时编码控制台 */}
      {(consoleState === "recording" || dualState === "recording") && (
        <div className="mt-6 space-y-4">
          {/* 当前结构 */}
          {liveCodingState && (
            <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
              <div className="flex items-center gap-4 text-sm font-bold text-[#14241B]">
                <span>当前：</span>
                <span className="text-[#F97316]">第{liveCodingState.set_ordinal || "?"}盘</span>
                <span className="text-[#3B82F6]">第{liveCodingState.game_ordinal || "?"}局</span>
                <span className="text-[#22C55E]">第{liveCodingState.rally_ordinal || "?"}分</span>
                {liveCodingState.non_play && <span className="text-[#6B7280]">（非比赛）</span>}
                <span className="text-xs text-slate-400 ml-auto">rev.{liveCodingState.revision}</span>
              </div>
            </div>
          )}

          {/* 事件按钮 */}
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
            <h3 className="text-sm font-bold text-[#14241B] mb-3">实时编码</h3>
            <div className="flex flex-wrap gap-2">
              {MATCH_QUICK_EVENTS.map((event) => {
                const colorMap: Record<string, string> = {
                  start_set: "bg-[#FFF7ED] border-[#F97316] text-[#F97316] hover:bg-[#F97316] hover:text-white",
                  start_game: "bg-[#EFF6FF] border-[#3B82F6] text-[#3B82F6] hover:bg-[#3B82F6] hover:text-white",
                  start_next_rally: "bg-[#F0FDF4] border-[#22C55E] text-[#22C55E] hover:bg-[#22C55E] hover:text-white",
                  end_rally: "bg-slate-50 border-slate-300 text-slate-500 hover:bg-slate-500 hover:text-white",
                  toggle_non_play: "bg-slate-50 border-slate-400 text-slate-500 hover:bg-slate-500 hover:text-white",
                  change_side: "bg-[#FAF5FF] border-[#A855F7] text-[#A855F7] hover:bg-[#A855F7] hover:text-white",
                  add_note: "bg-slate-50 border-slate-300 text-slate-500 hover:bg-slate-500 hover:text-white",
                  undo: "bg-[#FEF2F2] border-[#EF4444] text-[#EF4444] hover:bg-[#EF4444] hover:text-white",
                };
                const keyMap: Record<string, string> = {
                  start_set: "1", start_game: "2", start_next_rally: "3",
                  toggle_non_play: "4", change_side: "5", add_note: "H", undo: "⌫",
                  end_rally: "",
                };
                const colorClass = colorMap[event.type] ?? "";
                return (
                  <button
                    key={event.type}
                    className={`rounded-xl border px-3 py-2 text-xs font-bold transition ${colorClass}`}
                    onClick={() => handleAddTimelineEvent(event)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleAddTimelineEvent(event); }}
                    type="button"
                    title={event.note}
                  >
                    {event.label}{keyMap[event.type] ? ` [${keyMap[event.type]}]` : ""}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Outbox 状态 */}
          {outboxItems.filter((i) => i.status !== "synced").length > 0 && (
            <div className="rounded-2xl border border-[#FEF3C7] bg-[#FFFBEB] p-3">
              <h4 className="text-xs font-bold text-[#92400E] mb-1">同步状态</h4>
              <div className="text-xs text-[#92400E] space-y-0.5">
                {outboxItems.filter((i) => i.status !== "synced").slice(0, 5).map((item) => (
                  <div key={item.clientActionId} className="flex items-center gap-2">
                    <span>{item.action === "start_next_rally" ? "下一分" : item.action}</span>
                    <span className="opacity-60">{item.status === "sending" ? "⟳" : item.status === "failed" ? "✗" : item.status === "blocked" ? "⊘" : "⏳"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 事件时间线列表 */}
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
            <h3 className="text-sm font-bold text-[#14241B] mb-3">
              最近事件
              <span className="ml-2 text-xs font-normal text-slate-400">
                {timelineEvents.length} 条
              </span>
            </h3>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {timelineEvents.slice(-15).reverse().map((event) => (
                <div
                  key={event.id}
                  className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-1.5 text-xs"
                >
                  <span className="font-bold text-slate-600">{event.label || event.event_type}</span>
                  <span className="ml-2 text-slate-400 tabular-nums">
                    {formatMs(event.timestamp_ms)}
                  </span>
                  {event.note && (
                    <span className="ml-2 truncate text-slate-400">{event.note}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 多轨时间线 */}
      {(segments.length > 0 || timelineEvents.length > 0) && (
        <MiniTimeline
          segments={segments}
          events={timelineEvents}
          liveState={liveCodingState}
          totalDurationMs={Math.max(elapsedSec * 1000, 60000)}
          elapsedMs={elapsedSec * 1000}
        />
      )}
    </div>
      )}

      {/* 设备抽屉 */}
      {drawerOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-white shadow-2xl overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-[#DDE9D6] p-4 flex items-center justify-between">
              <h2 className="text-lg font-black text-[#14241B]">设备管理</h2>
              <button className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100" onClick={() => setDrawerOpen(false)} type="button">
                <X size={20} />
              </button>
            </div>

            <div className="p-4">
              {/* Tab 切换 */}
              <div className="flex gap-2 mb-4">
                <button
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold ${drawerTab === "list" ? "bg-[#17231D] text-white" : "bg-slate-100 text-slate-500"}`}
                  onClick={() => setDrawerTab("list")}
                  type="button"
                >
                  已注册摄像头
                </button>
                <button
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold ${drawerTab === "register" ? "bg-[#17231D] text-white" : "bg-slate-100 text-slate-500"}`}
                  onClick={() => setDrawerTab("register")}
                  type="button"
                >
                  <PlusCircle size={14} className="inline mr-1" />注册新摄像头
                </button>
              </div>

              {drawerTab === "list" && (
                <div className="space-y-2">
                  {cameras.length === 0 ? (
                    <p className="text-sm text-slate-400 py-4 text-center">还没有注册摄像头</p>
                  ) : (
                    cameras.map((cam) => {
                      const probe = probeResults[cam.camera_id];
                      const isCurrent = cam.camera_id === selectedCameraId;
                      return (
                        <div
                          key={cam.camera_id}
                          className={`rounded-xl border p-3 text-left ${isCurrent ? "border-[#2F80ED]/40 bg-[#2F80ED]/6" : slotSelecting && cam.camera_id === selectedSlots[slotSelecting] ? "border-[#2F80ED]/40 bg-[#2F80ED]/6" : "border-[#DDE9D6]"}`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="min-w-0 flex-1">
                              <span className="text-sm font-bold text-[#14241B]">{cam.name}</span>
                              {isCurrent && (
                                <span className="ml-2 rounded px-1.5 py-0.5 text-xs bg-[#2F80ED]/10 text-[#2F80ED] font-bold">当前</span>
                              )}
                              {slotSelecting && cam.camera_id === selectedSlots[slotSelecting] && (
                                <span className="ml-2 rounded px-1.5 py-0.5 text-xs bg-[#2F80ED]/10 text-[#2F80ED] font-bold">
                                  {slotSelecting === "cam_1" ? "底线机位 A" : "底线机位 B"}
                                </span>
                              )}
                              <p className="text-xs text-slate-400 truncate">{cam.camera_id} · {cam.protocol}</p>
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              {probe?.online === true && <Wifi size={12} className="text-[#22C55E]" />}
                              {probe?.online === false && <WifiOff size={12} className="text-[#FF4D4F]" />}
                            </div>
                          </div>
                          <div className="flex gap-2 mt-2">
                            {!isCurrent && (
                              <button
                                className="text-xs font-medium text-[#2F80ED] hover:underline"
                                onClick={() => {
                                  if (slotSelecting) {
                                    const otherSlot = slotSelecting === "cam_1" ? "cam_2" : "cam_1";
                                    if (selectedSlots[otherSlot] === cam.camera_id) return; // 阻止同一摄像头双选
                                    setSelectedSlots((prev) => ({ ...prev, [slotSelecting]: cam.camera_id }));
                                    setSlotSelecting(null);
                                  } else {
                                    setSelectedCameraId(cam.camera_id);
                                  }
                                  setDrawerOpen(false);
                                }}
                                type="button"
                              >
                                {slotSelecting ? `设为${slotSelecting === "cam_1" ? "底线机位 A" : "底线机位 B"}` : "选择"}
                              </button>
                            )}
                            <button
                              className="text-xs font-medium text-slate-500 hover:underline"
                              onClick={() => handleProbe(cam.camera_id)}
                              type="button"
                            >
                              <RefreshCw size={10} className="inline mr-1" />探测
                            </button>
                            <button
                              className="text-xs font-medium text-[#FF4D4F] hover:underline"
                              onClick={() => handleDeleteCamera(cam.camera_id)}
                              type="button"
                            >
                              <Trash2 size={10} className="inline mr-1" />删除
                            </button>
                          </div>
                          {probe && (
                            <p className="mt-1 text-xs text-slate-400">
                              {probe.online ? `在线 · ${probe.resolution ?? "—"} · ${probe.latency_ms != null ? `${probe.latency_ms}ms` : "—"}` : `离线 · ${probe.error_message ?? ""}`}
                            </p>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {drawerTab === "register" && (
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-600 mb-1">摄像头 ID</label>
                    <input
                      className="field-input w-full"
                      value={newCameraForm.camera_id}
                      onChange={(e) => setNewCameraForm((f) => ({ ...f, camera_id: e.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-600 mb-1">名称</label>
                    <input
                      className="field-input w-full"
                      value={newCameraForm.name}
                      onChange={(e) => setNewCameraForm((f) => ({ ...f, name: e.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-600 mb-1">流地址</label>
                    <input
                      className="field-input w-full"
                      placeholder="rtsp://192.168.1.100:8554/live"
                      value={newCameraForm.stream_url}
                      onChange={(e) => setNewCameraForm((f) => ({ ...f, stream_url: e.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-600 mb-1">协议</label>
                    <select
                      className="field-input w-full"
                      value={newCameraForm.protocol}
                      onChange={(e) => setNewCameraForm((f) => ({ ...f, protocol: e.target.value as "rtsp" }))}
                    >
                      <option value="rtsp">RTSP</option>
                      <option value="rtmp">RTMP</option>
                      <option value="http">HTTP</option>
                    </select>
                  </div>
                  <button
                    className="green-button w-full py-2.5 text-sm"
                    onClick={handleRegisterCamera}
                    disabled={!newCameraForm.camera_id || !newCameraForm.stream_url}
                    type="button"
                  >
                    注册
                  </button>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// 内联组件

// ── 双摄子组件 ──
function SlotCard({
  role,
  label,
  cameraId,
  cameras,
  probeResults,
  onSelect,
  onProbe,
}: {
  role: "cam_1" | "cam_2";
  label: string;
  cameraId: string;
  cameras: CameraInfo[];
  probeResults: Record<string, ProbeResult>;
  onSelect: () => void;
  onProbe: (id: string) => void;
}) {
  const camera = cameras.find((c) => c.camera_id === cameraId);
  const probe = cameraId ? probeResults[cameraId] : undefined;
  const isOnline = probe?.online;

  return (
    <div className={`rounded-xl border p-3 mb-2 ${role === "cam_1" ? "border-[#2F80ED]/30 bg-[#2F80ED]/4" : "border-green-200/50 bg-green-50/40"}`}>
      <div className="flex items-center justify-between mb-1">
        <span className={`text-xs font-bold ${role === "cam_1" ? "text-[#2F80ED]" : "text-[#168A34]"}`}>
          {label}
        </span>
        <button
          className="text-xs text-slate-400 hover:text-slate-600"
          onClick={onSelect}
          type="button"
        >
          {camera ? "更换" : "选择"}
        </button>
      </div>
      {camera ? (
        <div>
          <div className="flex items-center gap-2">
            {isOnline === true ? (
              <Wifi size={12} className="text-[#22C55E]" />
            ) : (
              <WifiOff size={12} className="text-slate-300" />
            )}
            <span className="text-sm font-bold text-[#14241B]">{camera.name}</span>
          </div>
          <div className="flex gap-2 mt-1">
            <button
              className="text-xs text-[#2F80ED] hover:underline"
              onClick={() => onProbe(cameraId)}
              type="button"
            >
              <RefreshCw size={10} className="inline mr-0.5" />探测
            </button>
            {probe && (
              <span className="text-xs text-slate-400">
                {probe.online ? `在线 · ${probe.resolution ?? "—"}` : "离线"}
              </span>
            )}
          </div>
        </div>
      ) : (
        <p className="text-xs text-slate-400">未分配摄像头</p>
      )}
    </div>
  );
}

function TestResultCard({ result }: { result: SyncTestResult }) {
  return (
    <div className="mt-3 rounded-lg border border-[#DDE9D6] bg-white p-3 text-xs space-y-2">
      <div className="flex items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 font-bold ${result.success ? "bg-[#22C55E]/12 text-[#168A34]" : "bg-[#FF4D4F]/12 text-[#C92A2A]"}`}>
          {result.success ? "测试通过" : "测试失败"}
        </span>
        <span className="text-slate-400">时长 {result.duration_sec}s</span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-slate-600">
        <div>
          <p className="font-bold">底线机位 A</p>
          <p>{result.cam_1_online ? "在线" : "离线"}</p>
          <p>{result.cam_1_file_size > 0 ? `${(result.cam_1_file_size / 1024).toFixed(1)}KB` : "空文件"}</p>
          {result.cam_1_error && <p className="text-[#FF4D4F] truncate">{result.cam_1_error}</p>}
          {result.cam_1_first_frame_url ? (
            <img src={result.cam_1_first_frame_url} alt="底线机位 A 首帧" className="mt-1 w-full rounded aspect-video object-cover border border-[#DDE9D6]" />
          ) : (
            result.cam_1_first_frame_exists === false && <p className="text-slate-400">首帧不可用</p>
          )}
        </div>
        <div>
          <p className="font-bold">底线机位 B</p>
          <p>{result.cam_2_online ? "在线" : "离线"}</p>
          <p>{result.cam_2_file_size > 0 ? `${(result.cam_2_file_size / 1024).toFixed(1)}KB` : "空文件"}</p>
          {result.cam_2_error && <p className="text-[#FF4D4F] truncate">{result.cam_2_error}</p>}
          {result.cam_2_first_frame_url ? (
            <img src={result.cam_2_first_frame_url} alt="底线机位 B 首帧" className="mt-1 w-full rounded aspect-video object-cover border border-[#DDE9D6]" />
          ) : (
            result.cam_2_first_frame_exists === false && <p className="text-slate-400">首帧不可用</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ArrowLeft2({ size = 24, ...props }: { size?: number; [key: string]: unknown }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  );
}

function SparklesIcon({ size = 24, ...props }: { size?: number; [key: string]: unknown }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z" />
      <path d="M18 14l.7 2.5L21 17.2l-2.3.7-.7 2.3-.7-2.3L15 17.2l2.3-.7z" />
    </svg>
  );
}
