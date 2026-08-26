import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Check, ChevronRight, Lock, Plus, RotateCcw, Save, Trash2, X } from "lucide-react";
import type { CaptureSegmentSummary, CaptureTakeSummary } from "../types/report";
import type { NavigateFn } from "../app/navigationTypes";
import {
  AnalysisApiError,
  createScoringCalibrationAnnotation,
  createScoringCalibrationPackage,
  createScoringCalibrationRevision,
  decideScoringCalibrationCandidate,
  getCaptureTake,
  getScoringCalibrationPackage,
  getVideoStreamUrl,
  listScoringCalibrationPackages,
  listSegments,
  lockScoringCalibrationPackage,
  revokeScoringCalibrationAnnotation,
  reviewScoringCalibrationPackage,
  updateScoringCalibrationAnnotation,
} from "../services/analysisClient";
import { SegmentVideoPlayer, type SegmentVideoPlayerHandle } from "../components/SegmentVideoPlayer";
import { ScoringCalibrationTimeline } from "../components/ScoringCalibrationTimeline";
import type {
  AnnotationDecision,
  AnnotationPackageCreateRequest,
  AnnotationUpsertRequest,
  LandingStatus,
  LandingZone,
  OpportunityStatus,
  ScoringCalibrationAnnotation,
  ScoringCalibrationCandidate,
  ScoringCalibrationPackage,
  ShotOutcome,
  ShotStage,
} from "../types/scoringCalibrationAnnotation";

interface AnnotationFormState {
  event_ms: number;
  evidence_start_ms: number;
  evidence_end_ms: number;
  video_id: string;
  rally_segment_id: string;
  player_id: string;
  stage: ShotStage;
  opportunity_status: OpportunityStatus;
  outcome: ShotOutcome;
  landing_status: LandingStatus;
  landing_zone: LandingZone;
  confidence: string;
  note: string;
  candidate_id: string;
  decision: AnnotationDecision;
}

type QueueMode = "sampled" | "all";
type QuickActionKind = "serveInPlay" | "serveFailed" | "returnInPlay" | "returnUnobservable";

interface RallyProgress {
  serve: ScoringCalibrationAnnotation | undefined;
  return: ScoringCalibrationAnnotation | undefined;
  skipped: boolean;
  complete: boolean;
}

const EMPTY_FORM: AnnotationFormState = {
  event_ms: 0,
  evidence_start_ms: 0,
  evidence_end_ms: 500,
  video_id: "",
  rally_segment_id: "",
  player_id: "",
  stage: "unknown",
  opportunity_status: "eligible",
  outcome: "unknown",
  landing_status: "unobservable",
  landing_zone: "unknown",
  confidence: "",
  note: "",
  candidate_id: "",
  decision: "accepted",
};

export function ScoringCalibrationWorkbenchPage({
  fieldSessionId,
  takeId,
  onNavigate,
}: {
  fieldSessionId: string;
  takeId: string;
  onNavigate: NavigateFn;
}) {
  const [take, setTake] = useState<CaptureTakeSummary | null>(null);
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const [packageList, setPackageList] = useState<ScoringCalibrationPackage[]>([]);
  const [currentPackage, setCurrentPackage] = useState<ScoringCalibrationPackage | null>(null);
  const [form, setForm] = useState<AnnotationFormState>(EMPTY_FORM);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "unreviewed" | "uncertain" | "warning">("all");
  const [queueMode, setQueueMode] = useState<QueueMode>("sampled");
  const [activeRallyId, setActiveRallyId] = useState<string | null>(null);
  const [skippedRallyIds, setSkippedRallyIds] = useState<Set<string>>(new Set());
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [quickSaving, setQuickSaving] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  const [activeVideoIndex, setActiveVideoIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const playerRef = useRef<SegmentVideoPlayerHandle>(null);

  const trackOptions = useMemo(
    () => (take?.video_ids ?? []).map((id, index) => ({
      label: (take?.video_ids?.length ?? 0) > 1 ? `机位${index + 1}` : "原视频",
      url: getVideoStreamUrl(id) ?? "",
    })),
    [take?.video_ids],
  );
  const activeVideoId = take?.video_ids?.[activeVideoIndex] ?? take?.video_ids?.[0] ?? "";
  const activeVideoUrl = trackOptions[activeVideoIndex]?.url ?? trackOptions[0]?.url ?? "";
  const rallySegments = useMemo(
    () => segments
      .filter((segment) => segment.segment_type === "rally" && segment.edit_status !== "superseded")
      .sort((a, b) => (a.effective_start_ms ?? a.start_ms) - (b.effective_start_ms ?? b.start_ms)),
    [segments],
  );
  const queueRallies = useMemo(
    () => queueMode === "all" ? rallySegments : sampleRallySegments(rallySegments, 12),
    [queueMode, rallySegments],
  );
  const activeRally = queueRallies.find((rally) => rally.id === activeRallyId) ?? queueRallies[0];
  const progressByRally = useMemo(() => {
    const annotations = currentPackage?.annotations ?? [];
    return new Map(queueRallies.map((rally) => {
      const rallyAnnotations = annotations.filter((annotation) => annotation.rally_segment_id === rally.id && !annotation.revoked);
      const serve = rallyAnnotations.find((annotation) => annotation.stage === "serve");
      const returnAnnotation = rallyAnnotations.find((annotation) => annotation.stage === "return");
      const complete = skippedRallyIds.has(rally.id) || Boolean(serve && (serve.outcome !== "in_play" || returnAnnotation));
      return [rally.id, { serve, return: returnAnnotation, skipped: skippedRallyIds.has(rally.id), complete } satisfies RallyProgress];
    }));
  }, [currentPackage?.annotations, queueRallies, skippedRallyIds]);
  const completedRallyCount = Array.from(progressByRally.values()).filter((item) => item.complete).length;
  const skippedRallyCount = Array.from(progressByRally.values()).filter((item) => item.skipped).length;
  const activeRallyIndex = activeRally ? queueRallies.findIndex((rally) => rally.id === activeRally.id) : -1;
  const activeRallyCandidates = useMemo(() => {
    if (!activeRally) return currentPackage?.candidates ?? [];
    const start = activeRally.effective_start_ms ?? activeRally.start_ms;
    const end = activeRally.effective_end_ms ?? activeRally.end_ms ?? start + 1;
    return (currentPackage?.candidates ?? []).filter((candidate) => candidate.rally_id === activeRally.id || (candidate.timestamp_ms >= start && candidate.timestamp_ms <= end));
  }, [activeRally, currentPackage?.candidates]);
  const timelineDurationMs = useMemo(() => Math.max(
    1000,
    take?.duration_ms ?? 0,
    durationMs,
    ...segments.map((segment) => segment.effective_end_ms ?? segment.end_ms ?? 0),
  ), [durationMs, segments, take?.duration_ms]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [takeResult, segmentResult, packages] = await Promise.all([
        getCaptureTake(takeId),
        listSegments(takeId).catch(() => []),
        listScoringCalibrationPackages(takeId),
      ]);
      setTake(takeResult);
      setSegments(segmentResult);
      setPackageList(packages);
      const latest = packages[0];
      setCurrentPackage(latest ? await getScoringCalibrationPackage(latest.id) : null);
    } catch (error) {
      setLoadError(formatError(error));
    } finally {
      setLoading(false);
    }
  }, [takeId]);

  useEffect(() => {
    // Load external CaptureTake/package data when the route changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes async API results.
    void loadData();
  }, [loadData]);

  const focusRally = useCallback((rally: CaptureSegmentSummary, resetForm = true) => {
    const start = rally.effective_start_ms ?? rally.start_ms;
    setActiveRallyId(rally.id);
    setCurrentTimeMs(start);
    playerRef.current?.seekToTakeTime(start);
    if (resetForm) {
      setSelectedAnnotationId(null);
      setSelectedCandidateId(null);
      setAdvancedOpen(false);
      setForm({ ...EMPTY_FORM, event_ms: start, evidence_start_ms: start, evidence_end_ms: Math.max(start + 500, rally.effective_end_ms ?? rally.end_ms ?? start + 500), video_id: activeVideoId, rally_segment_id: rally.id });
    }
  }, [activeVideoId]);

  useEffect(() => {
    if (queueRallies.length === 0) return;
    if (!activeRallyId || !queueRallies.some((rally) => rally.id === activeRallyId)) {
      // Keep the quick queue anchored to its first sample after loading or mode changes.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- synchronizes the selected rally with the derived queue.
      focusRally(queueRallies[0]);
    }
  }, [activeRallyId, focusRally, queueRallies]);

  const setPackage = (next: ScoringCalibrationPackage) => {
    setCurrentPackage(next);
    setPackageList((current) => {
      const without = current.filter((item) => item.id !== next.id);
      return [next, ...without].sort((a, b) => b.revision - a.revision);
    });
  };

  const createPackage = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const payload: AnnotationPackageCreateRequest = { annotator: "本地标注者" };
      setPackage(await createScoringCalibrationPackage(takeId, payload));
      setMessage("已创建 draft 标注包");
    } catch (error) {
      setMessage(formatError(error));
    } finally {
      setSaving(false);
    }
  };

  const selectAnnotation = (annotation: ScoringCalibrationAnnotation) => {
    setSelectedAnnotationId(annotation.id);
    setSelectedCandidateId(null);
    setForm(annotationToForm(annotation));
    setAdvancedOpen(true);
    if (annotation.rally_segment_id && queueRallies.some((rally) => rally.id === annotation.rally_segment_id)) setActiveRallyId(annotation.rally_segment_id);
    setCurrentTimeMs(annotation.evidence_start_ms);
    playerRef.current?.seekToTakeTime(annotation.evidence_start_ms);
  };

  const selectCandidate = (candidate: ScoringCalibrationCandidate) => {
    setSelectedCandidateId(candidate.candidate_id);
    setSelectedAnnotationId(null);
    setAdvancedOpen(true);
    const candidateRally = queueRallies.find((rally) => rally.id === candidate.rally_id || isWithinSegment(candidate.timestamp_ms, rally));
    if (candidateRally) setActiveRallyId(candidateRally.id);
    const eventMs = candidate.timestamp_ms;
    setForm({
      ...EMPTY_FORM,
      event_ms: eventMs,
      evidence_start_ms: Math.max(0, candidate.start_ms ?? eventMs - 500),
      evidence_end_ms: candidate.end_ms ?? eventMs + 700,
      video_id: activeVideoId,
      rally_segment_id: candidateRally?.id ?? "",
      player_id: candidate.player_id ?? "",
      stage: candidate.candidate_type === "serve" ? "serve" : "unknown",
      candidate_id: candidate.candidate_id,
      decision: "accepted",
    });
    setCurrentTimeMs(Math.max(0, candidate.start_ms ?? eventMs - 500));
    playerRef.current?.seekToTakeTime(Math.max(0, candidate.start_ms ?? eventMs - 500));
  };

  const startManualAnnotation = () => {
    const eventMs = Math.round(currentTimeMs);
    setSelectedAnnotationId(null);
    setSelectedCandidateId(null);
    setAdvancedOpen(true);
    setForm({
      ...EMPTY_FORM,
      event_ms: eventMs,
      evidence_start_ms: Math.max(0, eventMs - 500),
      evidence_end_ms: eventMs + 700,
      video_id: activeVideoId,
      rally_segment_id: activeRally?.id ?? "",
    });
  };

  const nextRally = useCallback((fromId = activeRally?.id) => {
    const startIndex = Math.max(-1, queueRallies.findIndex((rally) => rally.id === fromId));
    return queueRallies.slice(startIndex + 1).find((rally) => !progressByRally.get(rally.id)?.complete);
  }, [activeRally?.id, progressByRally, queueRallies]);

  const saveQuickAction = async (action: QuickActionKind) => {
    if (!currentPackage || currentPackage.status === "locked" || !activeRally || quickSaving) return;
    setQuickSaving(true);
    setSaving(true);
    setMessage(null);
    const rallyStart = activeRally.effective_start_ms ?? activeRally.start_ms;
    const rallyEnd = activeRally.effective_end_ms ?? activeRally.end_ms ?? Math.max(rallyStart + 500, rallyStart + 1);
    const stage: ShotStage = action.startsWith("serve") ? "serve" : "return";
    const existing = (currentPackage.annotations ?? []).find((annotation) => !annotation.revoked && annotation.rally_segment_id === activeRally.id && annotation.stage === stage);
    const matchingCandidate = activeRallyCandidates.find((candidate) => (stage === "serve" ? candidate.candidate_type === "serve" : candidate.candidate_type !== "serve"));
    const eventMs = Math.min(rallyEnd, Math.max(rallyStart, matchingCandidate?.timestamp_ms ?? currentTimeMs));
    const evidenceStart = Math.max(rallyStart, eventMs - 500);
    const evidenceEnd = Math.min(rallyEnd, Math.max(eventMs + 1, eventMs + 700));
    const common = {
      event_ms: eventMs,
      evidence_start_ms: evidenceStart,
      evidence_end_ms: Math.max(evidenceStart + 1, evidenceEnd),
      video_id: activeVideoId || undefined,
      rally_segment_id: activeRally.id,
      candidate_id: matchingCandidate?.candidate_id,
      decision: "accepted" as AnnotationDecision,
      landing_zone: "unknown" as LandingZone,
      confidence: matchingCandidate?.confidence ?? undefined,
    };
    const payload: AnnotationUpsertRequest = action === "serveInPlay"
      ? { ...common, stage: "serve", opportunity_status: "eligible", outcome: "in_play", landing_status: "unobservable" }
      : action === "serveFailed"
        ? { ...common, stage: "serve", opportunity_status: "eligible", outcome: "unknown", landing_status: "not_applicable", note: "快速校准：发球失败，暂未细分下网/出界" }
        : action === "returnInPlay"
          ? { ...common, stage: "return", opportunity_status: "eligible", outcome: "in_play", landing_status: "unobservable" }
          : { ...common, stage: "return", opportunity_status: "unobservable", outcome: "unknown", landing_status: "unobservable" };
    try {
      let next = existing
        ? await updateScoringCalibrationAnnotation(currentPackage.id, existing.id, payload)
        : await createScoringCalibrationAnnotation(currentPackage.id, payload);
      const linked = payload.candidate_id ? next.annotations.find((annotation) => annotation.candidate_id === payload.candidate_id) : undefined;
      if (payload.candidate_id && linked) {
        next = await decideScoringCalibrationCandidate(next.id, payload.candidate_id, { decision: "accepted", annotation_id: linked.id });
      }
      setPackage(next);
      setSelectedAnnotationId(next.annotations.find((annotation) => annotation.rally_segment_id === activeRally.id && annotation.stage === stage)?.id ?? existing?.id ?? null);
      setSelectedCandidateId(null);
      setMessage(action === "serveFailed" ? "已记录发球失败（未细分下网/出界）" : "快速事实已保存");
      const destination = nextRally(activeRally.id);
      if (destination) focusRally(destination);
    } catch (error) {
      setMessage(formatError(error));
    } finally {
      setQuickSaving(false);
      setSaving(false);
    }
  };

  const skipCurrentRally = () => {
    if (!activeRally || currentPackage?.status === "locked") return;
    setSkippedRallyIds((current) => new Set(current).add(activeRally.id));
    const destination = nextRally(activeRally.id);
    if (destination) focusRally(destination);
    setMessage("已跳过当前回合，不会写入人工事实");
  };

  const saveAnnotation = async (advanceToNext = false) => {
    if (!currentPackage || currentPackage.status === "locked") return;
    const validationMessage = validateForm(form);
    if (validationMessage) {
      setMessage(validationMessage);
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const payload: AnnotationUpsertRequest = {
        event_ms: form.event_ms,
        evidence_start_ms: form.evidence_start_ms,
        evidence_end_ms: form.evidence_end_ms,
        video_id: form.video_id || activeVideoId || undefined,
        rally_segment_id: form.rally_segment_id || undefined,
        player_id: form.player_id || undefined,
        stage: form.stage,
        opportunity_status: form.opportunity_status,
        outcome: form.outcome,
        landing_status: form.landing_status,
        landing_zone: form.landing_zone,
        confidence: form.confidence ? Number(form.confidence) : undefined,
        note: form.note || undefined,
        candidate_id: form.candidate_id || undefined,
        decision: form.decision,
      };
      let next = selectedAnnotationId
        ? await updateScoringCalibrationAnnotation(currentPackage.id, selectedAnnotationId, payload)
        : await createScoringCalibrationAnnotation(currentPackage.id, payload);
      const linked = next.annotations.find((annotation) => annotation.candidate_id === form.candidate_id);
      if (form.candidate_id && linked) {
        next = await decideScoringCalibrationCandidate(next.id, form.candidate_id, {
          decision: form.decision,
          annotation_id: linked.id,
        });
      }
      setPackage(next);
      setSelectedAnnotationId(linked?.id ?? (selectedAnnotationId ?? null));
      setMessage("标注已保存");
      if (advanceToNext) {
        const nextAnnotation = next.annotations
          .filter((annotation) => annotation.id !== linked?.id && annotation.decision === "unreviewed")
          .sort((a, b) => a.event_ms - b.event_ms)[0];
        if (nextAnnotation) {
          selectAnnotation(nextAnnotation);
        } else {
          const nextCandidate = next.candidates.find((candidate) => candidate.decision === "unreviewed");
          if (nextCandidate) selectCandidate(nextCandidate);
          else startManualAnnotation();
        }
      }
    } catch (error) {
      setMessage(formatError(error));
    } finally {
      setSaving(false);
    }
  };

  const removeAnnotation = async () => {
    if (!currentPackage || !selectedAnnotationId || currentPackage.status === "locked") return;
    setSaving(true);
    try {
      setPackage(await revokeScoringCalibrationAnnotation(currentPackage.id, selectedAnnotationId));
      setSelectedAnnotationId(null);
      setForm(EMPTY_FORM);
      setMessage("标注已撤销");
    } catch (error) {
      setMessage(formatError(error));
    } finally {
      setSaving(false);
    }
  };

  const decideCandidate = async (candidate: ScoringCalibrationCandidate, decision: AnnotationDecision) => {
    if (!currentPackage || currentPackage.status === "locked") return;
    try {
      setPackage(await decideScoringCalibrationCandidate(currentPackage.id, candidate.candidate_id, { decision }));
      setMessage(decision === "rejected" ? "候选已拒绝" : "候选决定已保存");
    } catch (error) {
      setMessage(formatError(error));
    }
  };

  const markReviewed = async () => {
    if (!currentPackage || currentPackage.status === "locked") return;
    setSaving(true);
    try {
      setPackage(await reviewScoringCalibrationPackage(currentPackage.id));
      setMessage("标注包已进入 reviewed");
    } catch (error) {
      setMessage(formatError(error));
    } finally {
      setSaving(false);
    }
  };

  const lockPackage = async () => {
    if (!currentPackage || currentPackage.status === "locked") return;
    setSaving(true);
    try {
      setPackage(await lockScoringCalibrationPackage(currentPackage.id));
      setMessage("Gold Set 已锁定");
    } catch (error) {
      setMessage(formatError(error));
    } finally {
      setSaving(false);
    }
  };

  const createRevision = async () => {
    if (!currentPackage || currentPackage.status !== "locked") return;
    setSaving(true);
    try {
      setPackage(await createScoringCalibrationRevision(currentPackage.id, { annotator: "本地标注者" }));
      setSelectedAnnotationId(null);
      setForm(EMPTY_FORM);
      setMessage("已创建新的 draft revision");
    } catch (error) {
      setMessage(formatError(error));
    } finally {
      setSaving(false);
    }
  };

  const visibleAnnotations = useMemo(() => {
    const annotations = currentPackage?.annotations ?? [];
    if (filter === "unreviewed") return annotations.filter((item) => item.decision === "unreviewed");
    if (filter === "uncertain") return annotations.filter((item) => item.outcome === "unknown" || item.opportunity_status === "unobservable");
    if (filter === "warning") {
      const warningIds = new Set((currentPackage?.validation_issues ?? []).filter((issue) => issue.severity === "warning").map((issue) => issue.annotation_id));
      return annotations.filter((item) => warningIds.has(item.id));
    }
    return annotations;
  }, [currentPackage, filter]);

  if (loading) return <div className="p-8 text-sm text-slate-400">正在加载评分校准工作台…</div>;
  if (loadError || !take) {
    return <div className="mx-auto max-w-4xl p-8 text-center text-sm text-[#B91C1C]">{loadError ?? "CaptureTake 不存在"}</div>;
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 px-4 py-6">
      <div className="flex flex-wrap items-center gap-3">
        <button className="inline-flex items-center gap-1 text-sm text-[#2F80ED]" onClick={() => onNavigate(`/capture/${fieldSessionId}/takes/${takeId}/segments`)}>
          <ArrowLeft size={16} /> 返回片段管理
        </button>
        <h1 className="text-lg font-bold text-[#14241B]">评分校准标注工作台</h1>
        {currentPackage && <StatusBadge status={currentPackage.status} revision={currentPackage.revision} />}
        {packageList.length > 1 && (
          <select
            className="field-input w-auto min-w-28 text-xs"
            value={currentPackage?.id ?? ""}
            onChange={(event) => {
              void getScoringCalibrationPackage(event.target.value).then(setPackage).catch((error) => setMessage(formatError(error)));
            }}
          >
            {packageList.map((item) => <option key={item.id} value={item.id}>revision {item.revision}</option>)}
          </select>
        )}
        <div className="ml-auto flex items-center gap-2">
          {message && <span className="max-w-[320px] text-xs text-slate-500">{message}</span>}
          {currentPackage?.status === "locked" ? (
            <button className="inline-flex items-center gap-1 rounded-lg border border-[#2F80ED] px-3 py-2 text-xs font-bold text-[#2F80ED]" onClick={() => void createRevision()} disabled={saving}>
              <RotateCcw size={14} /> 创建修订
            </button>
          ) : currentPackage ? (
            <>
              <button className="inline-flex items-center gap-1 rounded-lg border border-[#64748B] px-3 py-2 text-xs font-bold text-[#475569]" onClick={() => void markReviewed()} disabled={saving}>
                <Check size={14} /> 标记 reviewed
              </button>
              <button className="green-button inline-flex items-center gap-1 px-3 py-2 text-xs" onClick={() => void lockPackage()} disabled={saving}>
                <Lock size={14} /> 锁定 Gold Set
              </button>
            </>
          ) : null}
        </div>
      </div>

      {!currentPackage ? (
        <div className="rounded-2xl border border-dashed border-[#B8CDB5] bg-white p-10 text-center">
          <h2 className="text-base font-bold text-[#14241B]">还没有评分校准标注包</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-slate-500">请使用已注册的本地比赛视频创建一个 draft。PB Vision 分享链接不会直接作为系统视频源。</p>
          {(take.video_ids?.length ?? 0) === 0 ? (
            <p className="mt-4 text-sm font-bold text-[#B91C1C]">当前 CaptureTake 没有可播放视频，请先完成视频注册。</p>
          ) : (
            <button className="green-button mt-5 inline-flex items-center gap-2 px-4 py-2 text-sm" onClick={() => void createPackage()} disabled={saving}>
              <Plus size={16} /> 创建 draft 标注包
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="space-y-4">
              {activeVideoUrl ? (
                <SegmentVideoPlayer
                  ref={playerRef}
                  videoUrl={activeVideoUrl}
                  trackOptions={trackOptions}
                  onTrackChange={(index) => { setActiveVideoIndex(index); setForm((current) => ({ ...current, video_id: take.video_ids?.[index] ?? "" })); }}
                  onTimeUpdate={setCurrentTimeMs}
                  onDurationReady={setDurationMs}
                />
              ) : (
                <div className="grid aspect-video place-items-center rounded-2xl border border-[#FECACA] bg-[#FEF2F2] text-sm text-[#B91C1C]">暂无可用视频回放</div>
              )}
              <ScoringCalibrationTimeline
                segments={queueRallies}
                annotations={currentPackage.annotations}
                candidates={currentPackage.candidates}
                totalDurationMs={timelineDurationMs}
                currentTimeMs={currentTimeMs}
                selectedAnnotationId={selectedAnnotationId}
                selectedCandidateId={selectedCandidateId}
                onSeek={(ms) => { setCurrentTimeMs(ms); playerRef.current?.seekToTakeTime(ms); }}
                onSelectAnnotation={selectAnnotation}
                onSelectCandidate={selectCandidate}
              />
            </div>

            <div className="space-y-3">
              <QuickSamplingPanel
                rallies={queueRallies}
                activeRallyId={activeRally?.id ?? null}
                activeRallyIndex={activeRallyIndex}
                queueMode={queueMode}
                completedCount={completedRallyCount}
                skippedCount={skippedRallyCount}
                progressByRally={progressByRally}
                locked={currentPackage.status === "locked"}
                quickSaving={quickSaving}
                onQueueModeChange={setQueueMode}
                onFocusRally={(rally) => focusRally(rally)}
                onQuickAction={(action) => void saveQuickAction(action)}
                onSkip={skipCurrentRally}
                onNext={() => { const destination = nextRally(); if (destination) focusRally(destination); }}
              />
              <div className="rounded-2xl border border-[#B8CDB5] bg-[#F6FBF3] p-4">
                <div className="flex items-center gap-2">
                  <h2 className="mr-auto text-sm font-bold text-[#14241B]">高级信息</h2>
                  <button type="button" className="rounded-lg border border-[#B8CDB5] bg-white px-3 py-1.5 text-[11px] font-bold text-[#2F80ED]" onClick={() => setAdvancedOpen((current) => !current)}>
                    {advancedOpen ? "收起详细字段" : "补充字段"}
                  </button>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">第一批校准只需处理当前回合的最小事实；击球人、落点、置信度和备注可在这里补充，不是每条都必填。</p>
              </div>
              {advancedOpen && (
                <AnnotationForm
                  form={form}
                  disabled={currentPackage.status === "locked" || saving}
                  rallies={rallySegments}
                  onChange={(next) => setForm((current) => ({ ...current, ...next }))}
                  onSave={() => void saveAnnotation()}
                  onSaveNext={() => void saveAnnotation(true)}
                  onNew={startManualAnnotation}
                  onRemove={() => void removeAnnotation()}
                  hasSelection={Boolean(selectedAnnotationId || selectedCandidateId)}
                />
              )}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h2 className="mr-auto text-sm font-bold text-[#14241B]">人工标注队列</h2>
                {(["all", "unreviewed", "uncertain", "warning"] as const).map((value) => (
                  <button key={value} className={`rounded-full px-3 py-1 text-[11px] font-bold ${filter === value ? "bg-[#2F80ED] text-white" : "bg-slate-100 text-slate-500"}`} onClick={() => setFilter(value)}>
                    {{ all: "全部", unreviewed: "未复核", uncertain: "不确定", warning: "有 warning" }[value]}
                  </button>
                ))}
              </div>
              {visibleAnnotations.length === 0 ? (
                <p className="py-6 text-center text-sm text-slate-400">当前筛选没有人工标注</p>
              ) : (
                <div className="space-y-1">
                  {visibleAnnotations.map((annotation) => (
                    <button key={annotation.id} type="button" className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs ${selectedAnnotationId === annotation.id ? "border-[#2F80ED] bg-[#EFF6FF]" : "border-transparent hover:bg-slate-50"}`} onClick={() => selectAnnotation(annotation)}>
                      <span className="w-12 tabular-nums text-slate-400">{formatMs(annotation.event_ms)}</span>
                      <span className="font-bold text-[#14241B]">{stageLabel(annotation.stage)}</span>
                      <span className="text-slate-500">{outcomeLabel(annotation.outcome)}</span>
                      <span className="ml-auto rounded-full bg-slate-100 px-2 py-0.5 text-[10px]">{decisionLabel(annotation.decision)}</span>
                      <ChevronRight size={14} className="text-slate-300" />
                    </button>
                  ))}
                </div>
              )}
            </div>
            <QualityCard package={currentPackage} />
          </div>

          <CandidateQueue
            candidates={activeRallyCandidates}
            candidateStatus={currentPackage.candidate_status}
            candidateMessage={currentPackage.candidate_message}
            candidateCoverageWarning={currentPackage.candidate_coverage_warning}
            disabled={currentPackage.status === "locked" || saving}
            onSelect={selectCandidate}
            onDecision={decideCandidate}
          />
        </>
      )}
    </div>
  );
}

function QuickSamplingPanel({
  rallies,
  activeRallyId,
  activeRallyIndex,
  queueMode,
  completedCount,
  skippedCount,
  progressByRally,
  locked,
  quickSaving,
  onQueueModeChange,
  onFocusRally,
  onQuickAction,
  onSkip,
  onNext,
}: {
  rallies: CaptureSegmentSummary[];
  activeRallyId: string | null;
  activeRallyIndex: number;
  queueMode: QueueMode;
  completedCount: number;
  skippedCount: number;
  progressByRally: Map<string, RallyProgress>;
  locked: boolean;
  quickSaving: boolean;
  onQueueModeChange: (mode: QueueMode) => void;
  onFocusRally: (rally: CaptureSegmentSummary) => void;
  onQuickAction: (action: QuickActionKind) => void;
  onSkip: () => void;
  onNext: () => void;
}) {
  const activeRally = rallies.find((rally) => rally.id === activeRallyId) ?? rallies[0];
  const activeProgress = activeRally ? progressByRally.get(activeRally.id) : undefined;
  const disabled = locked || quickSaving || !activeRally;
  return (
    <div className="rounded-2xl border border-[#B8CDB5] bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start gap-3">
        <div className="mr-auto">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold text-[#14241B]">快速校准</h2>
            <span className="rounded-full bg-[#DCFCE7] px-2 py-0.5 text-[10px] font-bold text-[#166534]">默认抽样</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">每个回合只先确认发球和接发的最小事实，不需要逐球填完整场。</p>
        </div>
        <div className="flex rounded-lg bg-slate-100 p-0.5 text-[11px] font-bold">
          <button type="button" className={`rounded-md px-3 py-1.5 ${queueMode === "sampled" ? "bg-white text-[#2F80ED] shadow-sm" : "text-slate-500"}`} onClick={() => onQueueModeChange("sampled")}>抽样 12 个</button>
          <button type="button" className={`rounded-md px-3 py-1.5 ${queueMode === "all" ? "bg-white text-[#2F80ED] shadow-sm" : "text-slate-500"}`} onClick={() => onQueueModeChange("all")}>全部回合</button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span className="font-bold text-[#14241B]">已处理 {completedCount} / {rallies.length}</span>
        <span>待处理 {Math.max(0, rallies.length - completedCount)}</span>
        <span>已跳过 {skippedCount}</span>
        {activeRally && <span>当前第 {activeRallyIndex + 1} 条 · {formatMs(activeRally.effective_start_ms ?? activeRally.start_ms)}–{formatMs(activeRally.effective_end_ms ?? activeRally.end_ms ?? activeRally.start_ms)}</span>}
      </div>
      {rallies.length === 0 ? (
        <p className="mt-4 rounded-lg bg-slate-50 p-4 text-center text-sm text-slate-400">当前 Take 没有有效 rally 片段；仍可通过高级信息在视频当前位置新建人工事实。</p>
      ) : (
        <>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {rallies.map((rally) => {
              const progress = progressByRally.get(rally.id);
              return (
                <button key={rally.id} type="button" className={`min-w-[104px] rounded-lg border px-2.5 py-2 text-left text-[11px] ${activeRally?.id === rally.id ? "border-[#2F80ED] bg-[#EFF6FF]" : "border-[#E5E7EB] bg-white hover:border-[#B8CDB5]"}`} onClick={() => onFocusRally(rally)}>
                  <div className="flex items-center gap-1 font-bold text-[#14241B]"><span>{rally.label || `回合 ${rally.ordinal}`}</span><span className="ml-auto text-slate-400">{progress?.skipped ? "跳过" : progress?.complete ? "完成" : "待处理"}</span></div>
                  <div className="mt-1 tabular-nums text-slate-400">{formatMs(rally.effective_start_ms ?? rally.start_ms)}–{formatMs(rally.effective_end_ms ?? rally.end_ms ?? rally.start_ms)}</div>
                  <div className="mt-1 text-[10px] text-slate-500">发球 {progress?.serve ? "✓" : "—"} · 接发 {progress?.return ? "✓" : "—"}</div>
                </button>
              );
            })}
          </div>
          <div className="mt-3 rounded-xl border border-[#E5E7EB] bg-[#FAFCF9] p-3">
            <div className="flex items-center gap-2 text-xs"><span className="font-bold text-[#14241B]">当前回合：{activeRally?.label || `回合 ${(activeRally?.ordinal ?? 0)}`}</span><span className="text-slate-400">先看这一小段，再点结果</span></div>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <QuickActionButton label="发球入界" onClick={() => onQuickAction("serveInPlay")} disabled={disabled} tone="green" />
              <QuickActionButton label="发球失败" onClick={() => onQuickAction("serveFailed")} disabled={disabled} tone="orange" />
              <QuickActionButton label="接发入界" onClick={() => onQuickAction("returnInPlay")} disabled={disabled} tone="blue" />
              <QuickActionButton label="接发不可观察" onClick={() => onQuickAction("returnUnobservable")} disabled={disabled} tone="gray" />
            </div>
            <div className="mt-2 flex gap-2">
              <button type="button" className="flex-1 rounded-lg border border-dashed border-slate-300 py-2 text-xs font-bold text-slate-500 hover:bg-white" onClick={onSkip} disabled={disabled}>跳过当前回合</button>
              <button type="button" className="inline-flex items-center justify-center gap-1 rounded-lg border border-[#2F80ED] px-4 py-2 text-xs font-bold text-[#2F80ED] hover:bg-[#EFF6FF]" onClick={onNext} disabled={locked || quickSaving}><ChevronRight size={14} /> 下一条</button>
            </div>
            {activeProgress?.complete && <p className="mt-2 text-[11px] font-bold text-[#166534]">当前回合已完成，可点击下一条或重新点选修改。</p>}
          </div>
        </>
      )}
    </div>
  );
}

function QuickActionButton({ label, onClick, disabled, tone }: { label: string; onClick: () => void; disabled: boolean; tone: "green" | "orange" | "blue" | "gray" }) {
  const styles = {
    green: "border-[#86EFAC] bg-[#F0FDF4] text-[#166534] hover:bg-[#DCFCE7]",
    orange: "border-[#FED7AA] bg-[#FFF7ED] text-[#9A3412] hover:bg-[#FFEDD5]",
    blue: "border-[#BFDBFE] bg-[#EFF6FF] text-[#1D4ED8] hover:bg-[#DBEAFE]",
    gray: "border-[#CBD5E1] bg-slate-50 text-slate-600 hover:bg-slate-100",
  }[tone];
  return <button type="button" className={`rounded-lg border px-2 py-2.5 text-xs font-bold ${styles}`} onClick={onClick} disabled={disabled}>{label}</button>;
}

function AnnotationForm({
  form,
  disabled,
  rallies,
  onChange,
  onSave,
  onSaveNext,
  onNew,
  onRemove,
  hasSelection,
}: {
  form: AnnotationFormState;
  disabled: boolean;
  rallies: CaptureSegmentSummary[];
  onChange: (next: Partial<AnnotationFormState>) => void;
  onSave: () => void;
  onSaveNext: () => void;
  onNew: () => void;
  onRemove: () => void;
  hasSelection: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="mr-auto text-sm font-bold text-[#14241B]">人工事实</h2>
        <button type="button" className="rounded-lg border border-[#DDE9D6] px-2 py-1 text-[11px] text-slate-500" onClick={onNew} disabled={disabled}>新建</button>
        {hasSelection && <button type="button" className="rounded-lg p-1 text-[#B91C1C] hover:bg-[#FEF2F2]" title="撤销当前标注" onClick={onRemove} disabled={disabled}><Trash2 size={14} /></button>}
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <NumberField label="事件 ms" value={form.event_ms} disabled={disabled} onChange={(value) => onChange({ event_ms: value })} />
        <NumberField label="证据开始" value={form.evidence_start_ms} disabled={disabled} onChange={(value) => onChange({ evidence_start_ms: value })} />
        <NumberField label="证据结束" value={form.evidence_end_ms} disabled={disabled} onChange={(value) => onChange({ evidence_end_ms: value })} />
        <label className="space-y-1"><span className="text-slate-500">回合</span><select className="field-input" value={form.rally_segment_id} disabled={disabled} onChange={(event) => onChange({ rally_segment_id: event.target.value })}><option value="">未关联</option>{rallies.map((rally) => <option key={rally.id} value={rally.id}>{rally.label || `回合 ${rally.ordinal}`}</option>)}</select></label>
        <label className="space-y-1"><span className="text-slate-500">阶段</span><select className="field-input" value={form.stage} disabled={disabled} onChange={(event) => onChange({ stage: event.target.value as ShotStage })}><option value="serve">发球</option><option value="return">接发</option><option value="other">其他</option><option value="unknown">未知</option></select></label>
        <label className="space-y-1"><span className="text-slate-500">击球人</span><input className="field-input" value={form.player_id} disabled={disabled} placeholder="可留空" onChange={(event) => onChange({ player_id: event.target.value })} /></label>
        <label className="space-y-1"><span className="text-slate-500">机会状态</span><select className="field-input" value={form.opportunity_status} disabled={disabled} onChange={(event) => onChange({ opportunity_status: event.target.value as OpportunityStatus })}><option value="eligible">可计入</option><option value="not_applicable">不适用</option><option value="unobservable">不可观察</option></select></label>
        <label className="space-y-1"><span className="text-slate-500">结果</span><select className="field-input" value={form.outcome} disabled={disabled} onChange={(event) => onChange({ outcome: event.target.value as ShotOutcome })}><option value="in_play">入界</option><option value="net">下网</option><option value="out">出界</option><option value="unknown">未知</option></select></label>
        <label className="space-y-1"><span className="text-slate-500">落点状态</span><select className="field-input" value={form.landing_status} disabled={disabled} onChange={(event) => onChange({ landing_status: event.target.value as LandingStatus })}><option value="measured">可测量</option><option value="not_applicable">不适用</option><option value="unobservable">不可观察</option></select></label>
        <label className="space-y-1"><span className="text-slate-500">落点区域</span><select className="field-input" value={form.landing_zone} disabled={disabled} onChange={(event) => onChange({ landing_zone: event.target.value as LandingZone })}><option value="short">短</option><option value="middle">中</option><option value="deep">深</option><option value="unknown">未知</option></select></label>
        <NumberField label="置信度 0-1" value={form.confidence} disabled={disabled} stringValue onChange={(value) => onChange({ confidence: String(value) })} />
        <label className="space-y-1"><span className="text-slate-500">人工决定</span><select className="field-input" value={form.decision} disabled={disabled} onChange={(event) => onChange({ decision: event.target.value as AnnotationDecision })}><option value="accepted">确认</option><option value="corrected">修正</option><option value="rejected">拒绝</option><option value="unreviewed">未复核</option></select></label>
      </div>
      <label className="mt-2 block space-y-1 text-xs"><span className="text-slate-500">备注</span><textarea className="field-input min-h-16 resize-y" value={form.note} disabled={disabled} onChange={(event) => onChange({ note: event.target.value })} placeholder="记录遮挡、边界或判断依据" /></label>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button type="button" className="green-button inline-flex items-center justify-center gap-2 py-2 text-sm" onClick={onSave} disabled={disabled}><Save size={15} /> 保存</button>
        <button type="button" className="inline-flex items-center justify-center gap-1 rounded-lg border border-[#2F80ED] py-2 text-xs font-bold text-[#2F80ED] hover:bg-[#EFF6FF]" onClick={onSaveNext} disabled={disabled}><ChevronRight size={14} /> 保存并下一条</button>
      </div>
      <p className="mt-2 text-[10px] leading-4 text-slate-400">不可观察不会自动视为失败；只有锁定后的 revision 才能作为 Gold Set。</p>
    </div>
  );
}

function CandidateQueue({ candidates, candidateStatus, candidateMessage, candidateCoverageWarning, disabled, onSelect, onDecision }: { candidates: ScoringCalibrationCandidate[]; candidateStatus?: string; candidateMessage?: string | null; candidateCoverageWarning?: string | null; disabled: boolean; onSelect: (candidate: ScoringCalibrationCandidate) => void; onDecision: (candidate: ScoringCalibrationCandidate, decision: AnnotationDecision) => void }) {
  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2"><h2 className="text-sm font-bold text-[#14241B]">当前回合的算法候选</h2><span className="text-[11px] text-slate-400">仅作为定位建议，不能自动成为 Gold Set</span></div>
      {candidateCoverageWarning && <p className="mb-2 rounded-lg bg-[#FFF7ED] px-3 py-2 text-[11px] text-[#9A3412]">覆盖提示：{candidateCoverageWarning}</p>}
      {candidates.length === 0 ? <p className="py-4 text-sm text-slate-400">{candidateMessage ?? (candidateStatus === "unavailable" ? "候选存储不可用" : "当前回合没有候选，可直接使用上方快捷人工校准。")} </p> : <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">{candidates.map((candidate) => <div key={candidate.candidate_id} className="flex items-center gap-2 rounded-lg border border-slate-100 px-3 py-2 text-xs"><button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => onSelect(candidate)}><span className="font-bold text-[#8B5CF6]">{candidate.candidate_type === "serve" ? "发球候选" : "击球候选"}</span><span className="tabular-nums text-slate-500">{formatMs(candidate.timestamp_ms)}</span><span className="truncate text-slate-400">{candidate.artifact_name ?? candidate.candidate_id}</span>{candidate.confidence != null && <span className="text-slate-400">{Math.round(candidate.confidence * 100)}%</span>}</button><button type="button" title="拒绝候选" className="rounded p-1 text-slate-400 hover:bg-[#FEF2F2] hover:text-[#B91C1C]" onClick={() => onDecision(candidate, "rejected")} disabled={disabled}><X size={13} /></button></div>)}</div>}
    </div>
  );
}

function QualityCard({ package: currentPackage }: { package: ScoringCalibrationPackage }) {
  const quality = currentPackage.quality;
  return <div className="rounded-2xl border border-[#DDE9D6] bg-white p-4"><div className="mb-3 flex items-center gap-2"><h2 className="text-sm font-bold text-[#14241B]">质量摘要</h2><span className="ml-auto text-[11px] text-slate-400">revision {currentPackage.revision}</span></div><div className="grid grid-cols-2 gap-2 text-xs">{[["条目", quality.total_count], ["已确认", quality.confirmed_count], ["未知/不可观察", quality.unknown_or_unobservable_count], ["候选未匹配", quality.unmatched_candidate_count], ["冲突", quality.conflict_count], ["证据完整率", `${Math.round(quality.evidence_complete_rate * 100)}%`]].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-slate-50 px-3 py-2"><div className="text-slate-400">{label}</div><div className="mt-1 font-bold text-[#14241B]">{value}</div></div>)}</div>{currentPackage.validation_issues.length > 0 && <div className="mt-3 space-y-1 text-[11px]">{currentPackage.validation_issues.slice(0, 4).map((issue, index) => <div key={`${issue.code}-${index}`} className={issue.severity === "error" ? "text-[#B91C1C]" : "text-[#A16207]"}>{issue.severity === "error" ? "阻塞" : "提示"}：{issue.message}</div>)}</div>}</div>;
}

function StatusBadge({ status, revision }: { status: string; revision: number }) {
  const label = status === "locked" ? "已锁定" : status === "reviewed" ? "已审核" : "草稿";
  return <span className={`rounded-full px-3 py-1 text-[11px] font-bold ${status === "locked" ? "bg-[#DCFCE7] text-[#166534]" : status === "reviewed" ? "bg-[#E0E7FF] text-[#3730A3]" : "bg-[#FEF3C7] text-[#92400E]"}`}>{label} · r{revision}</span>;
}

function NumberField({ label, value, disabled, onChange, stringValue = false }: { label: string; value: number | string; disabled: boolean; onChange: (value: number) => void; stringValue?: boolean }) {
  return <label className="space-y-1"><span className="text-slate-500">{label}</span><input className="field-input" type="number" min={0} step={stringValue ? 0.01 : 1} value={value} disabled={disabled} onChange={(event) => onChange(stringValue ? Number(event.target.value) : Math.max(0, Number(event.target.value)))} /></label>;
}

function annotationToForm(annotation: ScoringCalibrationAnnotation): AnnotationFormState {
  return {
    event_ms: annotation.event_ms,
    evidence_start_ms: annotation.evidence_start_ms,
    evidence_end_ms: annotation.evidence_end_ms,
    video_id: annotation.video_id ?? "",
    rally_segment_id: annotation.rally_segment_id ?? "",
    player_id: annotation.player_id ?? "",
    stage: annotation.stage ?? "unknown",
    opportunity_status: annotation.opportunity_status ?? "eligible",
    outcome: annotation.outcome ?? "unknown",
    landing_status: annotation.landing_status ?? "unobservable",
    landing_zone: annotation.landing_zone ?? "unknown",
    confidence: annotation.confidence == null ? "" : String(annotation.confidence),
    note: annotation.note ?? "",
    candidate_id: annotation.candidate_id ?? "",
    decision: annotation.decision,
  };
}

function formatError(error: unknown): string {
  if (error instanceof AnalysisApiError) return error.backendDetail ?? error.message;
  return error instanceof Error ? error.message : String(error);
}

function formatMs(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function sampleRallySegments(segments: CaptureSegmentSummary[], limit = 12): CaptureSegmentSummary[] {
  if (segments.length <= limit) return segments;
  const selected = new Set<number>();
  for (let index = 0; index < limit; index += 1) {
    selected.add(Math.round((index * (segments.length - 1)) / (limit - 1)));
  }
  return Array.from(selected).sort((a, b) => a - b).map((index) => segments[index]);
}

function isWithinSegment(timestampMs: number, segment: CaptureSegmentSummary): boolean {
  const start = segment.effective_start_ms ?? segment.start_ms;
  const end = segment.effective_end_ms ?? segment.end_ms ?? start + 1;
  return timestampMs >= start && timestampMs <= end;
}

function stageLabel(stage?: string | null): string { return stage === "serve" ? "发球" : stage === "return" ? "接发" : stage === "other" ? "其他" : "未知"; }
function outcomeLabel(outcome?: string | null): string { return outcome === "in_play" ? "入界" : outcome === "net" ? "下网" : outcome === "out" ? "出界" : "未知"; }
function decisionLabel(decision: string): string { return decision === "accepted" ? "确认" : decision === "corrected" ? "修正" : decision === "rejected" ? "拒绝" : "未复核"; }

function validateForm(form: AnnotationFormState): string | null {
  if (form.evidence_end_ms < form.evidence_start_ms || form.event_ms < form.evidence_start_ms || form.event_ms > form.evidence_end_ms) {
    return "事件时间必须位于合法的证据时间窗内";
  }
  if (form.opportunity_status === "not_applicable" && form.outcome !== "unknown") {
    return "不适用机会不能填写确定的击球结果";
  }
  if (form.opportunity_status === "unobservable" && form.outcome !== "unknown") {
    return "不可观察机会不能填写确定的击球结果";
  }
  if (form.landing_status === "measured" && form.landing_zone === "unknown") {
    return "已测量落点必须选择短、中或深区域";
  }
  if (form.landing_status !== "measured" && form.landing_zone !== "unknown") {
    return "不可测落点不能填写具体落点区域";
  }
  if ((form.outcome === "net" || form.outcome === "out") && form.landing_status === "measured") {
    return "下网或出界击球不能标记为已测量有效落点";
  }
  return null;
}
