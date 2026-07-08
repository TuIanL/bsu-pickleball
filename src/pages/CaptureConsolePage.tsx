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
import type { AppPath, CameraInfo, FieldSession, ProbeResult, RecordingSession, RecordingStartRequest, SessionTimelineEvent, TimelineEventCreate } from "../types/report";
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
} from "../services/analysisClient";
import { quickEventsForMode, type QuickEventDef } from "../services/timelineQuickEvents";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;
type ConsoleState = "preview" | "recording" | "stopped";

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

  // 录制计时器
  useEffect(() => {
    if (consoleState === "recording") {
      elapsedTimer.current = setInterval(() => {
        setElapsedSec((s) => s + 1);
      }, 1000);
    } else {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current);
    }
    return () => {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current);
    };
  }, [consoleState]);

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
        auto_analyze_after_stop: analysisIntent === "auto_analyze",
      };

      const recording = await startRecording(payload);
      setActiveRecording(recording);
      setConsoleState("recording");
      setElapsedSec(0);
      setPreviewStatus("idle"); // 录制时断开预览
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
    if (!activeRecording) return;
    try {
      const payload: TimelineEventCreate = {
        event_type: event.type,
        label: event.label,
        source: "manual",
        recording_session_id: activeRecording.session_id,
      };
      await createTimelineEvent(sessionId, payload);
      await loadTimelineEvents();
    } catch { /* ignore */ }
  };

  const handleCloseComplete = () => {
    setConsoleState("preview");
    setCompletedRecording(null);
    setPreviewKey((k) => k + 1);
  };

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
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
        {/* 左侧：实时预览 */}
        <div className="space-y-4">
          <div className="relative aspect-video rounded-2xl border border-[#DDE9D6] bg-[#0F172A] overflow-hidden">
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
        </div>

        {/* 右侧：设备状态 + 录制控制 */}
        <div className="space-y-4">
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
                    onClick={() => onNavigate(`/upload?videoId=${completedRecording.video_id}&source=recording`)}
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

      {/* 录制中：事件标记 + 时间线 */}
      {consoleState === "recording" && (
        <div className="mt-6 space-y-4">
          {/* 事件标记按钮 */}
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
            <h3 className="text-sm font-bold text-[#14241B] mb-3">场边事件标记</h3>
            <div className="flex flex-wrap gap-2">
              {quickEvents.map((event) => (
                <button
                  key={event.type}
                  className="rounded-xl border border-[#DDE9D6] bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:border-[#2F80ED]/40 hover:text-[#2F80ED] transition"
                  onClick={() => handleAddTimelineEvent(event)}
                  type="button"
                >
                  {event.label}
                </button>
              ))}
            </div>
          </div>

          {/* 时间线 */}
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
            <h3 className="text-sm font-bold text-[#14241B] mb-3">时间线</h3>
            {timelineEvents.length === 0 ? (
              <p className="text-xs text-slate-400">录制中，尚未有任何事件标记</p>
            ) : (
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {timelineEvents.slice(-10).reverse().map((evt) => (
                  <div key={evt.id} className="flex items-center gap-3 text-sm">
                    <span className="text-xs tabular-nums text-slate-400 w-14 shrink-0">
                      {evt.timestamp_ms != null ? formatElapsed(Math.floor(evt.timestamp_ms / 1000)) : "—:—"}
                    </span>
                    <span className="w-1.5 h-1.5 rounded-full bg-[#2F80ED] shrink-0" />
                    <span className="font-medium text-slate-700">{evt.label}</span>
                    {evt.note && <span className="text-slate-400 text-xs">{evt.note}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
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
                          className={`rounded-xl border p-3 text-left ${isCurrent ? "border-[#2F80ED]/40 bg-[#2F80ED]/6" : "border-[#DDE9D6]"}`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="min-w-0 flex-1">
                              <span className="text-sm font-bold text-[#14241B]">{cam.name}</span>
                              {isCurrent && (
                                <span className="ml-2 rounded px-1.5 py-0.5 text-xs bg-[#2F80ED]/10 text-[#2F80ED] font-bold">当前</span>
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
                                onClick={() => { setSelectedCameraId(cam.camera_id); setDrawerOpen(false); }}
                                type="button"
                              >
                                选择
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
