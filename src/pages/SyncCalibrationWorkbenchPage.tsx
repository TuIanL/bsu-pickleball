import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Copy,
  Download,
  Link2,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  Video,
} from "lucide-react";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { PageFrame } from "../components/PageFrame";
import {
  getCaptureTake,
  getSyncAnchorDraft,
  getSyncAnchorStatus,
  getSyncRecording,
  getVideoStreamUrl,
  getVideoTiming,
  isAnalysisApiError,
  confirmSyncAnchors,
  getSyncAnchorExportUrl,
  saveSyncAnchorDraft,
  type VideoTimingResponse,
} from "../services/analysisClient";
import {
  buildAnchorExport,
  clampFrameIndex,
  evaluateAnchorCoverage,
  findNearestFrameIndex,
  formatPts,
  getTimingFrame,
  type CalibrationAnchor,
} from "../services/syncCalibration";
import type { CaptureTakeSummary, SyncRecordingSession } from "../types/report";
import type { SyncAnchorDraftResponse, SyncAnchorStatus } from "../types/syncAnchors";

type CameraSlot = "cam_1" | "cam_2";

interface SyncCalibrationWorkbenchPageProps {
  captureTakeId: string;
  onNavigate: NavigateFn;
  returnPath?: NavigatePath;
}

interface WorkbenchView {
  slot: CameraSlot;
  cameraId: string;
  videoId: string;
  videoSrc: string;
  timing: VideoTimingResponse;
  framePosition: number;
}

const SLOTS: CameraSlot[] = ["cam_1", "cam_2"];
const STORAGE_PREFIX = "pre-pickleball-sync-calibration-anchors:";

function storageKey(takeId: string): string {
  return `${STORAGE_PREFIX}${takeId}`;
}

function readStoredAnchors(takeId: string): CalibrationAnchor[] {
  try {
    const value = window.localStorage.getItem(storageKey(takeId));
    if (!value) return [];
    const parsed = JSON.parse(value) as unknown;
    return Array.isArray(parsed) ? (parsed as CalibrationAnchor[]) : [];
  } catch {
    return [];
  }
}

function formatFrameLabel(view: WorkbenchView): string {
  const frame = getTimingFrame(view.timing.frames, view.framePosition);
  return frame ? `#${frame.frame_index}` : "—";
}

function formatDuration(seconds: number | null | undefined): string {
  if (!Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Number(seconds));
  const minutes = Math.floor(total / 60);
  const remainder = total - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(3).padStart(6, "0")}`;
}

function errorMessage(error: unknown): string {
  if (isAnalysisApiError(error)) return error.backendDetail ?? error.message;
  return error instanceof Error ? error.message : "无法加载双摄 timing 数据。";
}

function validationMessages(error: unknown): string[] {
  if (!isAnalysisApiError(error) || !error.backendDetail) return [errorMessage(error)];
  try {
    const payload = JSON.parse(error.backendDetail) as { issues?: Array<{ code?: string; message?: string; field?: string | null }> };
    if (Array.isArray(payload.issues) && payload.issues.length > 0) {
      return payload.issues.map((issue) => [issue.code, issue.field, issue.message].filter(Boolean).join(" · "));
    }
  } catch {
    // The API error may be a plain text response from a legacy server.
  }
  return [error.backendDetail];
}

function WorkbenchStatus({
  label,
  value,
  good = false,
}: {
  label: string;
  value: string;
  good?: boolean;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-xl border border-[#E4E7EC] bg-white px-3 py-2">
      {good ? <CheckCircle2 className="shrink-0 text-[#168A34]" size={15} /> : <Clock3 className="shrink-0 text-slate-400" size={15} />}
      <span className="truncate text-[11px] font-bold uppercase tracking-[0.1em] text-slate-400">{label}</span>
      <strong className={good ? "ml-auto text-xs text-[#168A34]" : "ml-auto text-xs text-[#344054]"}>{value}</strong>
    </div>
  );
}

function CameraVideoCard({
  view,
  isPlaying,
  videoRef,
  onFrameInput,
  onStep,
  onTogglePlay,
  onTimeUpdate,
  onLoadedMetadata,
  onPlayingChange,
  onSelect,
  selected,
}: {
  view: WorkbenchView;
  isPlaying: boolean;
  videoRef: (element: HTMLVideoElement | null) => void;
  onFrameInput: (frameNumber: number) => void;
  onStep: (delta: number) => void;
  onTogglePlay: () => void;
  onTimeUpdate: (currentTime: number) => void;
  onLoadedMetadata: (video: HTMLVideoElement) => void;
  onPlayingChange: (playing: boolean) => void;
  onSelect: () => void;
  selected: boolean;
}) {
  const frame = getTimingFrame(view.timing.frames, view.framePosition);
  const frameNumber = frame?.frame_index ?? 0;
  const firstPts = view.timing.first_pts_seconds ?? 0;
  const lastPts = view.timing.last_pts_seconds ?? firstPts;
  const progress = lastPts > firstPts && frame ? ((frame.pts_seconds - firstPts) / (lastPts - firstPts)) * 100 : 0;

  return (
    <section className={`min-w-0 overflow-hidden rounded-2xl border bg-white shadow-[0_8px_24px_rgba(16,24,40,0.06)] ${selected ? "border-[#22C55E] ring-2 ring-[#22C55E]/15" : "border-[#E4E7EC]"}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EEF2F0] px-4 py-3">
        <button className="flex min-w-0 items-center gap-3 text-left" onClick={onSelect} type="button">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#EAF7EE] text-[#168A34]"><Video size={17} aria-hidden="true" /></span>
          <span className="min-w-0">
            <strong className="block truncate text-sm text-[#14241B]">Camera {view.cameraId}</strong>
            <span className="block truncate text-xs text-slate-400">{view.slot} · {view.videoId}</span>
          </span>
        </button>
        <span className="rounded-full bg-[#EAF7EE] px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-[#168A34]">source_pts</span>
      </div>

      <div className="bg-[#101828]">
        <video
          ref={videoRef}
          className="aspect-video w-full object-contain"
          muted
          playsInline
          preload="metadata"
          src={view.videoSrc}
          onEnded={() => { onPlayingChange(false); onTimeUpdate(lastPts); }}
          onLoadedMetadata={(event) => onLoadedMetadata(event.currentTarget)}
          onPause={() => onPlayingChange(false)}
          onPlay={() => onPlayingChange(true)}
          onTimeUpdate={(event) => onTimeUpdate(event.currentTarget.currentTime)}
        />
      </div>

      <div className="space-y-3 p-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">当前源帧</div>
            <div className="mt-1 text-2xl font-black tabular-nums text-[#14241B]">{formatFrameLabel(view)}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">source PTS</div>
            <div className="mt-1 font-mono text-sm font-bold tabular-nums text-[#168A34]">{formatPts(frame?.pts_seconds)}</div>
          </div>
        </div>

        <input
          aria-label={`Camera ${view.cameraId} 时间位置`}
          className="h-1.5 w-full cursor-pointer accent-[#19B84C]"
          max={Math.max(0, view.timing.frames.length - 1)}
          min={0}
          onChange={(event) => onFrameInput(Number(event.target.value))}
          type="range"
          value={view.framePosition}
        />

        <div className="flex items-center gap-2">
          <button aria-label="后退一帧" className="grid size-9 shrink-0 place-items-center rounded-xl border border-[#D0D5DD] text-[#344054] transition hover:border-[#22C55E] hover:text-[#168A34]" onClick={() => onStep(-1)} title="后退一帧" type="button"><ChevronLeft size={17} /></button>
          <button aria-label={isPlaying ? "暂停视频" : "播放视频"} className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#19B84C] text-white transition hover:bg-[#168A34]" onClick={onTogglePlay} title={isPlaying ? "暂停" : "播放"} type="button">{isPlaying ? <Pause size={16} /> : <Play size={16} />}</button>
          <button aria-label="前进一帧" className="grid size-9 shrink-0 place-items-center rounded-xl border border-[#D0D5DD] text-[#344054] transition hover:border-[#22C55E] hover:text-[#168A34]" onClick={() => onStep(1)} title="前进一帧" type="button"><ChevronRight size={17} /></button>
          <label className="ml-auto flex items-center gap-2 text-xs font-semibold text-slate-500">
            帧号
            <input
              aria-label={`Camera ${view.cameraId} 帧号`}
              className="w-24 rounded-lg border border-[#D0D5DD] px-2 py-1.5 text-right font-mono text-xs font-bold text-[#14241B] outline-none focus:border-[#22C55E]"
              max={view.timing.frames[view.timing.frames.length - 1]?.frame_index ?? 0}
              min={view.timing.frames[0]?.frame_index ?? 0}
              onChange={(event) => onFrameInput(Number(event.target.value))}
              type="number"
              value={frameNumber}
            />
          </label>
        </div>

        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <span>{formatDuration(frame?.pts_seconds)} / {formatDuration(lastPts)}</span>
          <span>{view.timing.frame_count.toLocaleString("zh-CN")} 帧 · {view.timing.fps?.toFixed(3) ?? "—"} fps</span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#19B84C] transition-[width]" style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} /></div>
      </div>
    </section>
  );
}

export function SyncCalibrationWorkbenchPage({ captureTakeId, onNavigate, returnPath }: SyncCalibrationWorkbenchPageProps) {
  const [take, setTake] = useState<CaptureTakeSummary | null>(null);
  const [session, setSession] = useState<SyncRecordingSession | null>(null);
  const [views, setViews] = useState<WorkbenchView[]>([]);
  const [anchors, setAnchors] = useState<CalibrationAnchor[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<CameraSlot>("cam_1");
  const [playingBySlot, setPlayingBySlot] = useState<Record<CameraSlot, boolean>>({ cam_1: false, cam_2: false });
  const [eventLabel, setEventLabel] = useState("");
  const [eventNote, setEventNote] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [syncStatus, setSyncStatus] = useState<SyncAnchorStatus | null>(null);
  const [draftRevision, setDraftRevision] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [validationIssues, setValidationIssues] = useState<string[]>([]);
  const [legacyImportAvailable, setLegacyImportAvailable] = useState(false);
  const videoRefs = useRef<Partial<Record<CameraSlot, HTMLVideoElement | null>>>({});
  const returnTo = returnPath ?? `/capture/takes/${captureTakeId}/analyze`;

  const applyDraftResponse = useCallback((response: SyncAnchorDraftResponse) => {
    setAnchors(response.draft.anchors.map((anchor) => ({
      id: anchor.id,
      label: anchor.label,
      note: anchor.note,
      frameByCamera: anchor.frame_by_camera ?? {},
      ptsByCamera: anchor.pts_by_camera ?? {},
      createdAt: anchor.created_at ?? new Date().toISOString(),
    })));
    setDraftRevision(response.revision);
    setSyncStatus(response.status);
    setLegacyImportAvailable(false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!captureTakeId) {
        setLoadError("URL 缺少 capture take id。");
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setLoadError(null);
      try {
        const takeData = await getCaptureTake(captureTakeId);
        const sessionData = await getSyncRecording(takeData.source_session_id);
        const loadedViews = await Promise.all(SLOTS.map(async (slot): Promise<WorkbenchView> => {
          const videoId = sessionData.registered_video_ids?.[slot];
          if (!videoId) throw new Error(`${slot} 没有 registered video_id。`);
          const timing = await getVideoTiming(videoId);
          if (timing.authority !== "source_pts") throw new Error(`${slot} 未达到 source_pts authority。`);
          const videoSrc = getVideoStreamUrl(videoId);
          if (!videoSrc) throw new Error(`${slot} 视频流地址不可用。`);
          return {
            slot,
            cameraId: sessionData.camera_slots?.[slot]?.camera_id ?? slot,
            videoId,
            videoSrc,
            timing,
            framePosition: 0,
          };
        }));
        if (cancelled) return;
        setTake(takeData);
        setSession(sessionData);
        setViews(loadedViews);
        const status = await getSyncAnchorStatus(captureTakeId);
        setSyncStatus(status);
        try {
          const draftResponse = await getSyncAnchorDraft(captureTakeId);
          applyDraftResponse(draftResponse);
        } catch (error) {
          if (isAnalysisApiError(error) && error.status === 404) {
            const legacy = readStoredAnchors(captureTakeId);
            setAnchors(legacy);
            setLegacyImportAvailable(legacy.length > 0);
            setDraftRevision(status.revision);
          } else {
            throw error;
          }
        }
        videoRefs.current = {};
      } catch (error) {
        if (!cancelled) setLoadError(errorMessage(error));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [applyDraftResponse, captureTakeId]);

  useEffect(() => {
    if (!captureTakeId || !anchors.length) return;
    try {
      window.localStorage.setItem(storageKey(captureTakeId), JSON.stringify(anchors));
    } catch {
      // Local storage remains a short-lived offline buffer only.
    }
  }, [anchors, captureTakeId]);

  const referenceView = views[0];
  const cameraIds = views.map((view) => view.cameraId);
  const coverage = useMemo(() => {
    if (!referenceView) return null;
    const validAnchors = anchors.filter((anchor) => (
      anchor
      && anchor.ptsByCamera
      && typeof anchor.ptsByCamera === "object"
    ));
    return evaluateAnchorCoverage(
      validAnchors,
      referenceView.cameraId,
      referenceView.timing.first_pts_seconds ?? 0,
      referenceView.timing.last_pts_seconds ?? 0,
    );
  }, [anchors, referenceView]);
  const allPlaying = views.length === 2 && views.every((view) => playingBySlot[view.slot]);
  const selectedView = views.find((view) => view.slot === selectedSlot);

  const seekToPosition = useCallback((slot: CameraSlot, requestedPosition: number) => {
    const view = views.find((item) => item.slot === slot);
    if (!view) return;
    const position = clampFrameIndex(requestedPosition, view.timing.frames);
    const frame = getTimingFrame(view.timing.frames, position);
    setViews((current) => current.map((item) => item.slot === slot ? { ...item, framePosition: position } : item));
    if (frame) {
      const video = videoRefs.current[slot];
      if (video) {
        try { video.currentTime = frame.pts_seconds; } catch { /* The browser will retry on loadedmetadata. */ }
      }
    }
  }, [views]);

  const seekToFrameNumber = useCallback((slot: CameraSlot, frameNumber: number) => {
    const view = views.find((item) => item.slot === slot);
    if (!view || !Number.isFinite(frameNumber)) return;
    const position = view.timing.frames.findIndex((frame) => frame.frame_index === Math.trunc(frameNumber));
    seekToPosition(slot, position >= 0 ? position : frameNumber);
  }, [seekToPosition, views]);

  const handleVideoTime = useCallback((slot: CameraSlot, currentTime: number) => {
    const view = views.find((item) => item.slot === slot);
    if (!view || !Number.isFinite(currentTime)) return;
    const position = findNearestFrameIndex(view.timing.frames, currentTime);
    setViews((current) => current.map((item) => item.slot === slot && item.framePosition !== position ? { ...item, framePosition: position } : item));
  }, [views]);

  const toggleViewPlayback = useCallback((slot: CameraSlot) => {
    const video = videoRefs.current[slot];
    if (!video) return;
    if (video.paused) {
      void video.play().catch(() => setNotice("浏览器阻止了播放，请先点击视频区域或播放按钮。"));
    } else {
      video.pause();
    }
    setPlayingBySlot((current) => ({ ...current, [slot]: !current[slot] }));
  }, []);

  const toggleAllPlayback = useCallback(() => {
    const shouldPlay = !allPlaying;
    views.forEach((view) => {
      const video = videoRefs.current[view.slot];
      if (!video) return;
      if (shouldPlay) void video.play().catch(() => setNotice("浏览器阻止了播放，请先点击任一播放按钮。"));
      else video.pause();
    });
    setPlayingBySlot({ cam_1: shouldPlay, cam_2: shouldPlay });
  }, [allPlaying, views]);

  const recordAnchor = () => {
    if (views.length !== 2 || views.some((view) => view.timing.authority !== "source_pts")) return;
    const frameByCamera: Record<string, number> = {};
    const ptsByCamera: Record<string, number> = {};
    views.forEach((view) => {
      const frame = getTimingFrame(view.timing.frames, view.framePosition);
      if (frame) {
        frameByCamera[view.cameraId] = frame.frame_index;
        ptsByCamera[view.cameraId] = frame.pts_seconds;
      }
    });
    if (Object.keys(ptsByCamera).length !== 2) return;
    const nextAnchor: CalibrationAnchor = {
      id: `anchor-${Date.now()}-${anchors.length + 1}`,
      label: eventLabel.trim() || `共同事件 ${anchors.length + 1}`,
      note: eventNote.trim(),
      frameByCamera,
      ptsByCamera,
      createdAt: new Date().toISOString(),
    };
    setAnchors((current) => [...current, nextAnchor]);
    setEventLabel("");
    setEventNote("");
    setNotice(`已记录 ${nextAnchor.label}`);
  };

  const deleteAnchor = (id: string) => setAnchors((current) => current.filter((anchor) => anchor.id !== id));

  const selectAnchor = (anchor: CalibrationAnchor) => {
    views.forEach((view) => {
      const frameNumber = anchor.frameByCamera[view.cameraId];
      if (Number.isFinite(frameNumber)) seekToFrameNumber(view.slot, frameNumber);
    });
    setNotice(`已定位到 ${anchor.label}`);
  };

  const exportAnchors = () => {
    if (views.length !== 2) return;
    const payload = buildAnchorExport(referenceView.cameraId, cameraIds, anchors);
    const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sync-anchors-${captureTakeId}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setNotice("anchors JSON 已下载");
  };

  const copyAnchors = async () => {
    if (views.length !== 2) return;
    const payload = buildAnchorExport(referenceView.cameraId, cameraIds, anchors);
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setNotice("anchors JSON 已复制");
    } catch {
      setNotice("当前浏览器不允许自动复制，请使用下载按钮。");
    }
  };

  const serverDraft = () => ({
    reference_camera: referenceView.cameraId,
    cameras: cameraIds,
    anchors: anchors.map((anchor) => ({
      id: anchor.id,
      label: anchor.label,
      note: anchor.note,
      frame_by_camera: anchor.frameByCamera,
      pts_by_camera: anchor.ptsByCamera,
      created_at: anchor.createdAt,
    })),
    expected_revision: draftRevision,
  });

  const saveDraft = async (notify = true): Promise<boolean> => {
    if (!referenceView || views.length !== 2) return false;
    setIsSaving(true);
    setValidationIssues([]);
    try {
      const response = await saveSyncAnchorDraft(captureTakeId, serverDraft());
      setDraftRevision(response.revision);
      setSyncStatus(response.status);
      setLegacyImportAvailable(false);
      if (notify) setNotice("草稿已保存到当前 CaptureTake");
      return true;
    } catch (error) {
      if (isAnalysisApiError(error) && error.status === 409) {
        try {
          const current = await getSyncAnchorDraft(captureTakeId);
          applyDraftResponse(current);
          setNotice("草稿版本已变化，已加载最新服务端版本。");
        } catch {
          setNotice("草稿版本已变化，请重新加载服务端草稿后再保存。");
        }
      } else {
        setNotice(errorMessage(error));
      }
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const importLegacyDraft = async () => {
    if (await saveDraft(false)) setNotice("旧浏览器草稿已导入服务端");
  };

  const confirmDraft = async () => {
    if (!referenceView || views.length !== 2 || !enoughAnchors) return;
    setIsConfirming(true);
    setValidationIssues([]);
    try {
      const response = await confirmSyncAnchors(captureTakeId, serverDraft());
      setSyncStatus(response.status);
      setDraftRevision(response.status.revision);
      setNotice("同步锚点已确认，正在返回双摄分析向导");
      window.setTimeout(() => onNavigate(returnTo), 250);
    } catch (error) {
      if (isAnalysisApiError(error) && error.status === 422) {
        setValidationIssues(validationMessages(error));
        setNotice("服务端校验未通过，草稿仍保留");
      } else if (isAnalysisApiError(error) && error.status === 409) {
        setNotice("确认版本已变化，请重新加载后再提交");
      } else {
        setNotice(errorMessage(error));
      }
    } finally {
      setIsConfirming(false);
    }
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName)) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        seekToPosition(selectedSlot, (selectedView?.framePosition ?? 0) + (event.key === "ArrowLeft" ? -1 : 1));
      }
      if (event.key === " ") {
        event.preventDefault();
        toggleViewPlayback(selectedSlot);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedSlot, selectedView, seekToPosition, toggleViewPlayback]);

  if (isLoading) {
    return <PageFrame><div className="mx-auto mt-20 max-w-md rounded-2xl border border-[#DDE9D6] bg-white p-6 text-center text-sm text-slate-500">正在加载两路视频和 source PTS…</div></PageFrame>;
  }

  if (loadError || !take || !session || views.length !== 2) {
    return (
      <PageFrame>
        <div className="mx-auto mt-16 max-w-lg rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-6">
          <div className="flex items-center gap-2 text-sm font-bold text-[#991B1B]"><AlertTriangle size={17} /> 工作台无法打开</div>
          <p className="mt-3 text-sm leading-6 text-[#B91C1C]">{loadError ?? "双摄 registered video 或 source timing 不完整。"}</p>
          <button className="quiet-button mt-5 px-4 py-2 text-sm" onClick={() => onNavigate(returnTo)} type="button"><ArrowLeft size={15} />返回双摄分析</button>
        </div>
      </PageFrame>
    );
  }

  const referenceCamera = referenceView.cameraId;
  const enoughAnchors = (coverage?.count ?? 0) >= 3;
  const broadCoverage = Boolean(coverage && coverage.spanRatio >= 0.5);

  return (
    <PageFrame>
      <section className="mx-auto max-w-[1380px]">
        <button className="mb-5 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]" onClick={() => onNavigate(returnTo)} type="button"><ArrowLeft size={16} />返回双摄分析</button>

        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.16em] text-[#168A34]"><Link2 size={14} />Manual sync anchors</div>
            <h1 className="text-3xl font-black tracking-tight text-[#14241B]">双摄同步锚点工作台</h1>
            <p className="mt-2 text-sm text-slate-500">{take.id} · {session.court_name || "未知球场"} · {session.duration_sec != null ? `${Math.round(session.duration_sec)} 秒` : "—"}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="quiet-button px-3 py-2 text-xs" onClick={toggleAllPlayback} type="button">{allPlaying ? <Pause size={15} /> : <Play size={15} />}{allPlaying ? "暂停双路" : "同步播放"}</button>
            <button className="quiet-button px-3 py-2 text-xs" onClick={() => window.location.reload()} type="button"><RefreshCw size={15} />重新加载</button>
          </div>
        </header>

        <div className="mb-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <WorkbenchStatus label="reference" value={referenceCamera} good />
          <WorkbenchStatus label="camera pair" value={`${cameraIds[0]} ↔ ${cameraIds[1]}`} good />
          <WorkbenchStatus label="timing authority" value="source_pts / source_pts" good />
          <WorkbenchStatus label="anchors" value={`${coverage?.count ?? 0} / min 3`} good={enoughAnchors} />
        </div>

        <section className="mb-5 rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-black text-[#14241B]">
                当前状态：{syncStatus?.state ?? "required"}
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-500">
                revision {syncStatus?.revision ?? draftRevision} · 服务端保存后可跨浏览器继续编辑
              </div>
            </div>
            {legacyImportAvailable && (
              <button className="quiet-button px-3 py-2 text-xs" onClick={() => void importLegacyDraft()} type="button">
                导入旧浏览器草稿
              </button>
            )}
          </div>
          {validationIssues.length > 0 && (
            <div className="mt-3 rounded-xl border border-[#FCA5A5] bg-[#FEF2F2] p-3 text-xs leading-5 text-[#991B1B]">
              {validationIssues.map((issue) => <div key={issue}>{issue}</div>)}
            </div>
          )}
        </section>

        <div className="mb-5 grid gap-4 lg:grid-cols-2">
          {views.map((view) => (
            <CameraVideoCard
              key={view.slot}
              isPlaying={playingBySlot[view.slot]}
              onFrameInput={(frameNumber) => seekToFrameNumber(view.slot, frameNumber)}
              onLoadedMetadata={(video) => {
                const frame = getTimingFrame(view.timing.frames, view.framePosition);
                if (frame) video.currentTime = frame.pts_seconds;
              }}
              onPlayingChange={(playing) => setPlayingBySlot((current) => ({ ...current, [view.slot]: playing }))}
              onSelect={() => setSelectedSlot(view.slot)}
              onStep={(delta) => seekToPosition(view.slot, view.framePosition + delta)}
              onTimeUpdate={(currentTime) => handleVideoTime(view.slot, currentTime)}
              onTogglePlay={() => toggleViewPlayback(view.slot)}
              selected={selectedSlot === view.slot}
              videoRef={(element) => { videoRefs.current[view.slot] = element; }}
              view={view}
            />
          ))}
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <section className="min-w-0 rounded-2xl border border-[#DDE9D6] bg-white p-5 shadow-[0_8px_24px_rgba(16,24,40,0.05)]">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-black text-[#14241B]"><CircleHelp size={16} className="text-[#168A34]" />记录共同事件</div>
                <p className="mt-1 text-xs leading-5 text-slate-500">当前两路画面都定位到同一个可见事件后，再保存一行锚点。</p>
              </div>
              <span className="rounded-full bg-[#F5FAF1] px-3 py-1 text-xs font-bold text-[#168A34]">当前选择：{selectedSlot}</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,180px)_minmax(0,1fr)_auto]">
              <input className="field-input !rounded-xl !px-3 !py-2.5" onChange={(event) => setEventLabel(event.target.value)} placeholder="事件标签（可选）" value={eventLabel} />
              <input className="field-input !rounded-xl !px-3 !py-2.5" onChange={(event) => setEventNote(event.target.value)} placeholder="备注（可选）" value={eventNote} />
              <button className="green-button !rounded-xl px-4 py-2.5 text-xs" disabled={views.length !== 2} onClick={recordAnchor} type="button"><CheckCircle2 size={15} />记录锚点</button>
            </div>
            {notice && <div className="mt-3 rounded-xl border border-[#DDE9D6] bg-[#F5FAF1] px-3 py-2 text-xs font-semibold text-[#168A34]">{notice}</div>}

            <div className="mt-5 overflow-x-auto rounded-xl border border-[#EAECF0]">
              <table className="w-full min-w-[720px] border-collapse text-left text-xs">
                <thead className="bg-[#F9FAFB] text-[10px] font-black uppercase tracking-[0.1em] text-slate-400">
                  <tr><th className="px-3 py-3"># / 事件</th><th className="px-3 py-3">Camera {cameraIds[0]} 帧 · PTS</th><th className="px-3 py-3">Camera {cameraIds[1]} 帧 · PTS</th><th className="px-3 py-3">备注</th><th className="px-3 py-3 text-right">操作</th></tr>
                </thead>
                <tbody className="divide-y divide-[#EAECF0]">
                  {anchors.length === 0 && <tr><td className="px-3 py-8 text-center text-slate-400" colSpan={5}>还没有锚点</td></tr>}
                  {anchors.map((anchor, index) => (
                    <tr className="hover:bg-[#FAFCF9]" key={anchor.id}>
                      <td className="px-3 py-3"><button className="text-left font-bold text-[#14241B] hover:text-[#168A34]" onClick={() => selectAnchor(anchor)} type="button">{index + 1}. {anchor.label}</button></td>
                      <td className="px-3 py-3 font-mono tabular-nums text-[#344054]">#{anchor.frameByCamera?.[cameraIds[0]] ?? "—"} · {formatPts(anchor.ptsByCamera?.[cameraIds[0]])}</td>
                      <td className="px-3 py-3 font-mono tabular-nums text-[#344054]">#{anchor.frameByCamera?.[cameraIds[1]] ?? "—"} · {formatPts(anchor.ptsByCamera?.[cameraIds[1]])}</td>
                      <td className="max-w-[180px] truncate px-3 py-3 text-slate-500">{anchor.note || "—"}</td>
                      <td className="px-3 py-3 text-right"><button aria-label={`删除 ${anchor.label}`} className="rounded-lg p-2 text-slate-400 transition hover:bg-[#FEF2F2] hover:text-[#B91C1C]" onClick={() => deleteAnchor(anchor.id)} title="删除锚点" type="button"><Trash2 size={15} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="space-y-4">
            <section className="rounded-2xl border border-[#DDE9D6] bg-white p-5 shadow-[0_8px_24px_rgba(16,24,40,0.05)]">
              <div className="flex items-center gap-2 text-sm font-black text-[#14241B]"><Clock3 size={16} className="text-[#168A34]" />锚点覆盖</div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                {[{ label: "前段", ok: coverage?.hasEarly }, { label: "中段", ok: coverage?.hasMiddle }, { label: "后段", ok: coverage?.hasLate }].map((item) => <div className={`rounded-xl border px-2 py-3 ${item.ok ? "border-[#B7E2C1] bg-[#F5FAF1]" : "border-[#EAECF0] bg-[#F9FAFB]"}`} key={item.label}><div className={`mx-auto mb-1 grid size-5 place-items-center rounded-full ${item.ok ? "bg-[#19B84C] text-white" : "bg-slate-200 text-slate-400"}`}>{item.ok ? <CheckCircle2 size={13} /> : <span className="text-[10px]">·</span>}</div><div className="text-xs font-bold text-slate-500">{item.label}</div></div>)}
              </div>
              <div className="mt-4 space-y-2 text-xs text-slate-500"><div className="flex justify-between"><span>已记录</span><strong className={enoughAnchors ? "text-[#168A34]" : "text-[#A45A00]"}>{coverage?.count ?? 0} 组</strong></div><div className="flex justify-between"><span>参考时间跨度</span><strong className={broadCoverage ? "text-[#168A34]" : "text-[#A45A00]"}>{((coverage?.spanRatio ?? 0) * 100).toFixed(1)}%</strong></div></div>
              <div className={`mt-4 rounded-xl border px-3 py-3 text-xs leading-5 ${enoughAnchors && broadCoverage ? "border-[#B7E2C1] bg-[#F5FAF1] text-[#168A34]" : "border-[#F4D8A8] bg-[#FDF6E7] text-[#8A5A00]"}`}>{enoughAnchors ? (broadCoverage ? "数量和跨时段覆盖已满足人工输入建议。" : "数量已满足；建议再补一个更靠前或更靠后的事件。") : "至少记录 3 组共同事件后再导出。"}</div>
            </section>

            <section className="rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-5">
              <div className="text-sm font-black text-[#14241B]">提交并确认</div>
              <p className="mt-2 text-xs leading-5 text-slate-500">服务端将重新校验 camera identity、覆盖范围和 residual；确认成功后返回分析向导。</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
                <button className="green-button !rounded-xl px-3 py-2.5 text-xs" disabled={!enoughAnchors || isConfirming} onClick={() => void confirmDraft()} type="button"><CheckCircle2 size={15} />{isConfirming ? "正在确认…" : "提交并确认"}</button>
                <button className="quiet-button !rounded-xl px-3 py-2.5 text-xs" disabled={isSaving} onClick={() => void saveDraft()} type="button"><RefreshCw size={15} />{isSaving ? "正在保存…" : "保存草稿"}</button>
                <button className="quiet-button !rounded-xl px-3 py-2.5 text-xs" disabled={!enoughAnchors} onClick={exportAnchors} type="button"><Download size={15} />诊断下载</button>
                <button className="quiet-button !rounded-xl px-3 py-2.5 text-xs" disabled={!enoughAnchors} onClick={() => void copyAnchors()} type="button"><Copy size={15} />复制 JSON</button>
              </div>
              <a className="mt-3 block text-xs font-semibold text-[#168A34] underline" href={getSyncAnchorExportUrl(captureTakeId)} target="_blank" rel="noreferrer">打开服务端当前导出</a>
              <div className="mt-4 rounded-xl border border-[#DDE9D6] bg-white/80 p-3 text-[11px] leading-5 text-slate-500"><code className="break-all font-mono">reference_camera: {referenceCamera}</code><br /><code className="break-all font-mono">cameras: {cameraIds.join(", ")}</code><br /><code className="break-all font-mono">anchors: {anchors.length}</code></div>
            </section>
          </aside>
        </div>
      </section>
    </PageFrame>
  );
}
