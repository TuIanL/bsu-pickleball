import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera, CheckCircle2, Clock, MapPin, Play, PlusCircle,
  RefreshCw, Square, Trash2, Upload, Users, Wifi, WifiOff, X,
} from "lucide-react";
import type { AppPath, FieldSession, CameraInfo, ProbeResult, RecordingSession, SyncRecordingSession, SessionTimelineEvent, CaptureStopResult } from "../types/report";
import {
  getFieldSession, startFieldSession, completeFieldSession,
  listCameras, createCamera, deleteCamera, probeCamera,
  getCameraPreviewUrl, cancelRecording, cancelSyncRecording,
} from "../services/analysisClient";
import { useCaptureRuntime } from "../hooks/useCaptureRuntime";
import { useCameraSetup } from "../hooks/useCameraSetup";
import { useCapturePreflight } from "../hooks/useCapturePreflight";
import { useLiveCoding } from "../hooks/useLiveCoding";

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

type CaptureConsolePageProps = {
  sessionId: string;
  onNavigate: NavigateFn;
};

export default function CaptureConsolePage({ sessionId, onNavigate }: CaptureConsolePageProps) {
  const [fieldSession, setFieldSession] = useState<FieldSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [analysisIntent, setAnalysisIntent] = useState<string>("ask_after_recording");
  const [recordingFps, setRecordingFps] = useState<number>(60);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const [drawerTab, setDrawerTab] = useState<"list" | "register">("list");
  const [newCameraForm, setNewCameraForm] = useState({ camera_id: "", name: "", stream_url: "", protocol: "rtsp" as const });

  const isDualMode = fieldSession?.camera_setup === "dual";
  const mode = isDualMode ? "dual" as const : "single" as const;

  // ── Hooks ──
  const runtime = useCaptureRuntime({ fieldSessionId: sessionId, onFieldSessionStarted: setFieldSession });
  const cameraSetup = useCameraSetup({ sessionId, mode });
  const preflight = useCapturePreflight({ mode, slots: isDualMode ? cameraSetup.selectedSlots : undefined });
  const liveCoding = useLiveCoding({
    fieldSessionId: sessionId,
    captureTakeId: runtime.captureTakeId,
    phase: runtime.phase,
    elapsedMs: runtime.elapsedMs,
  });

  // ── 页面协调 ──
  const handleStart = async () => {
    if (!cameraSetup.startIntent) return;
    await runtime.start({ ...cameraSetup.startIntent, fps: recordingFps, autoAnalyze: analysisIntent === "auto_analyze" });
  };

  const handleStop = async () => {
    liveCoding.freeze();
    const promise = runtime.stop();
    void liveCoding.flushWithDeadline(3000);
    await promise;
    setPreviewKey(k => k + 1);
  };

  const handleCancel = async () => { await runtime.cancel(); };
  const handleReset = () => runtime.reset();

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

  // ── 加载中 ──
  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><p className="text-slate-400">加载中…</p></div>;
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
      <div className="space-y-3">
        {(["cam_1", "cam_2"] as const).map(slot => (
          <div key={slot} className="space-y-1">
            <label className="text-xs font-bold text-slate-500">{slot === "cam_1" ? "底线机位 A" : "底线机位 B"}</label>
            <button
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-left"
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
          <div className="rounded-xl border border-slate-200 p-3 space-y-1 max-h-48 overflow-y-auto">
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
            className="w-full rounded-xl border border-[#3B82F6] text-[#3B82F6] px-3 py-2 text-sm font-bold hover:bg-[#EFF6FF] transition disabled:opacity-50"
            onClick={preflight.runTest}
            disabled={!cameraSetup.isReady || preflight.preflightState.status === "running" || runtime.isRecording}
            type="button"
          >
            {preflight.preflightState.status === "running" ? <RefreshCw size={14} className="inline animate-spin mr-1" /> : null}
            {preflight.preflightState.status === "running" ? "测试中…" : "短录测试"}
          </button>
        )}
        {preflight.preflightState.status === "passed" && (
          <p className="text-xs text-[#22C55E]">测试通过</p>
        )}
        {preflight.preflightState.status === "failed" && (
          <p className="text-xs text-[#FF4D4F]">测试失败: {preflight.preflightState.error}</p>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
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
            <div className={`w-3 h-3 rounded-full ${runtime.phase === "recording" ? "bg-[#FF4D4F] animate-pulse" : runtime.phase === "stopping" || runtime.phase === "recovering" ? "bg-[#E8A838]" : "bg-slate-300"}`} />
            <span className="text-sm font-bold text-[#14241B]">
              {runtime.phase === "idle" ? "就绪" :
               runtime.phase === "starting" ? "启动中…" :
               runtime.phase === "recording" ? `录制中 ${elapsedDisplay}` :
               runtime.phase === "stopping" ? "停止中…" :
               runtime.phase === "recovering" ? "恢复中…" :
               runtime.phase === "completed" || runtime.phase === "partial" ? `已完成 ${elapsedDisplay}` :
               runtime.phase === "failed" ? "失败" :
               runtime.phase === "canceled" ? "已取消" : "就绪"}
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
            {runtime.phase === "recovering" && (
              <button className="flex items-center gap-2 rounded-xl bg-[#3B82F6] px-5 py-2.5 text-white font-bold" onClick={() => runtime.recover()} type="button">
                <RefreshCw size={16} />重试恢复
              </button>
            )}
          </div>
        </div>
        {runtime.error && <p className="text-xs text-[#FF4D4F] mt-2">{runtime.error}</p>}
      </div>

      {/* 预览 + 设置 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className={`grid ${cameraSetup.previewTracks.length === 1 ? "grid-cols-1" : "grid-cols-2"} gap-4`}>
            {cameraSetup.previewTracks.length === 0 ? (
              <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 aspect-video flex items-center justify-center">
                <p className="text-slate-400 text-sm">选择摄像头后显示预览</p>
              </div>
            ) : cameraSetup.previewTracks.map(track => (
              <div key={track.slot} className="rounded-2xl border border-slate-200 bg-black aspect-video overflow-hidden relative">
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
        <div className="space-y-4">
          {renderCameraSelector()}
        </div>
      </div>

      {/* Live Coding */}
      {runtime.phase === "recording" && (
        <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
          <div className="flex flex-wrap gap-2">
            {liveCoding.quickEvents.map(event => {
              const colorMap: Record<string, string> = {
                game_start: "bg-[#EFF6FF] border-[#3B82F6] text-[#3B82F6]",
                game_end: "bg-slate-50 border-slate-300 text-slate-500",
                score_update: "bg-[#F0FDF4] border-[#22C55E] text-[#22C55E]",
                side_change: "bg-[#FAF5FF] border-[#A855F7] text-[#A855F7]",
                timeout_start: "bg-[#FFF7ED] border-[#F97316] text-[#F97316]",
                custom_marker: "bg-slate-50 border-slate-300 text-slate-500",
                session_note: "bg-[#EFF6FF] border-[#3B82F6] text-[#3B82F6]",
              };
              return (
                <button
                  key={event.type}
                  className={`rounded-xl border px-3 py-1.5 text-xs font-bold transition ${colorMap[event.type] ?? "bg-slate-50 border-slate-300 text-slate-500"}`}
                  onClick={() => liveCoding.addTimelineEvent(event)}
                  type="button"
                >
                  {event.label}
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
      {runtime.phase === "recording" && (
        <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
          <div className="flex gap-2">
            {liveCoding.timelineEvents.slice(-20).map(evt => (
              <div key={evt.id} className="text-xs bg-slate-100 px-2 py-1 rounded" title={evt.note}>
                {formatElapsed(evt.timestamp_ms)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 完成面板 */}
      {runtime.isStopped && runtime.result && (
        <div className="rounded-2xl border border-[#22C55E]/30 bg-[#22C55E]/8 p-6 space-y-3">
          <h3 className="text-lg font-black text-[#14241B]">
            {runtime.phase === "completed" ? "录制已完成" : runtime.phase === "partial" ? "录制部分完成" : "录制结束"}
          </h3>
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
                  <div className="text-sm">
                    <p className="font-bold">{c.name ?? c.camera_id}</p>
                    <p className="text-xs text-slate-500">{c.stream_url}</p>
                  </div>
                  <div className="flex gap-1">
                    <button className="p-1.5 rounded-lg hover:bg-slate-100" onClick={() => cameraSetup.runProbe(c.camera_id)} type="button"><Wifi size={14} /></button>
                  </div>
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
