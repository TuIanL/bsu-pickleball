import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Camera, List, Loader2, Play } from "lucide-react";
import type { AppPath, RecordingSession, SyncRecordingSession, FieldSession, SessionTimelineEvent } from "../types/report";
import type { CaptureSegmentSummary } from "../types/report";
import {
  getRecording, getSyncRecording, getFieldSession,
  listTimelineEvents, listSegments, getVideoStreamUrl,
} from "../services/analysisClient";
import { MiniTimeline } from "../components/MiniTimeline";
import { VidatWorkbenchPanel } from "../components/capture/VidatWorkbenchPanel";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

type RecordingType = "single" | "dual";
type PageState =
  | { status: "loading" }
  | { status: "not_found" }
  | { status: "loaded"; type: RecordingType; recording: RecordingSession | null; syncRecording: SyncRecordingSession | null };

type TimelineLoadState = "idle" | "loaded" | "unavailable";

const EVENT_TYPE_LABELS: Record<string, string> = {
  session_note: "备注",
  non_play_start: "非比赛开始",
  non_play_end: "非比赛结束",
  game_start: "局开始",
  game_end: "局结束",
  score_update: "得分",
  side_change: "换边",
  rally_start: "分开始",
  rally_end: "分结束",
  custom_marker: "自定义标记",
  timeout_start: "暂停开始",
  timeout_end: "暂停结束",
  drill_start: "训练开始",
  drill_end: "训练结束",
  set_start: "盘开始",
  set_end: "盘结束",
  score_correction: "比分修正",
  add_note: "标注",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  set_start: "text-[#F97316] bg-[#FFF7ED] border-[#F97316]",
  set_end: "text-[#F97316] bg-[#FFF7ED] border-[#F97316]",
  game_start: "text-[#3B82F6] bg-[#EFF6FF] border-[#3B82F6]",
  game_end: "text-[#3B82F6] bg-[#EFF6FF] border-[#3B82F6]",
  rally_start: "text-[#22C55E] bg-[#F0FDF4] border-[#22C55E]",
  rally_end: "text-slate-500 bg-slate-50 border-slate-300",
  side_change: "text-[#A855F7] bg-[#FAF5FF] border-[#A855F7]",
  timeout_start: "text-[#F97316] bg-[#FFF7ED] border-[#F97316]",
  score_update: "text-[#22C55E] bg-[#F0FDF4] border-[#22C55E]",
  session_note: "text-slate-500 bg-slate-50 border-slate-300",
  add_note: "text-slate-500 bg-slate-50 border-slate-300",
  custom_marker: "text-slate-500 bg-slate-50 border-slate-300",
};

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function recordingEndMs(session: RecordingSession | SyncRecordingSession): number | null {
  const stoppedAt = session.stopped_at ? Date.parse(session.stopped_at) : NaN;
  if (!Number.isNaN(stoppedAt)) return stoppedAt;

  const startedAt = Date.parse(session.started_at ?? "");
  if (!Number.isNaN(startedAt) && session.duration_sec != null) {
    return startedAt + session.duration_sec * 1000;
  }
  return null;
}

/**
 * Older recordings stored manual events only under their Field Session. Keep
 * those events when their creation time falls inside this recording, while
 * never accepting an event explicitly assigned to another recording or Take.
 */
export function eventsForRecording(
  events: SessionTimelineEvent[],
  session: RecordingSession | SyncRecordingSession,
): SessionTimelineEvent[] {
  const takeId = session.capture_take_id;
  const startedAt = Date.parse(session.started_at ?? "");
  const endedAt = recordingEndMs(session);

  return events.filter((event) => {
    if (takeId && event.capture_take_id === takeId) return true;
    if (event.recording_session_id === session.session_id) return true;

    if (event.capture_take_id || event.recording_session_id || Number.isNaN(startedAt) || endedAt === null) {
      return false;
    }

    const eventTime = Date.parse(event.occurred_at || event.created_at);
    return !Number.isNaN(eventTime) && eventTime >= startedAt && eventTime <= endedAt;
  });
}

export function RecordingWorkspacePage({ sessionId, onNavigate }: { sessionId: string; onNavigate: NavigateFn }) {
  const [pageState, setPageState] = useState<PageState>({ status: "loading" });
  const [fieldSession, setFieldSession] = useState<FieldSession | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);
  const [timelineLoadState, setTimelineLoadState] = useState<TimelineLoadState>("idle");
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const [playbackErrors, setPlaybackErrors] = useState<Record<string, boolean>>({});
  const [videoTimeMs, setVideoTimeMs] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const video1Ref = useRef<HTMLVideoElement | null>(null);
  const video2Ref = useRef<HTMLVideoElement | null>(null);
  const pendingSeekRef = useRef<{ source: string; target: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTimelineEvents([]);
    setSegments([]);
    setTimelineLoadState("idle");

    (async () => {
      const [singleResult, dualResult] = await Promise.all([
        getRecording(sessionId).catch(() => null),
        getSyncRecording(sessionId).catch(() => null),
      ]);

      if (cancelled) return;

      if (!singleResult && !dualResult) {
        setPageState({ status: "not_found" });
        return;
      }

      const type: RecordingType = singleResult ? "single" : "dual";
      setPageState({ status: "loaded", type, recording: singleResult, syncRecording: dualResult });

      const session = singleResult ?? dualResult!;
      const fsId = session.field_session_id;

      // Load field session
      if (fsId) {
        try {
          const fs = await getFieldSession(fsId);
          if (!cancelled) setFieldSession(fs);
        } catch { /* ignore */ }
      }

      // Load timeline events
      if (fsId) {
        try {
          const events = await listTimelineEvents(fsId);
          if (!cancelled) {
            setTimelineEvents(eventsForRecording(events ?? [], session));
            setTimelineLoadState("loaded");
          }
        } catch {
          if (!cancelled) setTimelineLoadState("unavailable");
        }
      }

      // Load segments
      if (session.capture_take_id) {
        try {
          const segs = await listSegments(session.capture_take_id);
          if (!cancelled) setSegments(segs ?? []);
        } catch { /* ignore */ }
      }
    })();

    return () => { cancelled = true; };
  }, [sessionId]);

  const elapsedMs = useMemo(() => {
    if (pageState.status !== "loaded") return 0;
    const s = pageState.type === "single"
      ? pageState.recording!
      : pageState.syncRecording!;
    return (s.duration_sec ?? 0) * 1000;
  }, [pageState]);

  const sortedEvents = useMemo(() => {
    return [...timelineEvents].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
  }, [timelineEvents]);

  const handlePlaybackError = useCallback((key: string) => {
    setPlaybackErrors(prev => ({ ...prev, [key]: true }));
  }, []);

  const handleTimeUpdate = useCallback(() => {
    const master = video1Ref.current;
    if (!master) return;
    setVideoTimeMs(Math.floor(master.currentTime * 1000));
  }, []);

  const getOtherVideo = (source: string) =>
    source === "cam_1" ? video2Ref.current : video1Ref.current;

  const handleCamPlay = useCallback((source: string) => {
    setIsPlaying(true);
    const sourceVideo = source === "cam_1" ? video1Ref.current : video2Ref.current;
    const otherVideo = getOtherVideo(source);
    if (!sourceVideo || !otherVideo) return;

    // 原生 controls 已经启动了 sourceVideo；这里只把另一路对齐并启动，
    // 不要再次调用 sourceVideo.play()，避免浏览器把一次点击变成重复播放命令。
    if (Math.abs(sourceVideo.currentTime - otherVideo.currentTime) > 0.03) {
      pendingSeekRef.current = { source: source === "cam_1" ? "cam_2" : "cam_1", target: sourceVideo.currentTime };
      otherVideo.currentTime = sourceVideo.currentTime;
    }
    if (otherVideo.paused) void otherVideo.play().catch(() => {});
  }, []);

  const handleCamPause = useCallback((source: string) => {
    setIsPlaying(false);
    const otherVideo = getOtherVideo(source);
    if (otherVideo && !otherVideo.paused) otherVideo.pause();
  }, []);

  const handleCamSeeked = useCallback((source: string) => {
    const srcEl = source === "cam_1" ? video1Ref.current : video2Ref.current;
    const otherEl = getOtherVideo(source);
    if (!srcEl) return;
    setVideoTimeMs(Math.floor(srcEl.currentTime * 1000));

    // 忽略由另一条视频的校正动作触发的 seeked，避免 A -> B -> A 反复回写。
    if (pendingSeekRef.current?.source === source) {
      pendingSeekRef.current = null;
      return;
    }

    if (otherEl && Math.abs(srcEl.currentTime - otherEl.currentTime) > 0.03) {
      pendingSeekRef.current = { source: source === "cam_1" ? "cam_2" : "cam_1", target: srcEl.currentTime };
      otherEl.currentTime = srcEl.currentTime;
    }
  }, []);

  const refreshDerivedData = useCallback(async () => {
    if (pageState.status !== "loaded") return;
    const current = pageState.recording ?? pageState.syncRecording;
    if (!current) return;
    const [events, nextSegments] = await Promise.all([
      current.field_session_id ? listTimelineEvents(current.field_session_id) : Promise.resolve([]),
      current.capture_take_id ? listSegments(current.capture_take_id) : Promise.resolve([]),
    ]);
    setTimelineEvents(eventsForRecording(events ?? [], current));
    setSegments(nextSegments ?? []);
  }, [pageState]);

  // ── Loading ──
  if (pageState.status === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[60vh] gap-3">
        <Loader2 size={20} className="animate-spin text-slate-400" />
        <p className="text-slate-400">加载录制数据…</p>
      </div>
    );
  }

  // ── Not Found ──
  if (pageState.status === "not_found") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-slate-500">录制未找到</p>
        <button className="quiet-button px-4 py-2" onClick={() => onNavigate("/tasks")} type="button">返回任务列表</button>
      </div>
    );
  }

  // ── Loaded ──
  const { type, recording, syncRecording } = pageState;
  const session = recording ?? syncRecording!;
  const isDual = type === "dual";

  const cam1Name = isDual ? syncRecording!.camera_slots?.cam_1?.camera_id ?? "—" : recording?.camera_id ?? "—";
  const cam2Name = isDual ? syncRecording!.camera_slots?.cam_2?.camera_id ?? "—" : null;
  const title = fieldSession?.title || session.court_name || "录制回放";
  const subtitle = [
    fieldSession?.court_name,
    isDual ? `A: ${cam1Name} / B: ${cam2Name}` : cam1Name,
    session.duration_sec ? `${Math.floor(session.duration_sec / 60)}分${Math.floor(session.duration_sec % 60)}秒` : null,
    `${sortedEvents.length} 个事件`,
  ].filter(Boolean).join(" · ");

  const cam1VideoId = isDual
    ? (syncRecording!.registered_video_ids?.cam_1 ?? syncRecording!.default_analysis_video_id)
    : recording?.video_id;
  const cam2VideoId = isDual ? syncRecording!.registered_video_ids?.cam_2 : undefined;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* 头部 */}
      <div className="flex items-center gap-4">
        <button className="quiet-button p-2" onClick={() => onNavigate("/tasks")} type="button" title="返回">
          <ArrowLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-black text-[#14241B] truncate">{title}</h1>
          <p className="text-sm text-slate-500 truncate">{subtitle}</p>
        </div>
      </div>

      {session.capture_take_id && (
        <VidatWorkbenchPanel captureTakeId={session.capture_take_id} onImported={refreshDerivedData} />
      )}

      {/* 视频区 */}
      <div className={`grid gap-4 ${isDual ? "lg:grid-cols-2" : "grid-cols-1"}`}>
        <div className="rounded-2xl border border-[#DDE9D6] bg-black aspect-video overflow-hidden relative">
          {cam1VideoId && !playbackErrors.cam_1 ? (
              <video
                ref={video1Ref}
                key={`cam1-${sessionId}`}
                className="w-full h-full object-contain"
                controls
                preload="auto"
                playsInline
                src={getVideoStreamUrl(cam1VideoId)}
                onError={() => handlePlaybackError("cam_1")}
                onTimeUpdate={handleTimeUpdate}
                onPlay={() => handleCamPlay("cam_1")}
                onPause={() => handleCamPause("cam_1")}
                onSeeked={() => handleCamSeeked("cam_1")}
              />
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-white/50 text-sm">
                {playbackErrors.cam_1 ? "视频加载失败" : isDual ? "底线机位 A 视频未注册" : "视频未注册"}
              </p>
            </div>
          )}
          <span className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-0.5 rounded">
            {isDual ? "机位 A" : "单摄"}
          </span>
        </div>
        {isDual && (
          <div className="rounded-2xl border border-[#DDE9D6] bg-black aspect-video overflow-hidden relative">
            {cam2VideoId && !playbackErrors.cam_2 ? (
              <video
                ref={video2Ref}
                key={`cam2-${sessionId}`}
                className="w-full h-full object-contain"
                controls
                preload="auto"
                playsInline
                src={getVideoStreamUrl(cam2VideoId)}
                onError={() => handlePlaybackError("cam_2")}
                onPlay={() => handleCamPlay("cam_2")}
                onPause={() => handleCamPause("cam_2")}
                onSeeked={() => handleCamSeeked("cam_2")}
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <p className="text-white/50 text-sm">
                  {playbackErrors.cam_2 ? "视频加载失败" : "底线机位 B 视频未注册"}
                </p>
              </div>
            )}
            <span className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-0.5 rounded">
              机位 B
            </span>
          </div>
        )}
      </div>

      {/* MiniTimeline — 有事件或 segment 才显示 */}
      {(timelineEvents.length > 0 || segments.length > 0) && (
        <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
          <h3 className="text-sm font-black text-[#14241B] mb-3">事件时间线</h3>
          <MiniTimeline
            segments={segments}
            events={timelineEvents}
            liveState={null}
            totalDurationMs={elapsedMs}
            elapsedMs={videoTimeMs}
            staticMode
            playing={isPlaying}
          />
        </div>
      )}

      {timelineLoadState === "unavailable" && (
        <p className="text-sm text-amber-700">
          该录制的历史时间线数据不可用，未显示时间条。
        </p>
      )}

      {/* 事件列表 — 有事件才显示 */}
      {sortedEvents.length > 0 && (
        <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
          <h3 className="text-sm font-black text-[#14241B] mb-3">
            关键事件
            <span className="ml-2 text-xs font-normal text-slate-400">{sortedEvents.length} 条</span>
          </h3>
          <div className="max-h-96 overflow-y-auto space-y-1">
            {sortedEvents.map((event) => {
              const colorClass = EVENT_TYPE_COLORS[event.event_type] ?? "text-slate-500 bg-slate-50 border-slate-300";
              const label = event.label || EVENT_TYPE_LABELS[event.event_type] || event.event_type;
              return (
                <div key={event.id} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-slate-50 transition">
                  <span className="tabular-nums text-slate-400 w-12 shrink-0">{formatElapsed(event.timestamp_ms)}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${colorClass}`}>{label}</span>
                  {event.note && <span className="text-slate-500 truncate min-w-0">{event.note}</span>}
                  {event.payload_json?.highlight === true && <span className="text-[#F59E0B] text-xs shrink-0">★</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
