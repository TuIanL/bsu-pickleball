import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Play, Scissors, Combine, Archive, RotateCcw, Tags, BadgeCheck, Ban, Crosshair, ListChecks, StepForward } from "lucide-react";
import type { BoundaryReviewSummary, CaptureSegmentSummary, CaptureTakeSummary, SessionTimelineEvent } from "../types/report";
import type { NavigateFn } from "../app/navigationTypes";
import { createRallySegment, getBoundaryReview, getCaptureTake, listSegments, patchSegment, reviewSegmentBoundary, splitSegment, mergeSegments, archiveSegment, restoreSegment, createAnalysisBatch, listTimelineEvents, getVideoStreamUrl, renumberRallyOrdinals } from "../services/analysisClient";
import { SegmentVideoPlayer, type SegmentVideoPlayerHandle } from "../components/SegmentVideoPlayer";
import { EditableSegmentTimeline } from "../components/EditableSegmentTimeline";

type FilterType = "all" | "set" | "game" | "rally";
type ReviewQueueFilter = "sampled" | "pending" | "reviewed" | "excluded" | "all";
type BoundaryDraft = { startMs?: number; endMs?: number | null };
type NewRallyDraft = { startMs: number | null; endMs: number | null };

export function SegmentManagerPage({
  fieldSessionId,
  takeId,
  onNavigate,
  embedded,
}: {
  fieldSessionId: string;
  takeId: string;
  onNavigate: NavigateFn;
  embedded?: boolean;
}) {
  const [take, setTake] = useState<CaptureTakeSummary | null>(null);
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const [events, setEvents] = useState<SessionTimelineEvent[]>([]);
  const [filter, setFilter] = useState<FilterType>("rally");
  const [reviewMode, setReviewMode] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mode") === "boundary-review");
  const [reviewQueueFilter, setReviewQueueFilter] = useState<ReviewQueueFilter>("sampled");
  const [reviewSummary, setReviewSummary] = useState<BoundaryReviewSummary | null>(null);
  const [boundaryDrafts, setBoundaryDrafts] = useState<Record<string, BoundaryDraft>>({});
  const [newRallyDraft, setNewRallyDraft] = useState<NewRallyDraft | null>(null);
  const [newRallySaving, setNewRallySaving] = useState(false);
  const [newRallyError, setNewRallyError] = useState<string | null>(null);
  const [ordinalEditorOpen, setOrdinalEditorOpen] = useState(false);
  const [ordinalStartInput, setOrdinalStartInput] = useState("1");
  const [ordinalSaving, setOrdinalSaving] = useState(false);
  const [ordinalError, setOrdinalError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editingLabel, setEditingLabel] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [activeVideoIndex, setActiveVideoIndex] = useState(0);
  const [loadError, setLoadError] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);
  const [playbackMode, setPlaybackMode] = useState<"idle" | "segment">("idle");
  const [boundarySavingId, setBoundarySavingId] = useState<string | null>(null);
  const [synchronizedPlaying, setSynchronizedPlayingState] = useState(false);
  const playerRef = useRef<SegmentVideoPlayerHandle>(null);
  const secondaryPlayerRef = useRef<SegmentVideoPlayerHandle>(null);
  const labelClickTimerRef = useRef<number | null>(null);
  const synchronizedPlayingRef = useRef(false);
  const playbackWindowRef = useRef<{ startMs: number; endMs: number } | null>(null);

  // 可播放视频源来自 take.video_ids（按机位顺序），单摄即单选项、双摄可切换机位。
  // 不使用 source_session_id（采集会话 ID ≠ video_id，流地址会 404）。
  const trackOptions = useMemo(
    () =>
      (take?.video_ids ?? []).map((id, i) => ({
        label: (take?.video_ids?.length ?? 0) > 1 ? `机位${i + 1}` : "原视频",
        url: getVideoStreamUrl(id) ?? "",
      })),
    [take?.video_ids],
  );
  const activeVideoUrl = trackOptions[activeVideoIndex]?.url ?? "";

  const loadData = useCallback(async () => {
    // 四个数据源相互独立：take 详情（渲染必需）、segments、边界复核、timeline-events，
    // 各自独立兜底，任一失败不得让整页永久停在「加载中...」。
    let takeFailed = false;
    let loadedSegments: CaptureSegmentSummary[] = [];
    let loadedReview: BoundaryReviewSummary | null = null;
    try {
      const t = await getCaptureTake(takeId);
      setTake(t);
    } catch {
      takeFailed = true;
    }
    try {
      loadedSegments = await listSegments(takeId);
    } catch { /* 片段列表缺失仅降级为空列表 */ }
    try {
      loadedReview = await getBoundaryReview(takeId);
      setReviewSummary(loadedReview);
    } catch { /* 旧后端仍可使用普通片段管理 */ }
    setSegments(mergeBoundaryReviewSegments(loadedSegments ?? [], loadedReview?.segments ?? []));
    try {
      const evts = await listTimelineEvents(fieldSessionId, { capture_take_id: takeId });
      setEvents(evts ?? []);
    } catch { /* 时间轴事件缺失不影响片段列表与播放 */ }
    if (takeFailed) setLoadError(true);
  }, [takeId, fieldSessionId]);

  useEffect(() => {
    // Load the selected CaptureTake and its derived timeline data.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes async API results.
    void loadData();
  }, [loadData]);

  useEffect(() => () => {
    if (labelClickTimerRef.current !== null) window.clearTimeout(labelClickTimerRef.current);
  }, []);

  const reviewRallies = useMemo(
    () => segments
      .filter((segment) => segment.segment_type === "rally" && segment.edit_status !== "superseded")
      .map((segment) => {
        const draft = boundaryDrafts[segment.id];
        if (!draft) return segment;
        return {
          ...segment,
          effective_start_ms: draft.startMs ?? segment.effective_start_ms ?? segment.start_ms,
          effective_end_ms: draft.endMs !== undefined ? (draft.endMs ?? undefined) : (segment.effective_end_ms ?? segment.end_ms),
          boundary_review_status: draft.startMs != null && draft.endMs == null ? "pending" : segment.boundary_review_status,
        };
      })
      .sort((a, b) => (a.effective_start_ms ?? a.start_ms) - (b.effective_start_ms ?? b.start_ms)),
    [boundaryDrafts, segments],
  );
  const sampledReviewIds = useMemo(
    () => new Set(sampleEvenly(reviewRallies, 6).map((segment) => segment.id)),
    [reviewRallies],
  );
  const reviewQueue = useMemo(() => {
    if (reviewQueueFilter === "sampled") return reviewRallies.filter((segment) => sampledReviewIds.has(segment.id));
    if (reviewQueueFilter === "pending") return reviewRallies.filter((segment) => (segment.boundary_review_status ?? "pending") === "pending");
    if (reviewQueueFilter === "reviewed") return reviewRallies.filter((segment) => {
      const status = segment.boundary_review_status ?? "pending";
      return status === "confirmed" || status === "corrected";
    });
    if (reviewQueueFilter === "excluded") return reviewRallies.filter((segment) => (segment.boundary_review_status ?? "pending") === "excluded");
    return reviewRallies;
  }, [reviewQueueFilter, reviewRallies, sampledReviewIds]);

  const filteredSegments = useMemo(() => {
    if (reviewMode) return reviewQueue;
    const active = segments.filter(s => s.edit_status === "active");
    return filter === "all" ? active : active.filter(s => s.segment_type === filter);
  }, [filter, reviewMode, reviewQueue, segments]);

  const activeReviewRally = reviewQueue.find((segment) => segment.id === activeSegmentId) ?? reviewQueue[0];

  const playableSegments = useMemo(
    () => segments
      .filter((segment) => segment.edit_status === "active")
      .sort((a, b) => {
        const aEnd = a.effective_end_ms ?? a.end_ms ?? Number.POSITIVE_INFINITY;
        const bEnd = b.effective_end_ms ?? b.end_ms ?? Number.POSITIVE_INFINITY;
        return (aEnd - (a.effective_start_ms ?? a.start_ms)) - (bEnd - (b.effective_start_ms ?? b.start_ms));
      }),
    [segments],
  );

  const findSegmentAtTime = useCallback((ms: number) => {
    return playableSegments.find((segment) => {
      const start = segment.effective_start_ms ?? segment.start_ms;
      const end = segment.effective_end_ms ?? segment.end_ms ?? durationMs;
      return end > start && ms >= start && ms <= end;
    });
  }, [durationMs, playableSegments]);

  const timelineTotalMs = useMemo(() => {
    const max = segments.reduce((m, s) => Math.max(m, s.effective_end_ms ?? s.end_ms ?? 0), 0);
    return Math.max(max, durationMs, take?.duration_ms ?? 0, 60000);
  }, [durationMs, segments, take?.duration_ms]);

  const invalidSegments = useMemo(
    () => segments.filter((segment) => {
      if (segment.edit_status === "superseded") return false;
      const start = segment.effective_start_ms ?? segment.start_ms;
      const end = segment.effective_end_ms ?? segment.end_ms;
      return start < 0 || (end != null && (end <= start || end - start < 500));
    }),
    [segments],
  );

  const refreshBoundaryReview = useCallback(async () => {
    const next = await getBoundaryReview(takeId);
    setReviewSummary(next);
    setSegments((current) => mergeBoundaryReviewSegments(current, next.segments));
    return next;
  }, [takeId]);

  const setSynchronizedPlaying = useCallback((playing: boolean) => {
    synchronizedPlayingRef.current = playing;
    setSynchronizedPlayingState(playing);
  }, []);

  const seekAllPlayers = useCallback((ms: number) => {
    playerRef.current?.seekToTakeTime(ms);
    secondaryPlayerRef.current?.seekToTakeTime(ms);
  }, []);

  const alignAllPlayers = useCallback((ms: number) => {
    playerRef.current?.syncToTakeTime(ms, 0);
    secondaryPlayerRef.current?.syncToTakeTime(ms, 0);
  }, []);

  const pauseAllPlayers = useCallback(() => {
    playerRef.current?.pause();
    secondaryPlayerRef.current?.pause();
    setSynchronizedPlaying(false);
  }, [setSynchronizedPlaying]);

  const focusReviewRally = useCallback((segment: CaptureSegmentSummary, playContext = false) => {
    const start = segment.effective_start_ms ?? segment.start_ms;
    const rawEnd = segment.effective_end_ms ?? segment.end_ms ?? start + 500;
    const contextStart = Math.max(0, start - 3000);
    // 边界倒置的异常回合也必须能被选中和播放上下文，先给它一个安全的可播放窗口，
    // 让用户可以把错误的另一端重新标定回来。
    const contextEnd = Math.min(timelineTotalMs, Math.max(start + 3000, rawEnd + 3000));
    setActiveSegmentId(segment.id);
    setCurrentTimeMs(contextStart);
    setPlaybackMode(playContext ? "segment" : "idle");
    if (playContext) {
      playbackWindowRef.current = { startMs: contextStart, endMs: contextEnd };
      setSynchronizedPlaying(true);
      playerRef.current?.playSegment(contextStart, contextEnd);
      secondaryPlayerRef.current?.playSegment(contextStart, contextEnd);
    } else {
      playbackWindowRef.current = null;
      // 选中或切换队列只定位；如果此前正在播放，先让两个视角一起停下。
      pauseAllPlayers();
      seekAllPlayers(contextStart);
    }
  }, [pauseAllPlayers, seekAllPlayers, setSynchronizedPlaying, timelineTotalMs]);

  const beginNewRally = useCallback(() => {
    playbackWindowRef.current = null;
    pauseAllPlayers();
    setOrdinalEditorOpen(false);
    setOrdinalError(null);
    setNewRallyError(null);
    setNewRallyDraft({ startMs: null, endMs: null });
    setActiveSegmentId(null);
    setPlaybackMode("idle");
  }, [pauseAllPlayers]);

  const cancelNewRally = useCallback(() => {
    setNewRallyDraft(null);
    setNewRallyError(null);
  }, []);

  const setNewRallyBoundary = useCallback((edge: "start" | "end") => {
    if (!newRallyDraft) return;
    const timestampMs = Math.max(0, Math.round(currentTimeMs));
    if (edge === "start") {
      if (newRallyDraft.endMs != null && newRallyDraft.endMs - timestampMs < 500) {
        setNewRallyError("新增回合的开始和结束时间至少需要相隔 0.5 秒。");
        return;
      }
      setNewRallyDraft((current) => current ? { ...current, startMs: timestampMs } : current);
      setNewRallyError(null);
      return;
    }
    if (newRallyDraft.startMs == null) {
      setNewRallyError("请先定位并设置新增回合的开始时间。");
      return;
    }
    if (timestampMs - newRallyDraft.startMs < 500) {
      setNewRallyError("新增回合的开始和结束时间至少需要相隔 0.5 秒。");
      return;
    }
    setNewRallyDraft((current) => current ? { ...current, endMs: timestampMs } : current);
    setNewRallyError(null);
  }, [currentTimeMs, newRallyDraft]);

  const createNewRally = useCallback(async () => {
    if (!newRallyDraft || newRallyDraft.startMs == null || newRallyDraft.endMs == null) return;
    setNewRallySaving(true);
    setNewRallyError(null);
    setSaveStatus("saving");
    try {
      const created = await createRallySegment(takeId, {
        start_ms: newRallyDraft.startMs,
        end_ms: newRallyDraft.endMs,
      });
      await refreshBoundaryReview();
      setNewRallyDraft(null);
      setReviewQueueFilter("pending");
      setActiveSegmentId(created.id);
      focusReviewRally(created);
      setSaveStatus("saved");
      window.setTimeout(() => setSaveStatus("idle"), 1500);
    } catch (error: unknown) {
      setNewRallyError(error instanceof Error ? error.message : "新增回合失败，请重试。");
      setSaveStatus("error");
    } finally {
      setNewRallySaving(false);
    }
  }, [focusReviewRally, newRallyDraft, refreshBoundaryReview, takeId]);

  const openOrdinalEditor = useCallback(() => {
    if (!activeReviewRally) return;
    setOrdinalStartInput(String(activeReviewRally.ordinal));
    setOrdinalError(null);
    setOrdinalEditorOpen(true);
  }, [activeReviewRally]);

  const cancelOrdinalEditor = useCallback(() => {
    setOrdinalEditorOpen(false);
    setOrdinalError(null);
  }, []);

  const applyRallyOrdinals = useCallback(async (mode: "from_anchor" | "whole_take") => {
    const anchorId = activeReviewRally?.id;
    if (mode === "from_anchor" && !anchorId) return;

    const startOrdinal = mode === "whole_take" ? 1 : Number.parseInt(ordinalStartInput.trim(), 10);
    if (!Number.isInteger(startOrdinal) || startOrdinal < 1) {
      setOrdinalError("请输入大于等于 1 的整数分序号。");
      return;
    }

    setOrdinalSaving(true);
    setOrdinalError(null);
    setSaveStatus("saving");
    try {
      const result = await renumberRallyOrdinals(takeId, {
        mode,
        anchor_segment_id: mode === "from_anchor" ? anchorId : undefined,
        start_ordinal: startOrdinal,
      });
      const updatedAnchor = anchorId ? result.segments.find((segment) => segment.id === anchorId) : undefined;
      await refreshBoundaryReview();
      setOrdinalEditorOpen(false);
      setSaveStatus("saved");
      window.setTimeout(() => setSaveStatus("idle"), 1500);
      if (updatedAnchor) {
        setActiveSegmentId(updatedAnchor.id);
        focusReviewRally(updatedAnchor);
      }
    } catch (error: unknown) {
      setOrdinalError(error instanceof Error ? error.message : "修改分序号失败，请重试。");
      setSaveStatus("error");
    } finally {
      setOrdinalSaving(false);
    }
  }, [activeReviewRally, focusReviewRally, ordinalStartInput, refreshBoundaryReview, takeId]);

  const handleSynchronizedPlaybackToggle = useCallback((sourceTimeMs: number, playing: boolean) => {
    const nextTimeMs = Number.isFinite(sourceTimeMs) ? Math.max(0, sourceTimeMs) : currentTimeMs;
    if (playing) {
      pauseAllPlayers();
      alignAllPlayers(nextTimeMs);
      setCurrentTimeMs(nextTimeMs);
      return;
    }

    const playbackWindow = playbackWindowRef.current;
    if (playbackWindow && nextTimeMs < playbackWindow.endMs) {
      setPlaybackMode("segment");
      setCurrentTimeMs(nextTimeMs);
      setSynchronizedPlaying(true);
      playerRef.current?.playSegment(nextTimeMs, playbackWindow.endMs);
      secondaryPlayerRef.current?.playSegment(nextTimeMs, playbackWindow.endMs);
      return;
    }

    playbackWindowRef.current = null;
    setPlaybackMode("idle");
    seekAllPlayers(nextTimeMs);
    setCurrentTimeMs(nextTimeMs);
    setSynchronizedPlaying(true);
    playerRef.current?.play();
    secondaryPlayerRef.current?.play();
  }, [alignAllPlayers, currentTimeMs, pauseAllPlayers, seekAllPlayers, setSynchronizedPlaying]);

  const handleSynchronizedSeek = useCallback((ms: number) => {
    const nextTimeMs = Math.max(0, Number.isFinite(ms) ? ms : 0);
    playbackWindowRef.current = null;
    setPlaybackMode("idle");
    pauseAllPlayers();
    seekAllPlayers(nextTimeMs);
    setCurrentTimeMs(nextTimeMs);
  }, [pauseAllPlayers, seekAllPlayers]);

  const handleSynchronizedFrameStep = useCallback((direction: "forward" | "backward", sourceTimeMs: number, stepMs = 1000 / 60) => {
    const current = Number.isFinite(sourceTimeMs) ? sourceTimeMs : currentTimeMs;
    const nextTimeMs = Math.max(0, current + (direction === "forward" ? stepMs : -stepMs));
    playbackWindowRef.current = null;
    setPlaybackMode("idle");
    pauseAllPlayers();
    seekAllPlayers(nextTimeMs);
    setCurrentTimeMs(nextTimeMs);
  }, [currentTimeMs, pauseAllPlayers, seekAllPlayers]);

  useEffect(() => {
    if (!reviewMode || !synchronizedPlaying) return;

    let animationFrameId: number | null = null;
    let timeoutId: number | null = null;
    let lastRenderedTimeMs = -Infinity;

    const tick = () => {
      const masterTimeMs = playerRef.current?.getCurrentTimeMs();
      if (masterTimeMs != null && Number.isFinite(masterTimeMs)) {
        secondaryPlayerRef.current?.syncToTakeTime(masterTimeMs, 12);
        if (Math.abs(masterTimeMs - lastRenderedTimeMs) >= 20) {
          lastRenderedTimeMs = masterTimeMs;
          setCurrentTimeMs(masterTimeMs);
        }
      }

      if (!synchronizedPlayingRef.current) return;
      if (typeof window.requestAnimationFrame === "function") {
        animationFrameId = window.requestAnimationFrame(tick);
      } else {
        timeoutId = window.setTimeout(tick, 50);
      }
    };

    tick();
    return () => {
      if (animationFrameId != null) window.cancelAnimationFrame(animationFrameId);
      if (timeoutId != null) window.clearTimeout(timeoutId);
    };
  }, [reviewMode, synchronizedPlaying]);

  const advanceToNextPending = useCallback((fromId: string) => {
    const fromIndex = reviewQueue.findIndex((segment) => segment.id === fromId);
    const ordered = fromIndex >= 0
      ? [...reviewQueue.slice(fromIndex + 1), ...reviewQueue.slice(0, fromIndex)]
      : reviewQueue;
    const next = ordered.find((segment) => segment.id !== fromId && (segment.boundary_review_status ?? "pending") === "pending");
    if (next) focusReviewRally(next);
  }, [focusReviewRally, reviewQueue]);

  const handleSegmentClick = (seg: CaptureSegmentSummary) => {
    const start = seg.effective_start_ms ?? seg.start_ms;
    const rawEnd = seg.effective_end_ms ?? seg.end_ms ?? Math.max(durationMs, start + 500);
    setActiveSegmentId(seg.id);
    if (reviewMode) {
      if (ordinalEditorOpen) {
        setOrdinalStartInput(String(seg.ordinal));
        setOrdinalError(null);
      }
      // 选中只定位，不自动开始播放；播放必须由用户主动点击播放器或“播放前后 3 秒”。
      focusReviewRally(seg);
    } else {
      setCurrentTimeMs(start);
      setPlaybackMode("segment");
      if (rawEnd > start) playerRef.current?.playSegment(start, rawEnd);
    }
  };

  const handleLabelClick = (event: React.MouseEvent, seg: CaptureSegmentSummary) => {
    event.stopPropagation();
    if (labelClickTimerRef.current !== null) window.clearTimeout(labelClickTimerRef.current);
    // Keep single-click playback compatible with double-click label editing.
    labelClickTimerRef.current = window.setTimeout(() => {
      labelClickTimerRef.current = null;
      handleSegmentClick(seg);
    }, 250);
  };

  const handleLabelDoubleClick = (event: React.MouseEvent, seg: CaptureSegmentSummary) => {
    event.stopPropagation();
    if (labelClickTimerRef.current !== null) {
      window.clearTimeout(labelClickTimerRef.current);
      labelClickTimerRef.current = null;
    }
    setEditingLabel(seg.id);
  };

  const handleTimelineSeek = (ms: number) => {
    if (reviewMode) {
      playbackWindowRef.current = null;
      pauseAllPlayers();
      // 复核时，拖动时间线只改变播放头，不改变“当前正在修改”的回合。
      // 当前回合必须由用户明确点击回合、时间线回合块或下一条来切换。
      setCurrentTimeMs(ms);
      setPlaybackMode("idle");
      seekAllPlayers(ms);
      return;
    }
    setCurrentTimeMs(ms);
    setActiveSegmentId(findSegmentAtTime(ms)?.id ?? null);
    setPlaybackMode("idle");
    seekAllPlayers(ms);
  };

  const handleTimelineSegmentClick = (segmentId: string, startMs: number) => {
    if (reviewMode) {
      playbackWindowRef.current = null;
      pauseAllPlayers();
    }
    setActiveSegmentId(segmentId);
    if (reviewMode && ordinalEditorOpen) {
      const selected = reviewRallies.find((segment) => segment.id === segmentId);
      if (selected) {
        setOrdinalStartInput(String(selected.ordinal));
        setOrdinalError(null);
      }
    }
    setCurrentTimeMs(startMs);
    setPlaybackMode("idle");
    seekAllPlayers(startMs);
  };

  const handleTimeUpdate = useCallback((ms: number) => {
    setCurrentTimeMs(ms);
    // 边界复核中，播放头的时间更新不能反向覆盖用户已经选中的回合。
    // 否则选中第 N 分后，定位到上下文时间会再次按播放头命中回合，导致 UI 跳回第一分。
    if (reviewMode) return;
    const active = findSegmentAtTime(ms);
    if (active) setActiveSegmentId(active.id);
  }, [findSegmentAtTime, reviewMode]);

  const handleDurationReady = useCallback((ms: number) => {
    setDurationMs(Math.max(0, ms));
  }, []);

  const handleSegmentPlaybackEnd = useCallback(() => {
    playbackWindowRef.current = null;
    pauseAllPlayers();
    setPlaybackMode("idle");
  }, [pauseAllPlayers]);

  const handleSaveLabel = async (seg: CaptureSegmentSummary, label: string) => {
    setSaveStatus("saving");
    try {
      await patchSegment(seg.id, { label, expected_version: seg.edit_version });
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 1500);
      await loadData();
    } catch {
      setSaveStatus("error");
    }
    setEditingLabel(null);
  };

  const handleBoundaryChange = useCallback(async (
    segId: string,
    startMs: number,
    endMs: number,
    expectedVersion: number,
  ) => {
    if (reviewMode) {
      const segment = reviewRallies.find((item) => item.id === segId);
      if (!segment) return;
      const previousStart = segment.effective_start_ms ?? segment.start_ms;
      const previousEnd = segment.effective_end_ms ?? segment.end_ms;
      const startChanged = startMs !== previousStart;
      const endChanged = endMs !== previousEnd;
      if (startChanged && !endChanged) {
        if (previousEnd == null || previousEnd - startMs < 500) {
          setSaveStatus("error");
          return;
        }
        setBoundaryDrafts((current) => ({ ...current, [segId]: { ...current[segId], startMs } }));
        setSaveStatus("saved");
        window.setTimeout(() => setSaveStatus("idle"), 1500);
        return;
      }
    }
    setBoundarySavingId(segId);
    setSaveStatus("saving");
    try {
      const updated = reviewMode
        ? await reviewSegmentBoundary(segId, {
            decision: "corrected",
            start_ms: startMs,
            end_ms: endMs,
            expected_version: expectedVersion,
          })
        : await patchSegment(segId, {
            corrected_start_ms: startMs,
            corrected_end_ms: endMs,
            expected_version: expectedVersion,
          });
      setSegments((current) => current.map((segment) => segment.id === segId ? updated : segment));
      if (reviewMode) {
        setBoundaryDrafts((current) => {
          if (!current[segId]) return current;
          const next = { ...current };
          delete next[segId];
          return next;
        });
        await refreshBoundaryReview();
      }
      setSaveStatus("saved");
      window.setTimeout(() => setSaveStatus("idle"), 1500);
    } catch {
      setSaveStatus("error");
      await loadData();
    } finally {
      setBoundarySavingId(null);
    }
  }, [loadData, refreshBoundaryReview, reviewMode, reviewRallies]);

  const saveBoundaryReview = useCallback(async (
    segment: CaptureSegmentSummary,
    decision: "confirmed" | "corrected" | "excluded",
    startMs?: number,
    endMs?: number,
    advance = true,
  ) => {
    setBoundarySavingId(segment.id);
    setSaveStatus("saving");
    try {
      await reviewSegmentBoundary(segment.id, {
        decision,
        expected_version: segment.edit_version,
        start_ms: startMs,
        end_ms: endMs,
      });
      setBoundaryDrafts((current) => {
        if (!current[segment.id]) return current;
        const next = { ...current };
        delete next[segment.id];
        return next;
      });
      await refreshBoundaryReview();
      setSaveStatus("saved");
      window.setTimeout(() => setSaveStatus("idle"), 1500);
      if (advance) advanceToNextPending(segment.id);
    } catch {
      setSaveStatus("error");
      await loadData();
    } finally {
      setBoundarySavingId(null);
    }
  }, [advanceToNextPending, loadData, refreshBoundaryReview]);

  const confirmActiveReview = () => {
    if (!activeReviewRally || activeReviewRally.edit_status !== "active") return;
    const draft = boundaryDrafts[activeReviewRally.id];
    if (draft?.startMs != null && draft.endMs == null) return;
    const start = activeReviewRally.effective_start_ms ?? activeReviewRally.start_ms;
    const end = activeReviewRally.effective_end_ms ?? activeReviewRally.end_ms;
    if (end == null) return;
    const changed = start !== activeReviewRally.start_ms || end !== activeReviewRally.end_ms;
    void saveBoundaryReview(activeReviewRally, changed ? "corrected" : "confirmed", start, end);
  };

  const setActiveBoundaryFromPlayhead = (edge: "start" | "end") => {
    if (!activeReviewRally || activeReviewRally.edit_status !== "active") return;
    const existingDraft = boundaryDrafts[activeReviewRally.id] ?? {};
    const currentStart = existingDraft.startMs ?? (activeReviewRally.effective_start_ms ?? activeReviewRally.start_ms);
    const currentEnd = existingDraft.endMs !== undefined
      ? existingDraft.endMs
      : (activeReviewRally.effective_end_ms ?? activeReviewRally.end_ms);
    const start = edge === "start" ? Math.round(currentTimeMs) : currentStart;
    const end = edge === "end" ? Math.round(currentTimeMs) : currentEnd;
    if (edge === "start") {
      // 边界倒置时允许先保存“起点草稿”，把错误的结束点视为未设置，
      // 这样用户可以继续定位并设置结束点，而不会被中间态校验锁死。
      const keepCurrentEnd = currentEnd != null && currentEnd - start >= 500;
      setBoundaryDrafts((current) => ({
        ...current,
        [activeReviewRally.id]: {
          ...current[activeReviewRally.id],
          startMs: start,
          ...(keepCurrentEnd ? {} : { endMs: null }),
        },
      }));
      setSaveStatus("saved");
      window.setTimeout(() => setSaveStatus("idle"), 1500);
      return;
    }
    if (currentStart == null || end == null || end - currentStart < 500) {
      setSaveStatus("error");
      return;
    }
    void saveBoundaryReview(activeReviewRally, "corrected", currentStart, end, false);
  };

  const getReviewQueueForFilter = useCallback((nextFilter: ReviewQueueFilter) => {
    if (nextFilter === "sampled") return reviewRallies.filter((segment) => sampledReviewIds.has(segment.id));
    if (nextFilter === "pending") return reviewRallies.filter((segment) => (segment.boundary_review_status ?? "pending") === "pending");
    if (nextFilter === "reviewed") return reviewRallies.filter((segment) => {
      const status = segment.boundary_review_status ?? "pending";
      return status === "confirmed" || status === "corrected";
    });
    if (nextFilter === "excluded") return reviewRallies.filter((segment) => (segment.boundary_review_status ?? "pending") === "excluded");
    return reviewRallies;
  }, [reviewRallies, sampledReviewIds]);

  const handleReviewQueueFilterChange = useCallback((nextFilter: ReviewQueueFilter) => {
    const nextQueue = getReviewQueueForFilter(nextFilter);
    const nextActive = nextQueue.find((segment) => segment.id === activeSegmentId) ?? nextQueue[0];
    setReviewQueueFilter(nextFilter);
    setSelectedIds(new Set());
    playbackWindowRef.current = null;
    if (nextActive) {
      // 切换队列只定位到当前队列的回合，不抢先播放，也不沿用另一个队列的隐藏选中项。
      setActiveSegmentId(nextActive.id);
      focusReviewRally(nextActive);
    } else {
      setActiveSegmentId(null);
      setPlaybackMode("idle");
      pauseAllPlayers();
      seekAllPlayers(0);
      setCurrentTimeMs(0);
    }
  }, [activeSegmentId, focusReviewRally, getReviewQueueForFilter, pauseAllPlayers, seekAllPlayers]);

  const handleSplit = async (seg: CaptureSegmentSummary) => {
    const ms = seg.effective_start_ms ?? seg.start_ms + 3000;
    try {
      await splitSegment(seg.id, ms);
      await loadData();
    } catch { /* ignore */ }
  };

  const handleMerge = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length !== 2) return;
    try {
      await mergeSegments(ids as [string, string]);
      setSelectedIds(new Set());
      await loadData();
    } catch { /* ignore */ }
  };

  const handleArchive = async (seg: CaptureSegmentSummary) => {
    try {
      await archiveSegment(seg.id);
      await loadData();
    } catch { /* ignore */ }
  };

  const handleRestore = async (seg: CaptureSegmentSummary) => {
    try {
      await restoreSegment(seg.id);
      await loadData();
    } catch { /* ignore */ }
  };

  const handleCreateAnalysis = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      const result = await createAnalysisBatch(takeId, ids);
      alert(`已创建分析批次: ${result.batch_id}\n${result.items.length} 个任务已排队`);
      setSelectedIds(new Set());
    } catch (error: unknown) {
      alert(`创建失败: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleBoundaryReviewMode = () => {
    const next = !reviewMode;
    setReviewMode(next);
    setSelectedIds(new Set());
    if (!next) {
      cancelNewRally();
      cancelOrdinalEditor();
    }
    if (next) {
      setFilter("rally");
      setReviewQueueFilter("sampled");
      const first = reviewQueue.find((segment) => (segment.boundary_review_status ?? "pending") === "pending") ?? reviewQueue[0];
      if (first) focusReviewRally(first);
    }
  };

  if (loadError) {
    return (
      <div className="p-8 text-center space-y-3">
        <p className="text-sm text-[#EF4444]">片段数据加载失败，请重试</p>
        <button
          className="rounded-lg border border-[#2F80ED] px-4 py-1.5 text-sm text-[#2F80ED] font-bold hover:bg-[#2F80ED]/5 transition"
          onClick={() => { setLoadError(false); setTake(null); void loadData(); }}
        >
          重试
        </button>
      </div>
    );
  }

  if (!take) return <div className="p-8 text-slate-400">加载中...</div>;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4" data-playback-mode={playbackMode}>
      {/* Header */}
      <div className="flex items-center gap-4">
        {!embedded && (
          <>
            <button className="text-sm text-[#2F80ED] flex items-center gap-1" onClick={() => onNavigate(`/capture/${fieldSessionId}`)}>
              <ArrowLeft size={16} /> 返回采集任务
            </button>
            <h2 className="text-lg font-bold text-[#14241B]">{reviewMode ? "有效回合边界复核" : "片段管理"}</h2>
          </>
        )}
        <div className="ml-auto flex items-center gap-2">
          {saveStatus === "saving" && <span className="text-xs text-[#E8A838]">保存中...</span>}
          {saveStatus === "saved" && <span className="text-xs text-[#22C55E]">已保存</span>}
          {saveStatus === "error" && <span className="text-xs text-[#EF4444]">保存失败</span>}
          <button
            className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-bold transition ${reviewMode ? "border-[#168A34] bg-[#F0FDF4] text-[#168A34]" : "border-[#168A34] text-[#168A34] hover:bg-[#F0FDF4]"}`}
            onClick={toggleBoundaryReviewMode}
            type="button"
          >
            <ListChecks size={16} /> {reviewMode ? "退出边界复核" : "有效回合复核"}
          </button>
          {reviewMode && (
            <>
              <button
                className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-bold transition disabled:opacity-50 ${ordinalEditorOpen ? "border-[#2F80ED] bg-[#EFF6FF] text-[#2563EB]" : "border-[#2F80ED] text-[#2563EB] hover:bg-[#EFF6FF]"}`}
                disabled={!activeReviewRally || activeReviewRally.edit_status !== "active" || newRallyDraft != null || newRallySaving || ordinalSaving}
                onClick={openOrdinalEditor}
                type="button"
              >
                <Tags size={16} /> 调整分序号
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-lg border border-[#F59E0B] bg-[#FFF7ED] px-3 py-2 text-sm font-bold text-[#B45309] hover:bg-[#FFEDD5] transition disabled:opacity-50"
                disabled={newRallyDraft != null || newRallySaving || ordinalEditorOpen || ordinalSaving}
                onClick={beginNewRally}
                type="button"
              >
                <Crosshair size={16} /> {newRallyDraft ? "正在新增回合" : "新增漏记回合"}
              </button>
            </>
          )}
          {!reviewMode && (
            <>
              <button
                className="green-button inline-flex items-center gap-2 px-4 py-2 text-sm"
                disabled={selectedIds.size === 0}
                onClick={handleCreateAnalysis}
              >
                <Play size={16} /> 创建分析 ({selectedIds.size})
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-lg border border-[#2F80ED] px-3 py-2 text-sm font-bold text-[#2F80ED] hover:bg-[#EFF6FF] transition"
                onClick={() => onNavigate(`/capture/${fieldSessionId}/takes/${takeId}/scoring-calibration`)}
              >
                <Tags size={16} /> 评分校准
              </button>
            </>
          )}
        </div>
      </div>

      {reviewMode && reviewSummary && (
        <div className="grid gap-2 rounded-2xl border border-[#B7E4C7] bg-[#F0FDF4] p-4 sm:grid-cols-5">
          <ReviewMetric label="全部回合" value={reviewSummary.total_count} />
          <ReviewMetric label="待复核" value={reviewSummary.pending_count} tone="pending" />
          <ReviewMetric label="确认不变" value={reviewSummary.confirmed_count} tone="confirmed" />
          <ReviewMetric label="已修正" value={reviewSummary.corrected_count} tone="corrected" />
          <ReviewMetric label="已排除" value={reviewSummary.excluded_count} tone="excluded" />
        </div>
      )}

      {/* Main layout */}
      <div className={reviewMode ? "space-y-4" : "grid grid-cols-[1fr_320px] gap-4"}>
        {/* Player */}
        <div className={reviewMode && trackOptions.length > 1 ? "grid gap-4 lg:grid-cols-2" : ""}>
          {(reviewMode ? trackOptions[0]?.url : activeVideoUrl) ? (
            <SegmentVideoPlayer
              ref={playerRef}
              videoUrl={reviewMode ? trackOptions[0].url : activeVideoUrl}
              fps={60}
              preload={reviewMode ? "metadata" : "auto"}
              trackLabel={reviewMode ? (trackOptions[0]?.label ?? "机位1") : undefined}
              trackOptions={reviewMode ? undefined : trackOptions}
              onTrackChange={(i) => setActiveVideoIndex(i)}
              onTimeUpdate={handleTimeUpdate}
              onDurationReady={handleDurationReady}
              onSegmentPlaybackEnd={handleSegmentPlaybackEnd}
              onPlaybackToggle={reviewMode ? handleSynchronizedPlaybackToggle : undefined}
              onSeekRequest={reviewMode ? handleSynchronizedSeek : undefined}
              onFrameStepRequest={reviewMode ? handleSynchronizedFrameStep : undefined}
            />
          ) : (
            <div className="grid aspect-video place-items-center rounded-2xl border border-[#DDE9D6] bg-slate-50 text-sm text-[#98A2B3]">
              暂无可用视频回放
            </div>
          )}
          {reviewMode && trackOptions[1]?.url && (
            <SegmentVideoPlayer
              ref={secondaryPlayerRef}
              videoUrl={trackOptions[1].url}
              fps={60}
              preload="metadata"
              trackLabel={trackOptions[1].label}
              onDurationReady={handleDurationReady}
              onSegmentPlaybackEnd={handleSegmentPlaybackEnd}
              onPlaybackToggle={handleSynchronizedPlaybackToggle}
              onSeekRequest={handleSynchronizedSeek}
              onFrameStepRequest={handleSynchronizedFrameStep}
            />
          )}
        </div>

        {reviewMode && ordinalEditorOpen && activeReviewRally ? (
          <RallyOrdinalControls
            segment={activeReviewRally}
            value={ordinalStartInput}
            saving={ordinalSaving}
            error={ordinalError}
            onChange={setOrdinalStartInput}
            onFromAnchor={() => void applyRallyOrdinals("from_anchor")}
            onWholeTake={() => void applyRallyOrdinals("whole_take")}
            onCancel={cancelOrdinalEditor}
          />
        ) : reviewMode && newRallyDraft ? (
          <NewRallyControls
            draft={newRallyDraft}
            currentTimeMs={currentTimeMs}
            saving={newRallySaving}
            error={newRallyError}
            onSetStart={() => setNewRallyBoundary("start")}
            onSetEnd={() => setNewRallyBoundary("end")}
            onCreate={() => void createNewRally()}
            onCancel={cancelNewRally}
          />
        ) : reviewMode && activeReviewRally ? (
          <BoundaryReviewControls
            segment={activeReviewRally}
            draft={boundaryDrafts[activeReviewRally.id]}
            currentTimeMs={currentTimeMs}
            saving={boundarySavingId === activeReviewRally.id}
            onPlayContext={() => focusReviewRally(activeReviewRally, true)}
            onSetStart={() => setActiveBoundaryFromPlayhead("start")}
            onSetEnd={() => setActiveBoundaryFromPlayhead("end")}
            onConfirm={confirmActiveReview}
            onExclude={() => void saveBoundaryReview(activeReviewRally, "excluded")}
            onNext={() => advanceToNextPending(activeReviewRally.id)}
          />
        ) : null}

        {/* Segment list */}
        <div className={`rounded-2xl border border-[#DDE9D6] bg-white p-4 overflow-y-auto ${reviewMode ? "max-h-[420px]" : "max-h-[500px]"}`}>
          <div className="flex flex-wrap gap-2 mb-3">
            {(reviewMode ? (["sampled", "pending", "reviewed", "excluded", "all"] as ReviewQueueFilter[]) : (["all", "set", "game", "rally"] as FilterType[])).map(f => (
              <button
                key={f}
                className={`text-xs px-3 py-1 rounded-full font-bold transition ${(reviewMode ? reviewQueueFilter === f : filter === f) ? "bg-[#2F80ED] text-white" : "bg-slate-100 text-slate-500"}`}
                onClick={() => {
                  if (reviewMode) handleReviewQueueFilterChange(f as ReviewQueueFilter);
                  else {
                    setFilter(f as FilterType);
                    setSelectedIds(new Set());
                  }
                }}
              >
                {reviewMode
                  ? { sampled: "首轮抽样", pending: "全部待复核", reviewed: "已确认/修正", excluded: "已排除", all: "全部" }[f as ReviewQueueFilter]
                  : { all: "全部", set: "盘", game: "局", rally: "分" }[f as FilterType]}
              </button>
            ))}
          </div>

          {filteredSegments.map(seg => (
            <div
              key={seg.id}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-sm border mb-1 transition ${
                activeSegmentId === seg.id
                  ? "border-[#2F80ED] bg-[#EFF6FF] ring-1 ring-[#2F80ED]/30"
                  : selectedIds.has(seg.id)
                    ? "border-[#22C55E] bg-[#F0FDF4]"
                    : "border-transparent hover:bg-slate-50"
              }`}
              onClick={() => handleSegmentClick(seg)}
            >
              {!reviewMode && (
                <input
                  type="checkbox"
                  className="size-3.5 accent-[#22C55E] shrink-0"
                  checked={selectedIds.has(seg.id)}
                  onChange={(e) => { e.stopPropagation(); toggleSelect(seg.id); }}
                  onClick={(e) => e.stopPropagation()}
                />
              )}
              {!reviewMode && editingLabel === seg.id ? (
                <input
                  className="flex-1 text-xs border rounded px-1"
                  defaultValue={seg.label}
                  onBlur={(e) => handleSaveLabel(seg, e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSaveLabel(seg, (e.target as HTMLInputElement).value); }}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span
                  className="flex-1 font-medium text-[#14241B] text-xs truncate"
                  title={reviewMode ? "点击播放边界前后 3 秒" : "单击播放；双击编辑标签"}
                  onClick={(e) => reviewMode ? undefined : handleLabelClick(e, seg)}
                  onDoubleClick={(e) => reviewMode ? undefined : handleLabelDoubleClick(e, seg)}
                >
                  {seg.label}
                </span>
              )}
              {reviewMode && <BoundaryReviewBadge status={seg.boundary_review_status ?? "pending"} />}
              {reviewMode && boundaryDrafts[seg.id]?.startMs != null && boundaryDrafts[seg.id]?.endMs == null && (
                <span className="rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-bold text-orange-700">起点已标</span>
              )}
              <span className="text-[10px] text-slate-400 tabular-nums shrink-0">
                {formatMs(seg.effective_start_ms ?? seg.start_ms)}→{seg.effective_end_ms != null ? formatMs(seg.effective_end_ms) : "?"}
              </span>
              <div className="flex gap-0.5 shrink-0">
                {!reviewMode && seg.segment_type === "rally" && (
                  <>
                    <button className="p-0.5 hover:bg-slate-200 rounded" title="拆分" onClick={(e) => { e.stopPropagation(); handleSplit(seg); }}><Scissors size={12} /></button>
                    {selectedIds.size === 2 && selectedIds.has(seg.id) && (
                      <button className="p-0.5 hover:bg-slate-200 rounded text-[#22C55E]" title="合并选中" onClick={(e) => { e.stopPropagation(); handleMerge(); }}><Combine size={12} /></button>
                    )}
                  </>
                )}
                {!reviewMode && <button className="p-0.5 hover:bg-slate-200 rounded" title="归档" onClick={(e) => { e.stopPropagation(); handleArchive(seg); }}><Archive size={12} /></button>}
                {seg.edit_status === "archived" && (
                  <button className="p-0.5 hover:bg-slate-200 rounded text-[#22C55E]" title="恢复" onClick={(e) => { e.stopPropagation(); handleRestore(seg); }}><RotateCcw size={12} /></button>
                )}
              </div>
            </div>
          ))}

          {!reviewMode && selectedIds.size === 2 && filter === "rally" && (
            <button className="w-full mt-2 text-xs bg-[#22C55E]/10 border border-[#22C55E] text-[#22C55E] rounded-lg py-1.5 font-bold hover:bg-[#22C55E]/20 transition" onClick={handleMerge}>
              <Combine size={14} className="inline mr-1" /> 合并选中的 2 个 Rally
            </button>
          )}
        </div>
      </div>

      {invalidSegments.length > 0 && (
        <div className="rounded-xl border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-xs text-[#B91C1C]">
          检测到 {invalidSegments.length} 个片段边界异常（结束时间必须晚于起始时间且时长不少于 0.5 秒），已禁止继续拖拽保存。请先修正或重新生成片段。
        </div>
      )}

      {/* Timeline */}
      <EditableSegmentTimeline
        segments={segments}
        events={events}
        totalDurationMs={timelineTotalMs}
        currentTimeMs={currentTimeMs}
        activeSegmentId={activeSegmentId}
        savingSegmentId={boundarySavingId}
        reviewMode={reviewMode}
        onSeek={handleTimelineSeek}
        onSegmentClick={handleTimelineSegmentClick}
        onBoundaryChange={handleBoundaryChange}
      />
    </div>
  );
}

function formatMs(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function formatPreciseMs(ms: number): string {
  const clamped = Math.max(0, Math.round(ms));
  const minutes = Math.floor(clamped / 60000);
  const seconds = Math.floor((clamped % 60000) / 1000);
  const millis = clamped % 1000;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function mergeBoundaryReviewSegments(
  base: CaptureSegmentSummary[],
  reviewed: CaptureSegmentSummary[],
): CaptureSegmentSummary[] {
  const byId = new Map(base.map((segment) => [segment.id, segment]));
  for (const segment of reviewed) byId.set(segment.id, segment);
  return Array.from(byId.values()).sort((a, b) => {
    const typeOrder = { set: 0, game: 1, rally: 2, custom: 3 } as const;
    const timeDelta = (a.effective_start_ms ?? a.start_ms) - (b.effective_start_ms ?? b.start_ms);
    return timeDelta || typeOrder[a.segment_type] - typeOrder[b.segment_type];
  });
}

function sampleEvenly<T>(values: T[], limit: number): T[] {
  if (values.length <= limit) return values;
  if (limit <= 1) return [values[0]];
  const indexes = new Set(Array.from({ length: limit }, (_, index) => Math.round(index * (values.length - 1) / (limit - 1))));
  return Array.from(indexes).sort((a, b) => a - b).map((index) => values[index]);
}

function ReviewMetric({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "pending" | "confirmed" | "corrected" | "excluded" }) {
  const colors = {
    default: "text-[#14241B]",
    pending: "text-[#D97706]",
    confirmed: "text-[#168A34]",
    corrected: "text-[#2563EB]",
    excluded: "text-[#DC2626]",
  };
  return (
    <div className="rounded-xl bg-white/80 px-3 py-2 text-center">
      <div className={`text-lg font-black tabular-nums ${colors[tone]}`}>{value}</div>
      <div className="text-[11px] text-slate-500">{label}</div>
    </div>
  );
}

function BoundaryReviewBadge({ status }: { status: "pending" | "confirmed" | "corrected" | "excluded" }) {
  const styles = {
    pending: "bg-amber-50 text-amber-700",
    confirmed: "bg-emerald-50 text-emerald-700",
    corrected: "bg-blue-50 text-blue-700",
    excluded: "bg-red-50 text-red-700",
  };
  const labels = { pending: "待复核", confirmed: "已确认", corrected: "已修正", excluded: "已排除" };
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${styles[status]}`}>{labels[status]}</span>;
}

function RallyOrdinalControls({
  segment,
  value,
  saving,
  error,
  onChange,
  onFromAnchor,
  onWholeTake,
  onCancel,
}: {
  segment: CaptureSegmentSummary;
  value: string;
  saving: boolean;
  error: string | null;
  onChange: (value: string) => void;
  onFromAnchor: () => void;
  onWholeTake: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="rounded-2xl border-2 border-[#2F80ED] bg-[#EFF6FF] p-4 shadow-[0_8px_24px_rgba(47,128,237,0.12)]"
      data-testid="rally-ordinal-editor"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[#2563EB]">
            <Tags size={18} strokeWidth={2.5} />
            <span className="text-xs font-black tracking-wide">当前正在修改这一分的序号</span>
          </div>
          <h3 className="mt-1 text-xl font-black text-[#1E3A8A]">正在调整：第 {segment.ordinal} 分</h3>
          <p className="mt-1 text-xs font-bold text-[#1D4ED8]">只修改“第几分”和默认分名称，不修改这分的起止时间。</p>
          <label className="mt-3 flex items-center gap-2 text-xs font-bold text-slate-700" htmlFor="rally-ordinal-start">
            当前所选这一分应为第
            <input
              id="rally-ordinal-start"
              className="w-20 rounded-lg border border-blue-200 bg-white px-2 py-1.5 text-center text-sm font-black text-[#1E3A8A] outline-none focus:border-[#2F80ED] focus:ring-2 focus:ring-blue-100"
              type="number"
              min={1}
              step={1}
              value={value}
              disabled={saving}
              onChange={(event) => onChange(event.target.value)}
            />
            分
          </label>
          <p className="mt-2 text-[11px] text-slate-500">从当前分开始会把后面的 active 回合依次加 1；整段视频重排会按视频时间从第 1 分开始。</p>
          {error && <p className="mt-1 text-xs font-bold text-red-600">{error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="inline-flex items-center gap-1 rounded-lg bg-[#2F80ED] px-3 py-2 text-xs font-bold text-white hover:bg-[#2563EB] disabled:opacity-50" disabled={saving} onClick={onFromAnchor} type="button">
            <Tags size={14} /> 从当前分开始连续编号
          </button>
          <button className="quiet-button inline-flex items-center gap-1 px-3 py-2 text-xs" disabled={saving} onClick={onWholeTake} type="button">
            <ListChecks size={14} /> 整段视频从第1分统一编号
          </button>
          <button className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-600 hover:bg-white disabled:opacity-50" disabled={saving} onClick={onCancel} type="button">
            <Ban size={14} /> 取消调整
          </button>
        </div>
      </div>
    </div>
  );
}

function NewRallyControls({
  draft,
  currentTimeMs,
  saving,
  error,
  onSetStart,
  onSetEnd,
  onCreate,
  onCancel,
}: {
  draft: NewRallyDraft;
  currentTimeMs: number;
  saving: boolean;
  error: string | null;
  onSetStart: () => void;
  onSetEnd: () => void;
  onCreate: () => void;
  onCancel: () => void;
}) {
  const complete = draft.startMs != null && draft.endMs != null;
  return (
    <div
      className="rounded-2xl border-2 border-[#F59E0B] bg-[#FFF7ED] p-4 shadow-[0_8px_24px_rgba(245,158,11,0.12)]"
      data-testid="new-rally-draft"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[#B45309]">
            <Crosshair size={18} strokeWidth={2.5} />
            <span className="text-xs font-black tracking-wide">正在补录一个漏记的有效回合</span>
          </div>
          <h3 className="mt-1 text-xl font-black text-[#7C2D12]">新增回合边界</h3>
          <p className="mt-1 text-xs font-bold text-[#9A3412]">先定位到回合开始和结束，再创建；两个视角共用同一个播放头。</p>
          <p className="mt-1 text-xs text-slate-500">
            当前播放头 {formatPreciseMs(currentTimeMs)} · 开始 {draft.startMs == null ? "未设置" : formatPreciseMs(draft.startMs)} · 结束 {draft.endMs == null ? "未设置" : formatPreciseMs(draft.endMs)}
          </p>
          {error && <p className="mt-1 text-xs font-bold text-red-600">{error}</p>}
          {!complete && !error && <p className="mt-1 text-[11px] text-slate-400">新增回合至少需要 0.5 秒；创建后会自动加入“全部待复核”。</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="quiet-button inline-flex items-center gap-1 px-3 py-2 text-xs" disabled={saving} onClick={onSetStart} type="button">
            <Crosshair size={14} /> 当前帧设为新增开始
          </button>
          <button className="quiet-button inline-flex items-center gap-1 px-3 py-2 text-xs" disabled={saving} onClick={onSetEnd} type="button">
            <Crosshair size={14} /> 当前帧设为新增结束
          </button>
          <button className="inline-flex items-center gap-1 rounded-lg bg-[#168A34] px-3 py-2 text-xs font-bold text-white disabled:opacity-50" disabled={saving || !complete} onClick={onCreate} type="button">
            <BadgeCheck size={14} /> 创建回合并加入待复核
          </button>
          <button className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-600 hover:bg-white disabled:opacity-50" disabled={saving} onClick={onCancel} type="button">
            <Ban size={14} /> 取消新增
          </button>
        </div>
      </div>
    </div>
  );
}

function BoundaryReviewControls({
  segment,
  draft,
  currentTimeMs,
  saving,
  onPlayContext,
  onSetStart,
  onSetEnd,
  onConfirm,
  onExclude,
  onNext,
}: {
  segment: CaptureSegmentSummary;
  draft?: BoundaryDraft;
  currentTimeMs: number;
  saving: boolean;
  onPlayContext: () => void;
  onSetStart: () => void;
  onSetEnd: () => void;
  onConfirm: () => void;
  onExclude: () => void;
  onNext: () => void;
}) {
  const originalStart = segment.start_ms;
  const start = segment.effective_start_ms ?? segment.start_ms;
  const end = draft?.endMs !== undefined
    ? (draft.endMs ?? start)
    : (segment.effective_end_ms ?? segment.end_ms ?? start);
  const originalEnd = segment.end_ms ?? start;
  const excluded = segment.edit_status === "archived";
  const waitingForEnd = draft?.startMs != null && draft.endMs == null;
  return (
    <div
      className="rounded-2xl border-2 border-[#F59E0B] bg-[#FFF7ED] p-4 shadow-[0_8px_24px_rgba(245,158,11,0.12)]"
      data-testid="active-boundary-review"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[#B45309]">
            <Crosshair size={18} strokeWidth={2.5} />
            <span className="text-xs font-black tracking-wide">当前正在修改这一分的开始和结束时间</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h3 className="text-xl font-black text-[#7C2D12]">正在修改：第 {segment.ordinal} 分</h3>
            <BoundaryReviewBadge status={segment.boundary_review_status ?? "pending"} />
          </div>
          <p className="mt-1 text-xs font-bold text-[#9A3412]">{segment.label || `第 ${segment.ordinal} 回合`} · 下方标定按钮只会作用于当前这一分</p>
          <p className="mt-1 text-xs text-slate-500">
            原始边界 {formatPreciseMs(originalStart)} → {formatPreciseMs(originalEnd)} · 当前边界 {formatPreciseMs(start)} → {formatPreciseMs(end)} · 播放头 {formatPreciseMs(currentTimeMs)}
          </p>
          {waitingForEnd && (
            <p className="mt-1 text-xs font-bold text-orange-700">起点已标定，仍待标定结束时间；当前回合不会算作复核完成。</p>
          )}
          <p className="mt-1 text-[11px] text-slate-400">可拖动下方回合时间条两端；也可逐帧定位后，用当前播放头设置起点或终点。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="quiet-button inline-flex items-center gap-1 px-3 py-2 text-xs" onClick={onPlayContext} type="button">
            <Play size={14} /> 播放前后 3 秒
          </button>
          <button className="quiet-button inline-flex items-center gap-1 px-3 py-2 text-xs" disabled={saving || excluded} onClick={onSetStart} type="button">
            <Crosshair size={14} /> 当前帧设为开始
          </button>
          <button className="quiet-button inline-flex items-center gap-1 px-3 py-2 text-xs" disabled={saving || excluded} onClick={onSetEnd} type="button">
            <Crosshair size={14} /> 当前帧设为结束
          </button>
          <button className="inline-flex items-center gap-1 rounded-lg bg-[#168A34] px-3 py-2 text-xs font-bold text-white disabled:opacity-50" disabled={saving || excluded || waitingForEnd} onClick={onConfirm} type="button">
            <BadgeCheck size={14} /> 确认并下一条
          </button>
          <button className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-3 py-2 text-xs font-bold text-red-600 disabled:opacity-50" disabled={saving || excluded} onClick={onExclude} type="button">
            <Ban size={14} /> 排除该回合
          </button>
          <button className="quiet-button inline-flex items-center gap-1 px-3 py-2 text-xs" onClick={onNext} type="button">
            <StepForward size={14} /> 下一待复核
          </button>
        </div>
      </div>
    </div>
  );
}
