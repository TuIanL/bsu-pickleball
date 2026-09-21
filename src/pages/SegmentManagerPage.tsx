import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Play, Scissors, Combine, Archive, RotateCcw, Tags, BadgeCheck, Ban, Crosshair, ListChecks, StepForward } from "lucide-react";
import type { BoundaryReviewSummary, CaptureSegmentSummary, CaptureTakeSummary, FormalSegmentationSummary, MatchStateCandidateReviewSummary, MatchStateCandidateSegment, SessionTimelineEvent } from "../types/report";
import type { NavigateFn } from "../app/navigationTypes";
import { createRallySegment, decideMatchStateCandidate, getBoundaryReview, getCaptureTake, getFormalSegmentationSummary, getMatchStateCandidates, isAnalysisApiError, listSegments, patchSegment, reviewSegmentBoundary, splitSegment, mergeSegments, archiveSegment, restoreSegment, createAnalysisBatch, listTimelineEvents, getVideoStreamUrl, renumberRallyOrdinals } from "../services/analysisClient";
import { SegmentVideoPlayer, type SegmentVideoPlayerHandle, type SegmentPlaybackEndReason } from "../components/SegmentVideoPlayer";
import { EditableSegmentTimeline } from "../components/EditableSegmentTimeline";

type FilterType = "all" | "set" | "game" | "rally";
type ReviewQueueFilter = "sampled" | "pending" | "reviewed" | "excluded" | "all";
type ReviewFocus = "model" | "manual";
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
  const [segmentationSummary, setSegmentationSummary] = useState<FormalSegmentationSummary | null>(null);
  const [events, setEvents] = useState<SessionTimelineEvent[]>([]);
  const [filter, setFilter] = useState<FilterType>("rally");
  const [reviewMode, setReviewMode] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mode") === "boundary-review");
  const [reviewFocus, setReviewFocus] = useState<ReviewFocus>("manual");
  const [reviewQueueFilter, setReviewQueueFilter] = useState<ReviewQueueFilter>("sampled");
  const [reviewSummary, setReviewSummary] = useState<BoundaryReviewSummary | null>(null);
  const [candidateSummary, setCandidateSummary] = useState<MatchStateCandidateReviewSummary | null>(null);
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(null);
  const [candidateDraft, setCandidateDraft] = useState<BoundaryDraft>({});
  const [candidateSaving, setCandidateSaving] = useState(false);
  const [candidateError, setCandidateError] = useState<string | null>(null);
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
    // 五个数据源相互独立：take 详情（渲染必需）、segments、正式切分摘要、边界复核、timeline-events，
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
    if (!reviewMode) {
      try {
        setSegmentationSummary(await getFormalSegmentationSummary(takeId));
      } catch {
        setSegmentationSummary(null);
      }
    } else {
      setSegmentationSummary(null);
    }
    try {
      if (reviewMode) {
        loadedReview = await getBoundaryReview(takeId);
        setReviewSummary(loadedReview);
      }
    } catch { /* 旧后端仍可使用普通片段管理 */ }
    setSegments(reviewMode ? mergeBoundaryReviewSegments(loadedSegments ?? [], loadedReview?.segments ?? []) : loadedSegments);
    try {
      const evts = await listTimelineEvents(fieldSessionId, { capture_take_id: takeId });
      setEvents(evts ?? []);
    } catch { /* 时间轴事件缺失不影响片段列表与播放 */ }
    if (takeFailed) setLoadError(true);
  }, [takeId, fieldSessionId, reviewMode]);

  useEffect(() => {
    // Load the selected CaptureTake and its derived timeline data.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes async API results.
    void loadData();
  }, [loadData]);

  const loadModelCandidates = useCallback(async () => {
    try {
      const candidates = await getMatchStateCandidates(takeId);
      setCandidateSummary(candidates);
      if (candidates.status === "available" && candidates.candidates.length > 0) setReviewFocus("model");
      setActiveCandidateId((current) => current ?? candidates.candidates.find((item) => item.status === "unreviewed")?.candidate_id ?? null);
    } catch {
      setCandidateSummary({ schema_version: "match-state-candidate-review.v1", status: "unavailable", reason: "candidate_api_unavailable", capture_take_id: takeId, revision: 0, candidates: [] });
    }
  }, [takeId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes an independent async API result.
    if (reviewMode) void loadModelCandidates();
  }, [loadModelCandidates, reviewMode]);

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
  const activeCandidate = useMemo(
    () => candidateSummary?.candidates.find((candidate) => candidate.candidate_id === activeCandidateId) ?? null,
    [activeCandidateId, candidateSummary?.candidates],
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

  const manualSegments = useMemo(
    () => filteredSegments.filter((segment) => segment.source !== "algorithm" && !segment.segmentation_run_id),
    [filteredSegments],
  );
  const modelSegments = useMemo(
    () => {
      const currentRunId = segmentationSummary?.run_id;
      if (!currentRunId) return [];
      return filteredSegments.filter((segment) => segment.segmentation_run_id === currentRunId);
    },
    [filteredSegments, segmentationSummary?.run_id],
  );

  // 回放提示（中央回合大字 + 进度条区间配色）的唯一数据来源：当前已发布 run 的 active algorithm Rally。
  // 刻意不复用 modelSegments —— 它建立在被列表筛选器过滤过的 filteredSegments 之上，切换筛选器会让
  // 进度条配色凭空变化；也不复用 playableSegments —— 它混入人工片段，且按时长升序排序，
  // 用于查找会优先命中短片段（见 findSegmentAtTime 的调用语境）。
  const autoRallySegments = useMemo(() => {
    const currentRunId = segmentationSummary?.run_id;
    if (!currentRunId) return [];
    return segments
      .filter(
        (segment) =>
          segment.edit_status === "active"
          && segment.source === "algorithm"
          && segment.segmentation_run_id === currentRunId,
      )
      .map((segment) => ({
        id: segment.id,
        ordinal: segment.ordinal,
        startMs: segment.effective_start_ms ?? segment.start_ms,
        // 终点留 null 表示「延伸到媒体末尾」，由播放器按媒体总时长兜底，
        // 与 findSegmentAtTime 的现有约定一致。
        endMs: segment.effective_end_ms ?? segment.end_ms ?? null,
      }))
      .sort((a, b) => a.startMs - b.startMs);
  }, [segments, segmentationSummary?.run_id]);

  // 播放头当前所属的自动回合。判定取左闭右开 [起点, 终点)：首尾相接的两个回合在共享边界上
  // 必须只命中一个，用 <= 会让 find 命中先出现的那个，产生瞬时但可见的错误编号。
  // cause 告诉播放器这次回合变化是不是自动续播引起的：自动续播受提示合并与最小静默间隔约束，
  // 用户主动导航永远提示（见 SegmentVideoPlayer 的提示状态机）。
  // 用 state 而非 ref：useMemo 内不允许读 ref；且续播分支与下一次时间更新分属不同事件批次，
  // state 在 memo 重算前必然已提交。
  const [autoAdvancePending, setAutoAdvancePending] = useState(false);
  const activeAutoRally = useMemo(() => {
    const hit = autoRallySegments.find((segment) => {
      const end = segment.endMs ?? durationMs;
      return end > segment.startMs && currentTimeMs >= segment.startMs && currentTimeMs < end;
    });
    return hit
      ? { id: hit.id, ordinal: hit.ordinal, cause: autoAdvancePending ? ("autoAdvance" as const) : ("user" as const) }
      : null;
  }, [autoAdvancePending, autoRallySegments, currentTimeMs, durationMs]);

  // 「自动跳过非比赛时间」开关：默认开启（规格已把「播到终点自动暂停」改成条件式）。
  // 刻意不持久化：每次进入片段页都回到开启，用户关闭只对当前会话有效。
  const [autoSkipEnabled, setAutoSkipEnabled] = useState(true);
  const autoSkipUnavailableReason = autoRallySegments.length === 0
    ? segmentationSummary?.run_id
      ? "当前切分结果没有自动回合"
      : "无正式切分结果"
    : null;

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

  const focusReviewRally = useCallback((segment: CaptureSegmentSummary, mode: "idle" | "context" | "segment" = "idle") => {
    const start = segment.effective_start_ms ?? segment.start_ms;
    const rawEnd = segment.effective_end_ms ?? segment.end_ms ?? start + 500;
    const segmentEnd = rawEnd > start ? rawEnd : Math.min(timelineTotalMs, start + 500);
    const contextStart = Math.max(0, start - 3000);
    // 边界倒置的异常回合也必须能被选中和播放上下文，先给它一个安全的可播放窗口，
    // 让用户可以把错误的另一端重新标定回来。
    const contextEnd = Math.min(timelineTotalMs, Math.max(start + 3000, segmentEnd + 3000));
    const playbackStart = mode === "context" ? contextStart : start;
    const playbackEnd = mode === "segment" ? segmentEnd : contextEnd;
    setActiveSegmentId(segment.id);
    setCurrentTimeMs(playbackStart);
    setPlaybackMode(mode === "idle" ? "idle" : "segment");
    if (mode !== "idle") {
      playbackWindowRef.current = { startMs: playbackStart, endMs: playbackEnd };
      setSynchronizedPlaying(true);
      playerRef.current?.playSegment(playbackStart, playbackEnd);
      secondaryPlayerRef.current?.playSegment(playbackStart, playbackEnd);
    } else {
      playbackWindowRef.current = null;
      // 选中或切换队列只定位；如果此前正在播放，先让两个视角一起停下。
      pauseAllPlayers();
      seekAllPlayers(playbackStart);
    }
  }, [pauseAllPlayers, seekAllPlayers, setSynchronizedPlaying, timelineTotalMs]);

  const focusModelCandidate = useCallback((candidate: MatchStateCandidateSegment, playContext = false) => {
    // 候选复核播放使用候选本身的边界：从候选起点开始，到候选终点自动暂停。
    // 之前这里沿用了人工边界的“前后 3 秒”上下文窗口，导致播放会越过候选终点，
    // 用户无法在播放器停下的瞬间判断模型给出的结束边界。
    const previewStart = Math.max(0, candidate.start_ms);
    const previewEnd = Math.min(timelineTotalMs, Math.max(previewStart + 500, candidate.end_ms));
    setActiveCandidateId(candidate.candidate_id);
    setActiveSegmentId(null);
    setCandidateDraft({});
    setCandidateError(null);
    setCurrentTimeMs(previewStart);
    if (playContext) {
      playbackWindowRef.current = { startMs: previewStart, endMs: previewEnd };
      setPlaybackMode("segment");
      setSynchronizedPlaying(true);
      playerRef.current?.playSegment(previewStart, previewEnd);
      secondaryPlayerRef.current?.playSegment(previewStart, previewEnd);
    } else {
      setPlaybackMode("idle");
      pauseAllPlayers();
      seekAllPlayers(previewStart);
      // 选中后如果用户点击播放器自身的播放按钮，也应沿用候选边界自动暂停。
      // 必须在 seekAllPlayers 之后设置，因为 seek 可能清理上一个片段播放窗口。
      playbackWindowRef.current = { startMs: previewStart, endMs: previewEnd };
    }
  }, [pauseAllPlayers, seekAllPlayers, setSynchronizedPlaying, timelineTotalMs]);

  const handleReviewFocusChange = useCallback((next: ReviewFocus) => {
    setReviewFocus(next);
    if (next === "model") {
      if (activeCandidate) focusModelCandidate(activeCandidate);
      else {
        playbackWindowRef.current = null;
        pauseAllPlayers();
      }
      return;
    }
    if (activeReviewRally) focusReviewRally(activeReviewRally);
    else {
      playbackWindowRef.current = null;
      pauseAllPlayers();
    }
  }, [activeCandidate, activeReviewRally, focusModelCandidate, focusReviewRally, pauseAllPlayers]);

  const setCandidateBoundaryFromPlayhead = useCallback((edge: "start" | "end") => {
    if (!activeCandidate) return;
    setCandidateDraft((current) => ({ ...current, [edge === "start" ? "startMs" : "endMs"]: Math.round(currentTimeMs) }));
    setCandidateError(null);
  }, [activeCandidate, currentTimeMs]);

  const saveCandidateDecision = useCallback(async (decision: "accepted" | "corrected" | "rejected") => {
    if (!activeCandidate || !candidateSummary || candidateSummary.status !== "available") return;
    const start = candidateDraft.startMs ?? activeCandidate.start_ms;
    const end = candidateDraft.endMs ?? activeCandidate.end_ms;
    if (decision === "corrected" && end - start < 500) {
      setCandidateError("修正后的结束时间必须晚于开始且至少持续 0.5 秒");
      return;
    }
    setCandidateSaving(true);
    setCandidateError(null);
    try {
      const decisionRequest = {
        decision,
        expected_revision: candidateSummary.revision,
        ...(decision === "corrected" ? { start_ms: Math.round(start), end_ms: Math.round(end) } : {}),
        ...(candidateSummary.artifact_version ? { artifact_version: candidateSummary.artifact_version } : {}),
      };
      await decideMatchStateCandidate(takeId, activeCandidate.candidate_id, decisionRequest);
      const refreshed = await getMatchStateCandidates(takeId);
      setCandidateSummary(refreshed);
      setCandidateDraft({});
      setActiveCandidateId(refreshed.candidates.find((item) => item.status === "unreviewed")?.candidate_id ?? activeCandidate.candidate_id);
      await refreshBoundaryReview();
    } catch (error) {
      if (isAnalysisApiError(error) && error.status === 409) {
        // Keep the user's draft visible while replacing only the server
        // snapshot.  A stale tab must never silently resubmit old boundaries.
        try {
          const refreshed = await getMatchStateCandidates(takeId);
          setCandidateSummary(refreshed);
          setCandidateError("候选状态已更新，请确认当前草稿后再提交");
        } catch {
          setCandidateError("候选状态已更新，请刷新后再提交");
        }
        return;
      }
      setCandidateError(error instanceof Error ? error.message : "候选复核保存失败");
    } finally {
      setCandidateSaving(false);
    }
  }, [activeCandidate, candidateDraft.endMs, candidateDraft.startMs, candidateSummary, refreshBoundaryReview, takeId]);

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
      // 选择人工边界时直接播放该回合本身，到有效结束边界自动暂停；
      // 若需要查看边界外上下文，使用控制面板中的“播放前后 3 秒”。
      focusReviewRally(seg, "segment");
    } else {
      // 用户主动进入：清除自动续播来源标记，使中央提示走「用户主动」分支（不受节流）。
      setAutoAdvancePending(false);
      // 记录本次播放窗口，供自动续播判定「下一个区间」的起点基准。
      playbackWindowRef.current = { startMs: start, endMs: rawEnd };
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
    // 拖动时间线是用户主动定位：清除自动续播来源标记，使提示走「用户主动」分支。
    setAutoAdvancePending(false);
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
    // 点击时间线片段块同样是用户主动进入，清除自动续播来源标记。
    setAutoAdvancePending(false);
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

  const handleSegmentPlaybackEnd = useCallback((reason: SegmentPlaybackEndReason) => {
    // 只有「自然播完」且开关开启才续播；被 seek/逐帧打断的一律回到现状行为。
    const canContinue = reason === "completed" && autoSkipEnabled && !reviewMode;
    const windowEndMs = playbackWindowRef.current?.endMs ?? null;
    // 下一个区间取「起点不早于当前窗口结束时间」的第一个 algorithm 回合，
    // 不按数组下标递推：用户可能从人工片段出发，下标推进在人工片段上无定义。
    const next = canContinue && windowEndMs != null
      ? autoRallySegments.find((segment) => segment.startMs >= windowEndMs)
      : undefined;
    if (!next) {
      playbackWindowRef.current = null;
      pauseAllPlayers();
      setPlaybackMode("idle");
      return;
    }
    // 自动续播：直接从下一个回合起点继续，跳过两者之间的全部非比赛时间。
    // 保持片段播放模式与窗口记录，使连续跳转可以一直进行下去。
    setAutoAdvancePending(true);
    const nextEndMs = next.endMs ?? durationMs;
    playbackWindowRef.current = { startMs: next.startMs, endMs: nextEndMs };
    setActiveSegmentId(next.id);
    playerRef.current?.playSegment(next.startMs, nextEndMs);
  }, [autoRallySegments, autoSkipEnabled, durationMs, pauseAllPlayers, reviewMode]);

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
          {reviewMode && <button
            className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-bold transition ${reviewMode ? "border-[#168A34] bg-[#F0FDF4] text-[#168A34]" : "border-[#168A34] text-[#168A34] hover:bg-[#F0FDF4]"}`}
            onClick={toggleBoundaryReviewMode}
            type="button"
          >
            <ListChecks size={16} /> {reviewMode ? "退出边界复核" : "有效回合复核"}
          </button>}
          {reviewMode && reviewFocus === "manual" && (
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
          {/* Production segment browsing is intentionally read-only.  The
              boundary-review URL remains the isolated QA entry point for
              editing and candidate decisions. */}
        </div>
      </div>

      {reviewMode && (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-black tracking-wide text-slate-500">回合复核工作区</p>
              <h3 className="mt-1 text-base font-black text-[#14241B]">先选择要复核的数据来源</h3>
              <p className="mt-1 text-xs text-slate-500">模型候选是自动推理结果；人工边界是已有标注。两者分开展示，避免混淆。</p>
            </div>
            <div className="flex rounded-xl bg-slate-100 p-1" role="tablist" aria-label="回合复核工作区">
              <button
                type="button"
                role="tab"
                aria-selected={reviewFocus === "model"}
                onClick={() => handleReviewFocusChange("model")}
                disabled={candidateSummary?.status !== "available" || candidateSummary.candidates.length === 0}
                className={`rounded-lg px-3 py-2 text-xs font-black transition disabled:cursor-not-allowed disabled:opacity-40 ${reviewFocus === "model" ? "bg-violet-600 text-white shadow-sm" : "text-slate-600 hover:bg-white"}`}
              >
                模型候选
                <span className="ml-1 rounded-full bg-white/20 px-1.5 py-0.5 tabular-nums">{candidateSummary?.candidates.length ?? 0}</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={reviewFocus === "manual"}
                onClick={() => handleReviewFocusChange("manual")}
                className={`rounded-lg px-3 py-2 text-xs font-black transition ${reviewFocus === "manual" ? "bg-amber-500 text-white shadow-sm" : "text-slate-600 hover:bg-white"}`}
              >
                人工边界
                <span className="ml-1 rounded-full bg-black/10 px-1.5 py-0.5 tabular-nums">{reviewSummary?.total_count ?? 0}</span>
              </button>
            </div>
          </div>

          {reviewFocus === "model" && candidateSummary?.status === "available" ? (
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <ReviewMetric label="模型候选" value={candidateSummary.candidates.length} tone="model" />
              <ReviewMetric label="待复核" value={candidateSummary.candidates.filter((candidate) => candidate.status === "unreviewed").length} tone="pending" />
              <ReviewMetric label="unknown 窗口" value={Math.round((candidateSummary.unknown_rate ?? 0) * 1000) / 10} suffix="%" tone="model" />
            </div>
          ) : reviewSummary ? (
            <div className="mt-4 grid gap-2 sm:grid-cols-5">
              <ReviewMetric label="全部回合" value={reviewSummary.total_count} />
              <ReviewMetric label="待复核" value={reviewSummary.pending_count} tone="pending" />
              <ReviewMetric label="确认不变" value={reviewSummary.confirmed_count} tone="confirmed" />
              <ReviewMetric label="已修正" value={reviewSummary.corrected_count} tone="corrected" />
              <ReviewMetric label="已排除" value={reviewSummary.excluded_count} tone="excluded" />
            </div>
          ) : null}
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
              // 回放提示只在普通片段页启用；边界复核隔离模式显式不传，把启用范围表达为调用点意图，
              // 而不是依赖 reviewMode 下 segmentationSummary 恰好为 null 这一隐式巧合。
              autoRallyCue={reviewMode ? undefined : activeAutoRally}
              autoRallyBands={reviewMode ? undefined : autoRallySegments}
              autoSkip={reviewMode ? undefined : {
                enabled: autoSkipEnabled,
                onToggle: setAutoSkipEnabled,
                disabledReason: autoSkipUnavailableReason,
              }}
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

        {reviewMode && reviewFocus === "manual" && ordinalEditorOpen && activeReviewRally ? (
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
        ) : reviewMode && reviewFocus === "manual" && newRallyDraft ? (
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
        ) : reviewMode && reviewFocus === "manual" && activeReviewRally ? (
          <BoundaryReviewControls
            segment={activeReviewRally}
            draft={boundaryDrafts[activeReviewRally.id]}
            currentTimeMs={currentTimeMs}
            saving={boundarySavingId === activeReviewRally.id}
            onPlayContext={() => focusReviewRally(activeReviewRally, "context")}
            onSetStart={() => setActiveBoundaryFromPlayhead("start")}
            onSetEnd={() => setActiveBoundaryFromPlayhead("end")}
            onConfirm={confirmActiveReview}
            onExclude={() => void saveBoundaryReview(activeReviewRally, "excluded")}
            onNext={() => advanceToNextPending(activeReviewRally.id)}
          />
        ) : null}

        {reviewMode && reviewFocus === "model" && candidateSummary && (
          <ModelCandidateReviewPanel
            summary={candidateSummary}
            activeCandidate={activeCandidate}
            draft={candidateDraft}
            currentTimeMs={currentTimeMs}
            saving={candidateSaving}
            error={candidateError}
            onSelect={(candidate) => focusModelCandidate(candidate, true)}
            onPlay={(candidate) => focusModelCandidate(candidate, true)}
            onSetStart={() => setCandidateBoundaryFromPlayhead("start")}
            onSetEnd={() => setCandidateBoundaryFromPlayhead("end")}
            onAccept={() => void saveCandidateDecision("accepted")}
            onCorrect={() => void saveCandidateDecision("corrected")}
            onReject={() => void saveCandidateDecision("rejected")}
          />
        )}

        {/* Manual segment list: kept out of the model workspace so the two sources stay visually separate. */}
        {(!reviewMode || reviewFocus === "manual") && (
        <div className={`rounded-2xl border border-[#DDE9D6] bg-white p-4 overflow-y-auto ${reviewMode ? "max-h-[420px]" : "max-h-[500px]"}`}>
          {reviewMode && (
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-sm font-black text-[#14241B]">人工边界队列</h3>
                <p className="mt-0.5 text-[11px] text-slate-500">已有人工标注的回合，用于复核、修正或补录。</p>
              </div>
              <span className="rounded-full bg-amber-50 px-2 py-1 text-[10px] font-bold text-amber-700">{filteredSegments.length} 条显示</span>
            </div>
          )}
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

          {!reviewMode && (
            <div className="mb-3 border-b border-violet-100 pb-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-xs font-black text-violet-700">自动回合切分（只读）</h3>
                {segmentationSummary?.status === "succeeded" || segmentationSummary?.status === "valid_no_rallies" ? (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">正式结果</span>
                ) : segmentationSummary?.status && segmentationSummary.status !== "unavailable" ? (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">{formatSegmentationStatus(segmentationSummary.status)}</span>
                ) : null}
              </div>
              {segmentationSummary && segmentationSummary.status !== "unavailable" ? (
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                  <span>模型 {segmentationSummary.model_version ?? segmentationSummary.model_package_id ?? "未知版本"}</span>
                  <span>生成于 {formatGeneratedAt(segmentationSummary.generated_at)}</span>
                  <span>{segmentationSummary.segment_count} 个回合</span>
                  {segmentationSummary.detail && !["succeeded", "valid_no_rallies"].includes(segmentationSummary.status) && (
                    <span className="text-amber-700">{segmentationSummary.detail}</span>
                  )}
                </div>
              ) : (
                <p className="mt-1 text-[11px] text-slate-400">尚未生成正式模型结果。</p>
              )}
            </div>
          )}
          {!reviewMode && modelSegments.map((seg) => (
            <ReadOnlyModelSegmentRow key={seg.id} segment={seg} active={activeSegmentId === seg.id} onClick={() => handleSegmentClick(seg)} />
          ))}
          {!reviewMode && manualSegments.length > 0 && <h3 className="mb-2 mt-3 text-xs font-black text-amber-700">拍摄阶段人工标记</h3>}
          {(reviewMode ? filteredSegments : manualSegments).map(seg => (
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
              <span
                className="flex-1 font-medium text-[#14241B] text-xs truncate"
                title={reviewMode ? "点击从该回合起点播放，到终点自动暂停" : "点击播放该片段"}
              >
                {seg.label}
              </span>
              {reviewMode && <BoundaryReviewBadge status={seg.boundary_review_status ?? "pending"} />}
              {reviewMode && boundaryDrafts[seg.id]?.startMs != null && boundaryDrafts[seg.id]?.endMs == null && (
                <span className="rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-bold text-orange-700">起点已标</span>
              )}
              <span className="text-[10px] text-slate-400 tabular-nums shrink-0">
                {formatMs(seg.effective_start_ms ?? seg.start_ms)}→{seg.effective_end_ms != null ? formatMs(seg.effective_end_ms) : "?"}
              </span>
              {reviewMode && seg.edit_status === "archived" && (
                <span className="text-[10px] font-bold text-slate-400">已归档</span>
              )}
            </div>
          ))}

        </div>
        )}
      </div>

      {invalidSegments.length > 0 && (
        <div className="rounded-xl border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-xs text-[#B91C1C]">
          检测到 {invalidSegments.length} 个片段边界异常（结束时间必须晚于起始时间且时长不少于 0.5 秒），已禁止继续拖拽保存。请先修正或重新生成片段。
        </div>
      )}

      {/* Timeline */}
      <div className={reviewMode ? "space-y-2" : ""}>
        {reviewMode && <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
          <div>
            <p className="text-xs font-black text-[#14241B]">证据时间线</p>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {reviewMode && reviewFocus === "model" ? "人工边界作为参考底稿；模型候选请在上方模型工作区复核。" : reviewMode ? "当前播放头与人工边界队列联动。" : "已保存的盘、局、分与事件。"}
            </p>
          </div>
          {reviewMode && <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${reviewFocus === "model" ? "bg-violet-50 text-violet-700" : "bg-amber-50 text-amber-700"}`}>{reviewFocus === "model" ? "人工边界 · 参考" : "人工边界 · 编辑"}</span>}
        </div>}
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

function formatGeneratedAt(value: string | null): string {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { dateStyle: "short", timeStyle: "short" });
}

function formatSegmentationStatus(status: string): string {
  return {
    running: "切分中",
    low_evidence: "证据不足",
    input_unavailable: "输入不可用",
    sync_unavailable: "同步不可用",
    model_unavailable: "模型不可用",
    inference_failed: "推理失败",
    failed: "切分失败",
    canceled: "已取消",
    interrupted: "已中断",
  }[status] ?? status;
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

function ReadOnlyModelSegmentRow({
  segment,
  active,
  onClick,
}: {
  segment: CaptureSegmentSummary;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`mb-1 flex w-full items-center gap-2 rounded-lg border px-2 py-1.5 text-left text-sm transition ${active ? "border-[#2F80ED] bg-[#EFF6FF] ring-1 ring-[#2F80ED]/30" : "border-transparent hover:bg-slate-50"}`}
      onClick={onClick}
      title="模型自动结果为只读；如需 QA 复核请使用内部 boundary-review 模式"
    >
      <span className="flex-1 truncate text-xs font-medium text-[#14241B]">{segment.label}</span>
      <span className="shrink-0 text-[10px] tabular-nums text-slate-400">
        {formatMs(segment.effective_start_ms ?? segment.start_ms)}→{segment.effective_end_ms != null ? formatMs(segment.effective_end_ms) : "?"}
      </span>
    </button>
  );
}

function ReviewMetric({ label, value, suffix = "", tone = "default" }: { label: string; value: number | string; suffix?: string; tone?: "default" | "pending" | "confirmed" | "corrected" | "excluded" | "model" }) {
  const colors = {
    default: "text-[#14241B]",
    pending: "text-[#D97706]",
    confirmed: "text-[#168A34]",
    corrected: "text-[#2563EB]",
    excluded: "text-[#DC2626]",
    model: "text-violet-700",
  };
  return (
    <div className="rounded-xl bg-white/80 px-3 py-2 text-center">
      <div className={`text-lg font-black tabular-nums ${colors[tone]}`}>{value}{suffix && <span className="ml-0.5 text-sm">{suffix}</span>}</div>
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

function ModelCandidateReviewPanel({
  summary,
  activeCandidate,
  draft,
  currentTimeMs,
  saving,
  error,
  onSelect,
  onPlay,
  onSetStart,
  onSetEnd,
  onAccept,
  onCorrect,
  onReject,
}: {
  summary: MatchStateCandidateReviewSummary;
  activeCandidate: MatchStateCandidateSegment | null;
  draft: BoundaryDraft;
  currentTimeMs: number;
  saving: boolean;
  error: string | null;
  onSelect: (candidate: MatchStateCandidateSegment) => void;
  onPlay: (candidate: MatchStateCandidateSegment) => void;
  onSetStart: () => void;
  onSetEnd: () => void;
  onAccept: () => void;
  onCorrect: () => void;
  onReject: () => void;
}) {
  if (summary.status === "unavailable") {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500" data-testid="model-candidate-unavailable">
        <span className="font-bold text-slate-700">模型候选不可用</span>（{summary.reason ?? "无可用 artifact"}），现有人工复核流程仍可正常使用。
      </div>
    );
  }
  const pending = summary.candidates.filter((candidate) => candidate.status === "unreviewed").length;
  const start = draft.startMs ?? activeCandidate?.start_ms ?? 0;
  const end = draft.endMs ?? activeCandidate?.end_ms ?? start;
  const alreadyReviewed = activeCandidate ? activeCandidate.status !== "unreviewed" : true;
  return (
    <div className="rounded-2xl border border-violet-200 bg-violet-50/60 p-4" data-testid="model-candidate-review">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-black text-violet-900">模型候选回合</h3>
          <p className="mt-0.5 text-[11px] text-violet-700">
            {summary.model?.model_version ?? "unknown model"} · {summary.candidates.length} 条 · 待复核 {pending} · unknown {((summary.unknown_rate ?? 0) * 100).toFixed(1)}%
          </p>
        </div>
        <span className="rounded-full bg-white px-2 py-1 text-[10px] font-bold text-violet-700">revision {summary.revision}</span>
      </div>
      <div className="mt-3 flex max-h-28 flex-wrap gap-1 overflow-y-auto">
        {summary.candidates.map((candidate) => (
          <button
            key={candidate.candidate_id}
            type="button"
            onClick={() => onSelect(candidate)}
            className={`rounded-lg border px-2 py-1 text-[10px] font-bold ${activeCandidate?.candidate_id === candidate.candidate_id ? "border-violet-500 bg-white text-violet-900" : "border-violet-100 bg-violet-100/60 text-violet-600"}`}
            title={`${formatPreciseMs(candidate.start_ms)} → ${formatPreciseMs(candidate.end_ms)}，置信度 ${(candidate.confidence * 100).toFixed(1)}%`}
          >
            #{candidate.segment_index} · {candidate.status === "unreviewed" ? "待复核" : candidate.status}
          </button>
        ))}
      </div>
      {activeCandidate && (
        <div className="mt-3 rounded-xl border border-violet-100 bg-white p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-bold text-slate-700">候选 #{activeCandidate.segment_index}：{formatPreciseMs(start)} → {formatPreciseMs(end)}</span>
            <span className="text-slate-500">置信度 {(activeCandidate.confidence * 100).toFixed(1)}% · 播放头 {formatPreciseMs(currentTimeMs)}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button className="quiet-button px-3 py-1.5 text-xs" type="button" onClick={() => onPlay(activeCandidate)} title="从候选起点播放，到候选终点自动暂停"><Play size={13} className="mr-1 inline" />播放候选回合</button>
            <button className="quiet-button px-3 py-1.5 text-xs" type="button" disabled={saving || alreadyReviewed} onClick={onSetStart}>当前帧设开始</button>
            <button className="quiet-button px-3 py-1.5 text-xs" type="button" disabled={saving || alreadyReviewed} onClick={onSetEnd}>当前帧设结束</button>
            <button className="rounded-lg bg-[#168A34] px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40" type="button" disabled={saving || alreadyReviewed} onClick={onAccept}>接受原边界</button>
            <button className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40" type="button" disabled={saving || alreadyReviewed || (draft.startMs == null && draft.endMs == null)} onClick={onCorrect}>保存修正</button>
            <button className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-bold text-red-600 disabled:opacity-40" type="button" disabled={saving || alreadyReviewed} onClick={onReject}>拒绝候选</button>
          </div>
          {alreadyReviewed && <p className="mt-2 text-[11px] font-bold text-slate-500">该候选已复核：{activeCandidate.status}，决定和 provenance 已保留。</p>}
          {error && <p className="mt-2 text-[11px] font-bold text-red-600">{error}</p>}
        </div>
      )}
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
