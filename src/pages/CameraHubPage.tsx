import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Camera,
  Clock,
  Edit3,
  Play,
  PlusCircle,
  Radar,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { PageFrame } from "../components/PageFrame";
import { Modal } from "../components/platform/Modal";
import { quickEventsForMode, ACTION_TO_EVENT_TYPE, type QuickEventDef } from "../services/timelineQuickEvents";
import type {
  CameraInfo,
  CameraCreateRequest,
  ProbeResult,
  RecordingSession,
  RecordingStartRequest,
  FieldSession,
  FieldSessionCreate,
  SessionTimelineEvent,
  TimelineEventCreate,
  TimelineEventUpdate,
} from "../types/report";
import {
  listCameras,
  createCamera,
  deleteCamera,
  probeCamera,
  startRecording,
  stopRecording,
  cancelRecording,
  listRecordings,
  deleteRecording,
  createFieldSession,
  listFieldSessions,
  startFieldSession,
  completeFieldSession,
  archiveFieldSession,
  deleteFieldSession,
  createTimelineEvent,
  listTimelineEvents,
  updateTimelineEvent,
  deleteTimelineEvent,
  getVideoStreamUrl,
  getCameraPreviewUrl,
} from "../services/analysisClient";


/**
 * 球场采集管理页组件
 */
export function CameraHubPage({ onNavigate }: { onNavigate: NavigateFn }) {
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [sessions, setSessions] = useState<RecordingSession[]>([]);
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResult>>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Field Session 状态
  const [fieldSessions, setFieldSessions] = useState<FieldSession[]>([]);
  const [selectedFieldSession, setSelectedFieldSession] = useState<FieldSession | null>(null);
  const [showCreateFsModal, setShowCreateFsModal] = useState(false);
  const [newFsForm, setNewFsForm] = useState<FieldSessionCreate>({
    title: "", venue: "", court_name: "", capture_mode: "practice", match_format: "doubles", camera_setup: "single", notes: "",
  });

  // Timeline Event 状态
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);
  const [editingEvent, setEditingEvent] = useState<SessionTimelineEvent | null>(null);
  const [showEventModal, setShowEventModal] = useState(false);
  const [editForm, setEditForm] = useState<TimelineEventUpdate>({});
  const [editPayloadText, setEditPayloadText] = useState("{}");
  const activeSession = sessions.find((s) => s.status === "recording");

  const loadTimelineEvents = useCallback(async (fieldSessionId: string, recordingSessionId?: string) => {
    try {
      const events = await listTimelineEvents(
        fieldSessionId,
        recordingSessionId ? { recording_session_id: recordingSessionId } : undefined,
      );
      setTimelineEvents(events);
    } catch {
      setTimelineEvents([]);
    }
  }, []);

  const [recordingForm, setRecordingForm] = useState<RecordingStartRequest>({
    camera_id: "",
    court_name: "",
    match_format: "doubles",
    camera_angle: "baseline_high",
    fps: 60,
    resolution: "1920x1080",
    auto_analyze_after_stop: true,
  });

  // 当选中的 Field Session 变化时，预填录制表单并加载时间线事件
  useEffect(() => {
    if (!selectedFieldSession || selectedFieldSession.status === "archived") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clears events for the selected session.
      setTimelineEvents([]);
      return;
    }
    setRecordingForm((f) => ({
      ...f,
      field_session_id: selectedFieldSession.id,
      court_name: selectedFieldSession.court_name || "",
      match_format: (selectedFieldSession.match_format || "doubles") as "singles" | "doubles",
    }));
    const currentRecordingId = activeSession?.field_session_id === selectedFieldSession.id ? activeSession.session_id : undefined;
    void loadTimelineEvents(selectedFieldSession.id, currentRecordingId);
  }, [selectedFieldSession, activeSession?.field_session_id, activeSession?.session_id, loadTimelineEvents]);

  // Modal 状态
  const [showRegisterModal, setShowRegisterModal] = useState(false);

  const [newCamera, setNewCamera] = useState<CameraCreateRequest>({
    camera_id: "",
    name: "",
    stream_url: "",
    protocol: "rtsp",
    username: "",
    password: "",
  });

  // 预览状态（依赖 recordingForm，需在其后声明）
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "displaying" | "failed">("idle");
  const previewUrl = useMemo(() => getCameraPreviewUrl(recordingForm.camera_id), [recordingForm.camera_id]);
  const [previewKey, setPreviewKey] = useState(0);

  // 视频播放器状态
  const [playingSession, setPlayingSession] = useState<RecordingSession | null>(null);
  const [playbackError, setPlaybackError] = useState(false);

  const [loading, setLoading] = useState(false);

  // 当选中的摄像头变化时，重置预览状态
  useEffect(() => {
    if (!recordingForm.camera_id) {
      // Camera selection changes an external preview resource.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets preview state for the new camera.
      setPreviewStatus("idle");
    } else {
      setPreviewStatus("loading");
      setPreviewKey((k) => k + 1);
    }
  }, [recordingForm.camera_id]);

  const loadData = useCallback(async () => {
    try {
      const [cam, rec, fss] = await Promise.all([listCameras(), listRecordings(), listFieldSessions()]);
      setCameras(cam);
      setSessions(rec);
      setFieldSessions(fss);
    } catch {
      // backend not available, keep empty
    }
  }, []);

  const handleCreateFieldSession = async () => {
    setLoading(true);
    setError(null);
    try {
      const fs = await createFieldSession(newFsForm);
      setNewFsForm({ title: "", venue: "", court_name: "", capture_mode: "practice", match_format: "doubles", camera_setup: "single", notes: "" });
      setShowCreateFsModal(false);
      await loadData();
      setSelectedFieldSession(fs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建采集任务失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectDirectRecording = () => {
    setSelectedFieldSession(null);
    setRecordingForm((f) => ({
      ...f,
      field_session_id: undefined,
      court_name: "",
      match_format: "doubles",
    }));
  };

  const refreshSelectedFieldSession = async (fieldSessionId: string) => {
    const fss = await listFieldSessions();
    setFieldSessions(fss);
    setSelectedFieldSession(fss.find((fs) => fs.id === fieldSessionId) ?? null);
  };

  const handleFieldSessionAction = async (action: "start" | "complete" | "archive") => {
    if (!selectedFieldSession) return;
    setLoading(true);
    setError(null);
    try {
      const updated =
        action === "start"
          ? await startFieldSession(selectedFieldSession.id)
          : action === "complete"
            ? await completeFieldSession(selectedFieldSession.id)
            : await archiveFieldSession(selectedFieldSession.id);
      setSelectedFieldSession(updated);
      await refreshSelectedFieldSession(updated.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新采集任务状态失败");
      await loadData();
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteFieldSession = async () => {
    if (!selectedFieldSession) return;
    if (!window.confirm(`确定删除采集任务「${selectedFieldSession.title || selectedFieldSession.id}」吗？已有录制记录或时间线事件的任务会被后端保护。`)) return;
    setLoading(true);
    setError(null);
    try {
      await deleteFieldSession(selectedFieldSession.id);
      handleSelectDirectRecording();
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除采集任务失败");
      await loadData();
    } finally {
      setLoading(false);
    }
  };

  // —— Timeline Event 操作 ——

  const handleCreateQuickEvent = async (def: QuickEventDef) => {
    if (!selectedFieldSession) return;
    const recordingSessionId = activeSession?.session_id;
    const eventType = ACTION_TO_EVENT_TYPE[def.type] ?? "custom_marker";
    try {
      const payload: TimelineEventCreate = {
        event_type: eventType,
        source: def.source,
        label: def.label,
        note: def.note,
        payload_json: def.payload,
        recording_session_id: recordingSessionId,
      };
      if (recordingSessionId && activeSession?.started_at) {
        // 前端计算当前录制时间戳
        // eslint-disable-next-line react-hooks/purity -- this handler runs only after a user event.
        const elapsed = Date.now() - new Date(activeSession.started_at).getTime();
        payload.timestamp_ms = Math.max(0, elapsed);
      }
      await createTimelineEvent(selectedFieldSession.id, payload);
      await loadTimelineEvents(selectedFieldSession.id, recordingSessionId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建时间线事件失败");
    }
  };

  const handleEditEvent = (event: SessionTimelineEvent) => {
    setEditingEvent(event);
    setEditForm({
      label: event.label,
      note: event.note,
    });
    setEditPayloadText(JSON.stringify(event.payload_json ?? {}, null, 2));
    setShowEventModal(true);
  };

  const handleSaveEdit = async () => {
    if (!editingEvent || !selectedFieldSession) return;
    try {
      const payloadJson = JSON.parse(editPayloadText || "{}");
      if (!payloadJson || Array.isArray(payloadJson) || typeof payloadJson !== "object") {
        setError("Payload JSON 必须是 JSON 对象");
        return;
      }
      await updateTimelineEvent(editingEvent.id, { ...editForm, payload_json: payloadJson });
      setShowEventModal(false);
      setEditingEvent(null);
      const currentRecordingId = activeSession?.field_session_id === selectedFieldSession.id ? activeSession.session_id : undefined;
      await loadTimelineEvents(selectedFieldSession.id, currentRecordingId);
    } catch (e) {
      setError(e instanceof SyntaxError ? "Payload JSON 必须是有效 JSON" : e instanceof Error ? e.message : "更新时间线事件失败");
    }
  };

  const handleDeleteEvent = async (eventId: string) => {
    if (!selectedFieldSession) return;
    if (!window.confirm("确定删除该时间线事件吗？")) return;
    try {
      await deleteTimelineEvent(eventId);
      const currentRecordingId = activeSession?.field_session_id === selectedFieldSession.id ? activeSession.session_id : undefined;
      await loadTimelineEvents(selectedFieldSession.id, currentRecordingId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除时间线事件失败");
    }
  };

  useEffect(() => {
    // Refresh the external camera/session list after mount and explicit refreshes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes async list results.
    void loadData();
  }, [loadData, refreshKey]);

  useEffect(() => {
    if (!activeSession) return;
    const interval = window.setInterval(() => {
      void loadData();
    }, 3000);
    return () => window.clearInterval(interval);
  }, [activeSession, loadData]);

  const handleRegisterCamera = async () => {
    if (!newCamera.camera_id || !newCamera.name || !newCamera.stream_url) {
      setError("请填写摄像头 ID、名称和流地址");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await createCamera(newCamera);
      setNewCamera({ camera_id: "", name: "", stream_url: "", protocol: "rtsp", username: "", password: "" });
      setShowRegisterModal(false);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  const handleProbe = async (cameraId: string) => {
    try {
      const result = await probeCamera(cameraId);
      setProbeResults((prev) => ({ ...prev, [cameraId]: result }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "探测失败");
    }
  };

  const handleStartRecording = async () => {
    if (!recordingForm.camera_id) {
      setError("请选择摄像头");
      return;
    }
    // 录制前断开预览流，避免双连接导致摄像头掉帧
    setPreviewStatus("idle");
    setPreviewKey((k) => k + 1);
    setLoading(true);
    setError(null);
    try {
      await startRecording(recordingForm);
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "开始录制失败");
      await loadData();
    } finally {
      setLoading(false);
    }
  };

  const handleStopRecording = async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      await stopRecording(sessionId);
      await loadData();
      // 停止录制后恢复预览
      if (recordingForm.camera_id) {
        setPreviewStatus("loading");
        setPreviewKey((k) => k + 1);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "停止录制失败");
      await loadData();
    } finally {
      setLoading(false);
    }
  };

  const handleCancelRecording = async (sessionId: string) => {
    if (!window.confirm("确定要取消录制吗？已录制的视频将被丢弃。")) return;
    setLoading(true);
    setError(null);
    try {
      await cancelRecording(sessionId);
      await loadData();
      // 取消录制后恢复预览
      if (recordingForm.camera_id) {
        setPreviewStatus("loading");
        setPreviewKey((k) => k + 1);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "取消录制失败");
      await loadData();
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveCamera = async (cameraId: string) => {
    if (!window.confirm(`确定要删除摄像头 ${cameraId} 吗？`)) return;
    try {
      await deleteCamera(cameraId);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!window.confirm("确定要删除该录制记录吗？")) return;
    try {
      await deleteRecording(sessionId);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除录制失败");
    }
  };

  const handlePlaySession = (session: RecordingSession) => {
    setPlaybackError(false);
    setPlayingSession(session);
  };

  const handleClosePlayer = () => {
    setPlayingSession(null);
    setPlaybackError(false);
  };

  const isPlayableSession = (session: RecordingSession): boolean => {
    return session.status === "completed" && !!session.video_id;
  };

  const statusLabel = (status: string) => {
    const map: Record<string, string> = { recording: "录制中", completed: "已完成", failed: "失败", canceled: "已取消" };
    return map[status] ?? status;
  };

  const statusColor = (status: string) => {
    const map: Record<string, string> = { recording: "text-red-500 bg-red-50", completed: "text-green-600 bg-green-50", failed: "text-orange-500 bg-orange-50", canceled: "text-gray-400 bg-gray-50" };
    return map[status] ?? "text-gray-500 bg-gray-50";
  };

  const nonPlayableReason = (session: RecordingSession): string | null => {
    if (session.status === "recording") return "录制进行中";
    if (session.status === "canceled") return "已取消";
    if (session.status === "failed") return "录制失败";
    if (session.status === "completed" && !session.video_id) return "视频未注册";
    return null;
  };

  // 最近 N 条录制（精简历史）
  const recentSessions = useMemo(() => sessions.slice(0, 5), [sessions]);

  return (
    <PageFrame>
      {/* 注册摄像头 Modal */}
      <Modal isOpen={showRegisterModal} onClose={() => setShowRegisterModal(false)} title="注册新摄像头" size="md">
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <input
              className="field-input col-span-2"
              placeholder="摄像头 ID (例: baseline-cam)"
              value={newCamera.camera_id}
              onChange={(e) => setNewCamera((c) => ({ ...c, camera_id: e.target.value }))}
            />
            <select
              className="field-input"
              value={newCamera.protocol}
              onChange={(e) => setNewCamera((c) => ({ ...c, protocol: e.target.value as "rtsp" | "rtmp" | "http" }))}
            >
              <option value="rtsp">RTSP</option>
              <option value="rtmp">RTMP</option>
              <option value="http">HTTP</option>
            </select>
          </div>
          <input className="field-input" placeholder="摄像头名称" value={newCamera.name} onChange={(e) => setNewCamera((c) => ({ ...c, name: e.target.value }))} />
          <input className="field-input" placeholder="流地址 (rtsp://...)" value={newCamera.stream_url} onChange={(e) => setNewCamera((c) => ({ ...c, stream_url: e.target.value }))} />
          <div className="grid grid-cols-2 gap-3">
            <input className="field-input" placeholder="用户名 (可选)" value={newCamera.username ?? ""} onChange={(e) => setNewCamera((c) => ({ ...c, username: e.target.value || undefined }))} />
            <input className="field-input" type="password" placeholder="密码 (可选)" value={newCamera.password ?? ""} onChange={(e) => setNewCamera((c) => ({ ...c, password: e.target.value || undefined }))} />
          </div>
          <button className="green-button w-full py-2.5" disabled={loading} onClick={handleRegisterCamera} type="button">
            {loading ? "注册中..." : "注册摄像头"}
          </button>
        </div>
      </Modal>

      <div className="mb-8">
        <h2 className="text-2xl font-black tracking-tight">球场采集管理</h2>
        <p className="mt-1 text-sm text-slate-500">管理网络摄像头并控制录制会话</p>
      </div>

      {/* Field Session 选择器 */}
      <div className="mb-6 rounded-2xl border border-[#DDE9D6] bg-white p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="flex items-center gap-2 text-sm font-bold text-slate-600">
            <Radar size={16} />
            当前采集任务
          </h3>
          <button className="green-button px-3 py-1.5 text-xs" onClick={() => setShowCreateFsModal(true)} type="button">
            + 新建采集任务
          </button>
        </div>
        {fieldSessions.length === 0 ? (
          <p className="text-xs text-slate-400">暂无采集任务，创建 Field Session 可将多段录制关联到同一次球场采集</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button
              className={`px-4 py-2 rounded-full text-xs font-bold transition ${!selectedFieldSession ? "bg-[#17231D] text-white" : "bg-[#F1F7EC] text-slate-600 hover:bg-[#E8F2DC]"}`}
              onClick={handleSelectDirectRecording}
              type="button"
            >
              直接录制
            </button>
            {fieldSessions.slice(0, 8).map((fs) => (
              <button
                key={fs.id}
                className={`px-4 py-2 rounded-full text-xs font-bold transition ${
                  selectedFieldSession?.id === fs.id ? "bg-[#17231D] text-white" : "bg-[#F1F7EC] text-slate-600 hover:bg-[#E8F2DC]"
                }`}
                onClick={() => setSelectedFieldSession(fs)}
                type="button"
              >
                {fs.title || fs.id}
                <span className={`ml-1.5 inline-block size-1.5 rounded-full ${
                  fs.status === "live" ? "bg-[#22C55E]" : fs.status === "completed" ? "bg-[#2F80ED]" : fs.status === "archived" ? "bg-slate-400" : "bg-slate-300"
                }`} />
              </button>
            ))}
          </div>
        )}
        {selectedFieldSession && (
          <div className="mt-3 flex items-center gap-4 text-xs text-slate-500 border-t border-[#DDE9D6] pt-3">
            <span>状态: <strong className="text-[#17231D]">{selectedFieldSession.status === "live" ? "进行中" : selectedFieldSession.status === "completed" ? "已完成" : selectedFieldSession.status === "archived" ? "已归档" : "计划中"}</strong></span>
            <span>{selectedFieldSession.venue} · {selectedFieldSession.court_name}</span>
            <span>{selectedFieldSession.capture_mode === "practice" ? "练习" : selectedFieldSession.capture_mode === "match" ? "比赛" : "工程"} · {selectedFieldSession.match_format === "doubles" ? "双打" : "单打"}</span>
            {selectedFieldSession.status !== "archived" && (
              <div className="ml-auto flex items-center gap-2">
                {selectedFieldSession.status === "planned" && (
                  <button className="quiet-button px-2.5 py-1 text-xs" disabled={loading} onClick={() => handleFieldSessionAction("start")} type="button">开始任务</button>
                )}
                {(selectedFieldSession.status === "planned" || selectedFieldSession.status === "live") && (
                  <button className="quiet-button px-2.5 py-1 text-xs" disabled={loading} onClick={() => handleFieldSessionAction("complete")} type="button">完成任务</button>
                )}
                {selectedFieldSession.status === "completed" && (
                  <button className="quiet-button px-2.5 py-1 text-xs" disabled={loading} onClick={() => handleFieldSessionAction("archive")} type="button">归档任务</button>
                )}
                {selectedFieldSession.status !== "live" && (
                  <button className="quiet-button px-2.5 py-1 text-xs text-[#C92A2A]" disabled={loading} onClick={handleDeleteFieldSession} type="button">删除任务</button>
                )}
                <button className="text-[#C92A2A] hover:underline" onClick={handleSelectDirectRecording} type="button">取消选择</button>
              </div>
            )}
          </div>
        )}

        {/* 时间线事件部分（仅在选中 Field Session 时显示） */}
        {selectedFieldSession && selectedFieldSession.status !== "archived" && (
          <div className="mt-3 border-t border-[#DDE9D6] pt-3">
            {/* 快捷打点面板（仅在录制中显示） */}
            {activeSession && activeSession.field_session_id === selectedFieldSession.id && (
              <div className="mb-3">
                <p className="text-xs font-bold text-slate-500 mb-2 flex items-center gap-1">
                  <PlusCircle size={12} /> 快速打点
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {quickEventsForMode(selectedFieldSession.capture_mode || "practice").map((def, i) => (
                    <button
                      key={i}
                      className="quiet-button px-2 py-1 text-[11px]"
                      onClick={() => handleCreateQuickEvent(def)}
                      type="button"
                    >
                      {def.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 时间线事件列表 */}
            <div>
              <p className="text-xs font-bold text-slate-500 mb-2 flex items-center gap-1">
                <Clock size={12} /> 时间线事件 ({timelineEvents.length})
              </p>
              {timelineEvents.length === 0 ? (
                <p className="text-[11px] text-slate-400">
                  {activeSession ? "录制中可点击上方快捷按钮打点" : "暂无时间线事件，开始录制后可打点记录"}
                </p>
              ) : (
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {timelineEvents.map((ev) => (
                    <div
                      key={ev.id}
                      className="flex items-center justify-between rounded-lg border border-[#DDE9D6] bg-[#F8FBF5] px-3 py-1.5"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-bold text-[#17231D] truncate">
                            {ev.label || ev.event_type}
                          </span>
                          <span className="text-[10px] text-slate-400">
                            {ev.timestamp_ms > 0 ? `${(ev.timestamp_ms / 1000).toFixed(1)}s` : "—"}
                          </span>
                          <span className={`rounded px-1 py-0.5 text-[9px] font-semibold ${
                            ev.source === "manual" ? "bg-slate-100 text-slate-500" :
                            ev.source === "algorithm" ? "bg-blue-50 text-blue-600" :
                            "bg-amber-50 text-amber-600"
                          }`}>
                            {ev.source === "manual" ? "人工" : ev.source === "algorithm" ? "算法" : "修正"}
                          </span>
                        </div>
                        {ev.note && (
                          <p className="text-[10px] text-slate-400 truncate mt-0.5">{ev.note}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1 ml-2 shrink-0">
                        <button
                          className="p-1 rounded hover:bg-[#E8F2DC] text-slate-400 hover:text-[#17231D]"
                          onClick={() => handleEditEvent(ev)}
                          type="button"
                          title="编辑"
                        >
                          <Edit3 size={12} />
                        </button>
                        <button
                          className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-[#C92A2A]"
                          onClick={() => handleDeleteEvent(ev.id)}
                          type="button"
                          title="删除"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 直接录制时不显示时间线事件（task 4.8） */}
        {!selectedFieldSession && null}
      </div>

      {/* 编辑时间线事件 Modal */}
      <Modal isOpen={showEventModal} onClose={() => { setShowEventModal(false); setEditingEvent(null); setEditPayloadText("{}"); }} title="编辑时间线事件" size="sm">
        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-slate-500 block mb-1">标签</label>
            <input
              className="field-input"
              value={editForm.label ?? editingEvent?.label ?? ""}
              onChange={(e) => setEditForm((f) => ({ ...f, label: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 block mb-1">备注</label>
            <textarea
              className="field-input"
              rows={2}
              value={editForm.note ?? editingEvent?.note ?? ""}
              onChange={(e) => setEditForm((f) => ({ ...f, note: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 block mb-1">时间戳 (毫秒)</label>
            <input
              className="field-input"
              type="number"
              value={editForm.timestamp_ms ?? editingEvent?.timestamp_ms ?? 0}
              onChange={(e) => setEditForm((f) => ({ ...f, timestamp_ms: Number(e.target.value) }))}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 block mb-1">Payload JSON</label>
            <textarea
              className="field-input font-mono text-xs"
              rows={5}
              value={editPayloadText}
              onChange={(e) => setEditPayloadText(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button className="green-button flex-1 py-2 text-sm" onClick={handleSaveEdit} type="button">保存</button>
            <button className="quiet-button flex-1 py-2 text-sm" onClick={() => { setShowEventModal(false); setEditingEvent(null); setEditPayloadText("{}"); }} type="button">取消</button>
          </div>
        </div>
      </Modal>

      {/* Create Field Session Modal */}
      <Modal isOpen={showCreateFsModal} onClose={() => setShowCreateFsModal(false)} title="新建采集任务" size="md">
        <div className="space-y-3">
          <input className="field-input" placeholder="任务名称 (例: 周三双打训练)" value={newFsForm.title ?? ""} onChange={(e) => setNewFsForm((f) => ({ ...f, title: e.target.value }))} />
          <div className="grid grid-cols-2 gap-3">
            <input className="field-input" placeholder="场馆" value={newFsForm.venue ?? ""} onChange={(e) => setNewFsForm((f) => ({ ...f, venue: e.target.value }))} />
            <input className="field-input" placeholder="球场" value={newFsForm.court_name ?? ""} onChange={(e) => setNewFsForm((f) => ({ ...f, court_name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <select className="field-input" value={newFsForm.capture_mode ?? "practice"} onChange={(e) => setNewFsForm((f) => ({ ...f, capture_mode: e.target.value }))}>
              <option value="practice">练习</option>
              <option value="match">比赛</option>
              <option value="engineering">工程调试</option>
            </select>
            <select className="field-input" value={newFsForm.match_format ?? "doubles"} onChange={(e) => setNewFsForm((f) => ({ ...f, match_format: e.target.value }))}>
              <option value="doubles">双打</option>
              <option value="singles">单打</option>
            </select>
            <select className="field-input" value={newFsForm.camera_setup ?? "single"} onChange={(e) => setNewFsForm((f) => ({ ...f, camera_setup: e.target.value }))}>
              <option value="single">单摄</option>
              <option value="dual">双摄</option>
              <option value="debug_single">调试单摄</option>
            </select>
          </div>
          <textarea className="field-input" placeholder="备注 (可选)" rows={2} value={newFsForm.notes ?? ""} onChange={(e) => setNewFsForm((f) => ({ ...f, notes: e.target.value }))} />
          <button className="green-button w-full py-2.5" disabled={loading} onClick={handleCreateFieldSession} type="button">
            {loading ? "创建中..." : "创建采集任务"}
          </button>
        </div>
      </Modal>

      {error && (
        <div className="mb-6 rounded-xl border border-[#FF4D4F]/25 bg-[#FF4D4F]/8 px-5 py-4 text-sm text-[#C92A2A]">
          {error}
          <button className="ml-3 underline" onClick={() => setError(null)} type="button">关闭</button>
        </div>
      )}

      {/* 视频播放器弹窗 */}
      {playingSession && (
        <div className="mb-6 rounded-2xl border border-[#DDE9D6] bg-white p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold truncate pr-4">录播回放 · {playingSession.session_id}</h3>
            <button className="quiet-button p-2" onClick={handleClosePlayer} type="button" title="关闭播放器"><X size={18} /></button>
          </div>
          <p className="mb-3 text-xs text-slate-400">{playingSession.camera_id} · {playingSession.court_name}{playingSession.duration_sec ? ` · ${playingSession.duration_sec.toFixed(0)}秒` : ""}</p>
          {playbackError ? (
            <div className="rounded-xl border border-[#FF4D4F]/25 bg-[#FF4D4F]/8 p-8 text-center">
              <p className="text-sm font-semibold text-[#C92A2A] mb-2">视频播放失败</p>
              <p className="text-xs text-slate-500">视频文件可能已被删除或浏览器不支持此格式。</p>
              <button className="mt-3 quiet-button px-4 py-1.5 text-xs" onClick={() => { setPlaybackError(false); }} type="button">重试</button>
            </div>
          ) : (
            <video key={playingSession.session_id} className="w-full rounded-xl bg-black" controls autoPlay src={getVideoStreamUrl(playingSession.video_id)} onError={() => setPlaybackError(true)} />
          )}
        </div>
      )}

      {activeSession && (
        <div className="mb-6 rounded-2xl border border-[#22C55E]/30 bg-[#22C55E]/8 p-5">
          <div className="flex items-center gap-3">
            <span className="flex size-3 animate-pulse rounded-full bg-[#22C55E]" />
            <span className="font-bold text-[#168A34]">正在录制</span>
            <span className="text-sm text-slate-500">{activeSession.camera_id} · {activeSession.court_name}</span>
            <span className="text-sm text-slate-400">{activeSession.started_at}</span>
          </div>
          <p className="mt-2 text-xs text-slate-400">录制期间预览已暂停，停止录制后自动恢复</p>
          <div className="mt-3 flex gap-3">
            <button className="green-button px-6 py-2" disabled={loading} onClick={() => handleStopRecording(activeSession.session_id)} type="button">停止录制</button>
            <button className="quiet-button px-6 py-2" disabled={loading} onClick={() => handleCancelRecording(activeSession.session_id)} type="button">取消录制</button>
          </div>
        </div>
      )}

      {/* 实时预览 — 居中全宽 */}
      <div className="mb-6 rounded-2xl border border-[#DDE9D6] bg-white p-6">
        <h3 className="mb-4 flex items-center gap-2 text-lg font-bold">
          <span className="grid size-8 place-items-center rounded-lg bg-[#19B84C]/12 text-[#168A34]"><Play size={16} /></span>
          实时预览
        </h3>
        {previewStatus === "idle" && (
          <div className="rounded-xl border border-dashed border-[#DDE9D6] bg-[#F8FBF5] p-16 text-center">
            <Camera size={36} className="mx-auto mb-3 text-slate-300" />
            <p className="text-sm text-slate-400">选择摄像头后显示实时画面</p>
          </div>
        )}
        {previewStatus === "loading" && (
          <div className="rounded-xl border border-dashed border-[#DDE9D6] bg-[#F8FBF5] p-16 text-center">
            <RefreshCw size={36} className="mx-auto mb-3 animate-spin text-slate-300" />
            <p className="text-sm text-slate-400">正在加载摄像头画面...</p>
          </div>
        )}
        {(previewStatus === "displaying" || previewStatus === "loading") && previewUrl && (
          <img
            key={previewKey}
            src={previewUrl}
            alt="摄像头实时预览"
            className="w-full rounded-xl bg-black object-contain max-h-[480px]"
            onLoad={() => setPreviewStatus("displaying")}
            onError={() => setPreviewStatus("failed")}
          />
        )}
        {previewStatus === "failed" && (
          <div className="rounded-xl border border-[#FF4D4F]/25 bg-[#FF4D4F]/8 p-10 text-center">
            <p className="text-sm font-semibold text-[#C92A2A] mb-2">预览加载失败</p>
            <p className="text-xs text-slate-500 mb-3">摄像头流可能不可达、鉴权失败或无法解码。请检查摄像头地址后重试。</p>
            <button className="quiet-button px-4 py-1.5 text-xs" onClick={() => { setPreviewStatus("loading"); setPreviewKey((k) => k + 1); }} type="button">重试预览</button>
          </div>
        )}
      </div>

      {/* 下半部分：摄像头列表 + 录制控制 并排 */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* 左侧：摄像头管理 */}
        <section>
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="flex items-center gap-2 text-lg font-bold">
                <span className="grid size-8 place-items-center rounded-lg bg-[#19B84C]/12 text-[#168A34]"><Camera size={16} /></span>
                摄像头列表
              </h3>
              <button className="green-button px-3 py-1.5 text-xs" onClick={() => setShowRegisterModal(true)} type="button">
                + 注册摄像头
              </button>
            </div>
            {cameras.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-400">暂无注册摄像头，点击上方按钮注册</p>
            ) : (
              <div className="space-y-3 max-h-[420px] overflow-y-auto">
                {cameras.map((cam) => {
                  const probe = probeResults[cam.camera_id];
                  return (
                    <div key={cam.camera_id} className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-bold text-sm text-[#17231D]">{cam.name}</span>
                          <span className="ml-2 text-xs text-slate-400">({cam.camera_id})</span>
                        </div>
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${probe?.online ? "text-[#168A34] bg-[#22C55E]/12" : "text-slate-400 bg-slate-100"}`}>
                          <span className={`size-1.5 rounded-full ${probe?.online ? "bg-[#22C55E]" : "bg-slate-300"}`} />
                          {probe?.online ? "在线" : probe ? "离线" : "未检测"}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-slate-400 truncate">{cam.stream_url}</p>
                      {probe?.online && probe.resolution && <p className="text-xs text-slate-400">分辨率: {probe.resolution} · 延迟: {probe.latency_ms}ms</p>}
                      {probe && !probe.online && probe.error_message && <p className="text-xs text-[#C92A2A]">{probe.error_message}</p>}
                      <div className="mt-2 flex gap-2">
                        <button className="quiet-button px-2.5 py-1 text-xs" onClick={() => handleProbe(cam.camera_id)} type="button">探测</button>
                        <button className="quiet-button px-2.5 py-1 text-xs" disabled={!!activeSession} onClick={() => setRecordingForm((f) => ({ ...f, camera_id: cam.camera_id }))} type="button">录制</button>
                        <button className="quiet-button px-2.5 py-1 text-xs text-[#C92A2A]" onClick={() => handleRemoveCamera(cam.camera_id)} disabled={!!activeSession} type="button">删除</button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {/* 右侧：录制控制 + 最近录制 */}
        <section className="space-y-6">
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-6">
            <h3 className="mb-4 text-lg font-bold">开始录制</h3>
            <div className="space-y-3">
              <select className="field-input" value={recordingForm.camera_id} onChange={(e) => setRecordingForm((f) => ({ ...f, camera_id: e.target.value }))}>
                <option value="">选择摄像头...</option>
                {cameras.map((cam) => (<option key={cam.camera_id} value={cam.camera_id}>{cam.name} ({cam.camera_id})</option>))}
              </select>
              <input className="field-input" placeholder="球场名称" value={recordingForm.court_name ?? ""} onChange={(e) => setRecordingForm((f) => ({ ...f, court_name: e.target.value }))} />
              <div className="grid grid-cols-2 gap-3">
                <select className="field-input" value={recordingForm.match_format ?? "doubles"} onChange={(e) => setRecordingForm((f) => ({ ...f, match_format: e.target.value as "singles" | "doubles" }))}>
                  <option value="doubles">双打</option>
                  <option value="singles">单打</option>
                </select>
                <select className="field-input" value={recordingForm.camera_angle ?? "baseline_high"} onChange={(e) => setRecordingForm((f) => ({ ...f, camera_angle: e.target.value }))}>
                  <option value="baseline_high">底线高角度</option>
                  <option value="sideline">侧边</option>
                  <option value="overhead">俯视</option>
                </select>
                <select className="field-input" value={recordingForm.fps ?? 60} onChange={(e) => setRecordingForm((f) => ({ ...f, fps: Number(e.target.value) }))}>
                  {[24, 25, 30, 50, 60].map((fps) => (
                    <option key={fps} value={fps}>{fps} fps</option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" className="size-4 accent-[#22C55E]" checked={recordingForm.auto_analyze_after_stop ?? true} onChange={(e) => setRecordingForm((f) => ({ ...f, auto_analyze_after_stop: e.target.checked }))} />
                停止后自动创建分析任务
              </label>
              <button className="green-button w-full py-2.5" disabled={loading || !!activeSession} onClick={handleStartRecording} type="button">
                {activeSession ? "已有录制进行中" : loading ? "开始中..." : "开始录制"}
              </button>
            </div>
          </div>

          {/* 最近录制历史（精简） */}
          <div className="rounded-2xl border border-[#DDE9D6] bg-white p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">最近录制</h3>
              {sessions.length > 0 && (
                <button className="text-xs font-semibold text-[#2F80ED] hover:underline" onClick={() => onNavigate("/analysis/tasks")} type="button">
                  查看全部录制 →
                </button>
              )}
            </div>
            {recentSessions.length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-400">暂无录制记录</p>
            ) : (
              <div className="space-y-2.5">
                {recentSessions.map((session) => (
                  <div key={session.session_id} className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-[#17231D] truncate max-w-[140px]">{session.session_id}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusColor(session.status)}`}>{statusLabel(session.status)}</span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-400">{session.camera_id} · {session.court_name}{session.duration_sec ? ` · ${session.duration_sec.toFixed(0)}秒` : ""}</p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {isPlayableSession(session) && (
                        <button className="text-[11px] font-semibold text-[#2F80ED] hover:underline flex items-center gap-1" onClick={() => handlePlaySession(session)} type="button"><Play size={10} /> 播放</button>
                      )}
                      {session.auto_analysis_job_id && (
                        <button className="text-[11px] font-semibold text-[#168A34] hover:underline" onClick={() => onNavigate(`/analysis/${session.auto_analysis_job_id}`)} type="button">分析结果 →</button>
                      )}
                      {!isPlayableSession(session) && nonPlayableReason(session) && <span className="text-[11px] text-slate-400">{nonPlayableReason(session)}</span>}
                      {session.status !== "recording" && (
                        <button className="text-[11px] font-semibold text-[#C92A2A] hover:underline ml-auto" onClick={() => handleDeleteSession(session.session_id)} type="button">
                          <Trash2 size={10} className="inline" /> 删除
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </PageFrame>
  );
}

/**
 * 训练建议页组件
 */
