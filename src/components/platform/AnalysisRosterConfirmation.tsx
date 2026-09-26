import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, SkipForward, UserRound } from "lucide-react";

import { getPlayerBootstrap, getVideoStreamUrl, resolveAnalysisApiUrl } from "../../services/analysisClient";
import type {
  AnalysisRosterConfirmationEntry,
  CourtEnd,
  PlayerBootstrapCandidate,
  PlayerBootstrapResult,
  RosterConfirmationRequest,
  RosterTeamId,
} from "../../types/rallyContext";
import { formatPlayerId } from "../../utils/analysisHelpers";

/**
 * 分析前的「球员名册与端位确认」步骤。
 *
 * 设计约束（对应 `analysis-roster-confirmation` 规格）：
 * - 名册必须在**创建任务之前**确认并随 Job 冻结，不能在未来的 `rally_start` 上引用。
 * - 用户可跳过；跳过或候选不足都不阻塞普通分析，只在依赖正式身份的消费者上标注 unavailable。
 * - 正式 Team A/B 由人工确认，不由 `initial_side` 推断。
 *
 * 该组件是纯受控输入：状态变化通过 `onChange` 回抛，由页面在 `createAnalysisJob` 时提交。
 */
export interface AnalysisRosterConfirmationProps {
  captureTakeId?: string | null;
  videoId?: string | null;
  videoIdB?: string | null;
  matchFormat?: "singles" | "doubles";
  /** 每次确认状态变化时回抛，供页面组装 Job 请求。 */
  onChange: (request: RosterConfirmationRequest) => void;
}

type SlotAssignment = { teamId: RosterTeamId | null; candidateId?: string | null };
type ManualPlayerAnchor = { timestampMs: number; bbox: [number, number, number, number]; viewId: string };
type DragSelection = { slot: number; x1: number; y1: number; x2: number; y2: number };

const ANCHOR_COLORS = ["#2563eb", "#06b6d4", "#f59e0b", "#f97316"];

function validAnchorBox(candidate: PlayerBootstrapCandidate): [number, number, number, number] | null {
  const box = candidate.anchor_bbox;
  if (!box || box.length < 4 || !box.slice(0, 4).every((value) => Number.isFinite(value))) return null;
  const [x1, y1, x2, y2] = box;
  if (x2 <= x1 || y2 <= y1) return null;
  return [x1, y1, x2, y2];
}

function slotsFor(matchFormat: "singles" | "doubles"): number {
  return matchFormat === "singles" ? 2 : 4;
}

function cropBackgroundStyle(
  bbox: number[] | null | undefined,
  dimensions: { width: number; height: number } | null,
  imageUrl: string | null,
): CSSProperties | undefined {
  if (!bbox || bbox.length < 4 || !dimensions || !imageUrl) return undefined;
  const [x1, y1, x2, y2] = bbox;
  const width = x2 - x1;
  const height = y2 - y1;
  if (![x1, y1, x2, y2, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return undefined;
  const scale = Math.min(112 / width, 144 / height);
  return {
    backgroundImage: `url("${imageUrl}")`,
    backgroundSize: `${dimensions.width * scale}px ${dimensions.height * scale}px`,
    backgroundPosition: `-${x1 * scale}px -${y1 * scale}px`,
  };
}

export function AnalysisRosterConfirmation({
  captureTakeId,
  videoId,
  videoIdB,
  matchFormat = "doubles",
  onChange,
}: AnalysisRosterConfirmationProps) {
  const [bootstrap, setBootstrap] = useState<PlayerBootstrapResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 默认"未跳过但未确认"：不预先给任何槽位分配 Team，也**绝不**由算法推断 Team A/B。
  const [skipped, setSkipped] = useState(false);
  const [courtEnd, setCourtEnd] = useState<CourtEnd | null>(null);
  const [assignments, setAssignments] = useState<Record<number, SlotAssignment>>({});
  const [captureView, setCaptureView] = useState<"A" | "B">("A");
  const [frameView, setFrameView] = useState<"A" | "B">("A");
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [frameTimestampMs, setFrameTimestampMs] = useState<number | null>(null);
  const [frameLoadError, setFrameLoadError] = useState(false);
  const [activeVisualSlot, setActiveVisualSlot] = useState(0);
  const [manualAnchors, setManualAnchors] = useState<Record<number, ManualPlayerAnchor>>({});
  const [dragSelection, setDragSelection] = useState<DragSelection | null>(null);
  const [referenceFrameSize, setReferenceFrameSize] = useState<
    { width: number; height: number; url: string } | null
  >(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameStageRef = useRef<HTMLDivElement | null>(null);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);

  const slotCount = slotsFor(matchFormat);
  const activeVideoId = captureView === "B" && videoIdB ? videoIdB : videoId;
  const videoStreamUrl = getVideoStreamUrl(activeVideoId ?? undefined);
  const bootstrapFrameUrl = bootstrap?.reference_frame_url
    ? resolveAnalysisApiUrl(bootstrap.reference_frame_url)
    : null;

  // 候选只是预检结果，P1–P4 的本次任务映射由用户确认。默认按候选顺序填充，
  // 但保留可编辑选择，避免把一次预检的编号误当成永久身份。
  useEffect(() => {
    const candidates = bootstrap?.candidates ?? [];
    setAssignments((current) => {
      const next: Record<number, SlotAssignment> = {};
      for (let index = 0; index < slotCount; index += 1) {
        const existing = current[index];
        const existingCandidateStillExists = existing?.candidateId
          ? candidates.some((candidate) => candidate.canonical_player_id === existing.candidateId)
          : false;
        next[index] = {
          teamId: existing?.teamId ?? null,
          candidateId: existingCandidateStillExists
            ? existing?.candidateId
            : candidates[index]?.canonical_player_id ?? null,
        };
      }
      return next;
    });
  }, [bootstrap, slotCount]);

  useEffect(() => {
    let cancelled = false;
    if (!captureTakeId && !videoId) {
      setBootstrap(null);
      return () => {
        cancelled = true;
      };
    }
    setIsLoading(true);
    setLoadError(null);
    // 用 Promise.resolve() 包一层：无论 client 抛同步错还是返回 undefined，
    // 都只会降级成"预检失败"，不会把创建分析页整页打崩。
    Promise.resolve()
      .then(() => getPlayerBootstrap({ captureTakeId, videoId, matchFormat }))
      .then((result) => {
        if (!cancelled) {
          setBootstrap(result ?? null);
          const nextFrameUrl = result?.reference_frame_url
            ? resolveAnalysisApiUrl(result.reference_frame_url)
            : null;
          setFrameUrl(nextFrameUrl);
          setFrameTimestampMs(result?.reference_timestamp_ms ?? null);
          setFrameView("A");
          setFrameLoadError(false);
          setManualAnchors({});
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setBootstrap(null);
        setLoadError(error instanceof Error ? error.message : "预检失败");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [captureTakeId, videoId, matchFormat]);

  const entries = useMemo<AnalysisRosterConfirmationEntry[]>(() => {
    const candidates = bootstrap?.candidates ?? [];
    return Array.from({ length: slotCount }, (_, index) => {
      const selectedCandidateId = assignments[index]?.candidateId;
      const candidate = selectedCandidateId
        ? candidates.find((item) => item.canonical_player_id === selectedCandidateId)
        : selectedCandidateId === null
          ? undefined
          : candidates[index];
      const canonical = candidate?.canonical_player_id ?? `Player_${index + 1}`;
      return {
        canonical_player_id: canonical,
        display_name: candidate?.display_name ?? null,
        team_id: assignments[index]?.teamId ?? null,
        source_view_id: manualAnchors[index]?.viewId ?? null,
        anchor_timestamp_ms: manualAnchors[index]?.timestampMs ?? candidate?.anchor_timestamp_ms ?? 0,
        anchor_bbox: manualAnchors[index]?.bbox ?? candidate?.anchor_bbox ?? null,
        anchor_court_xy: candidate?.anchor_court_xy ?? null,
        bootstrap_run_id: bootstrap?.bootstrap_run_id ?? null,
        bootstrap_model_version: bootstrap?.bootstrap_model_version ?? null,
        bootstrap_confidence: candidate?.confidence ?? null,
      };
    });
  }, [assignments, bootstrap, manualAnchors, slotCount]);

  const captureCurrentFrame = () => {
    const currentVideo = videoRef.current;
    if (!currentVideo || !activeVideoId || !Number.isFinite(currentVideo.currentTime)) return;
    if (currentVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !currentVideo.videoWidth || !currentVideo.videoHeight) {
      setFrameLoadError(true);
      return;
    }
    const timestampMs = Math.max(0, Math.round(currentVideo.currentTime * 1000));
    const canvas = document.createElement("canvas");
    canvas.width = currentVideo.videoWidth;
    canvas.height = currentVideo.videoHeight;
    try {
      const context = canvas.getContext("2d");
      if (!context) throw new Error("无法创建画面缓存");
      context.drawImage(currentVideo, 0, 0, canvas.width, canvas.height);
      const nextFrameUrl = canvas.toDataURL("image/jpeg", 0.92);
      setFrameTimestampMs(timestampMs);
      setFrameView(captureView);
      setFrameUrl(nextFrameUrl);
      setReferenceFrameSize(null);
      setFrameLoadError(false);
      setManualAnchors({});
      setDragSelection(null);
    } catch {
      setFrameLoadError(true);
    }
  };

  const imagePointFromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const stage = frameStageRef.current;
    if (!stage || !referenceFrameSize) return null;
    const bounds = stage.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return null;
    return {
      x: Math.min(referenceFrameSize.width, Math.max(0, (event.clientX - bounds.left) / bounds.width * referenceFrameSize.width)),
      y: Math.min(referenceFrameSize.height, Math.max(0, (event.clientY - bounds.top) / bounds.height * referenceFrameSize.height)),
    };
  };

  const handleFramePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (effectiveSkipped || !frameUrl || !referenceFrameSize) return;
    const point = imagePointFromPointer(event);
    if (!point) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStartRef.current = point;
    setDragSelection({ slot: activeVisualSlot, x1: point.x, y1: point.y, x2: point.x, y2: point.y });
  };

  const handleFramePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragStartRef.current;
    if (!start) return;
    const point = imagePointFromPointer(event);
    if (!point) return;
    setDragSelection({ slot: activeVisualSlot, x1: start.x, y1: start.y, x2: point.x, y2: point.y });
  };

  const handleFramePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragStartRef.current;
    const point = imagePointFromPointer(event);
    dragStartRef.current = null;
    setDragSelection(null);
    if (!start || !point || frameTimestampMs == null) return;
    const bbox: [number, number, number, number] = [
      Math.min(start.x, point.x), Math.min(start.y, point.y),
      Math.max(start.x, point.x), Math.max(start.y, point.y),
    ];
    if (bbox[2] - bbox[0] < 12 || bbox[3] - bbox[1] < 12) return;
    setSkipped(false);
    setManualAnchors((current) => ({
      ...current,
      [activeVisualSlot]: {
        timestampMs: frameTimestampMs,
        bbox,
        viewId: frameView === "A" ? "cam_1" : "cam_2",
      },
  }));
  };

  // feature gate 关闭时后端不会冻结任何上下文；此时一律按"跳过"提交，避免误导。
  const consumersEnabled = bootstrap?.consumers_enabled ?? true;
  const effectiveSkipped = skipped || !consumersEnabled;
  const displayFrameUrl = frameUrl ?? bootstrapFrameUrl;
  const displayTimestampMs = frameTimestampMs ?? bootstrap?.reference_timestamp_ms ?? 0;
  const visualAnchorsComplete = entries.every((entry) => entry.anchor_bbox?.length === 4);

  const emit = useCallback(() => {
    onChange({
      skipped: effectiveSkipped,
      initial_team_a_end: effectiveSkipped ? null : courtEnd,
      entries: effectiveSkipped ? [] : entries.filter((entry) => entry.team_id !== null),
      bootstrap_run_id: bootstrap?.bootstrap_run_id ?? null,
      bootstrap_model_version: bootstrap?.bootstrap_model_version ?? null,
    });
  }, [bootstrap, courtEnd, effectiveSkipped, entries, onChange]);

  useEffect(() => {
    emit();
  }, [emit]);

  const diagnostic = bootstrap?.unavailable_reason ?? null;
  const blocking = bootstrap?.status === "unavailable";

  return (
    <section
      className="mb-6 rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-5"
      data-testid="analysis-roster-confirmation"
      data-roster-status={effectiveSkipped ? "skipped" : (bootstrap?.status ?? "loading")}
      data-court-end={courtEnd ?? "unset"}
      data-skipped={effectiveSkipped ? "true" : "false"}
      data-consumers-enabled={consumersEnabled ? "true" : "false"}
    >
      <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-[#14241B]">球员名册与端位（可选）</h3>
          <p className="mt-1 text-xs text-slate-500">
            看视频截帧并为 P1–P4 框选球员后，再确认 Team A/B 和初始端位；任务创建时会冻结这份人工名册。
          </p>
        </div>
        <button
          type="button"
          className="quiet-button inline-flex items-center gap-1.5 text-xs"
          onClick={() => setSkipped((value) => !value)}
          disabled={!consumersEnabled}
          data-testid="roster-skip-toggle"
        >
          {skipped ? <UserRound size={14} /> : <SkipForward size={14} />}
          {skipped ? "改为填写名册" : "跳过名册确认"}
        </button>
      </header>

      {consumersEnabled ? null : (
        <p className="mt-2 text-xs text-slate-500" data-testid="roster-consumers-disabled">
          当前部署未启用分析回合上下文消费，提交名册与端位不会冻结任何上下文；该步骤仅作说明。
        </p>
      )}

      {isLoading ? (
        <p className="flex items-center gap-2 text-xs text-slate-500" data-testid="roster-loading">
          <Loader2 className="animate-spin" size={14} />
          正在读取可复用产物的候选球员…
        </p>
      ) : null}

      {loadError ? (
        <p className="flex items-center gap-2 text-xs text-amber-700" data-testid="roster-load-error">
          <AlertTriangle size={14} />
          预检请求失败（{loadError}）。你仍可手工填写或跳过。
        </p>
      ) : null}

      {!isLoading && !loadError && diagnostic ? (
        <p className="flex items-start gap-2 text-xs text-slate-600" data-testid="roster-diagnostic">
          <Info className="mt-0.5 shrink-0" size={14} />
          <span>
            {blocking
              ? "没有可复用的分析产物，无法自动给出候选参考帧。可直接手工指定或跳过。"
              : "候选不足：请手工补全未识别的槽位。"}
            <code className="ml-1 rounded bg-white px-1 py-0.5 text-[11px] text-slate-500">{diagnostic}</code>
          </span>
        </p>
      ) : null}

      {bootstrap && bootstrap.diagnostics.length > 0 ? (
        <ul className="mt-2 space-y-1" data-testid="roster-quality-diagnostics">
          {bootstrap.diagnostics.map((item) => (
            <li key={item.code} className="flex items-start gap-2 text-[11px] text-amber-700">
              <AlertTriangle className="mt-0.5 shrink-0" size={12} />
              <span>
                <code className="rounded bg-white px-1 py-0.5">{item.code}</code>
                {item.detail ? <span className="ml-1 text-slate-500">{item.detail}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {!effectiveSkipped ? (
        <section className="mt-4 rounded-xl border border-[#DDE9D6] bg-white p-3" data-testid="roster-visual-picker">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-bold text-[#14241B]">视频画面确认 P1–P{slotCount}</p>
              <p className="mt-1 text-[11px] text-slate-500">暂停在四名球员都清楚的一帧并截取；逐个选择 P1–P4，在静帧上拖框框住脸部/上半身（远景可框整个人），卡片会放大显示裁剪图。</p>
            </div>
            <div className="flex gap-1" aria-label="名册参考机位">
              {(["A", "B"] as const).filter((view) => view === "A" || Boolean(videoIdB)).map((view) => (
                <button
                  key={view}
                  type="button"
                  aria-pressed={captureView === view}
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold ${captureView === view ? "bg-[#EAF8F0] text-[#168A34]" : "bg-slate-100 text-slate-600"}`}
                  onClick={() => setCaptureView(view)}
                >
                  {view} 机位
                </button>
              ))}
            </div>
          </div>
          {videoStreamUrl ? (
            <div className="mt-3">
              <video
                ref={videoRef}
                key={activeVideoId}
                src={videoStreamUrl}
                controls
                playsInline
                crossOrigin="anonymous"
                preload="metadata"
                className="max-h-72 w-full rounded-lg bg-black object-contain"
                data-testid="roster-source-video"
              />
              <button
                type="button"
                className="mt-2 rounded-lg border border-[#B7E4C7] bg-[#F5FAF1] px-3 py-2 text-xs font-bold text-[#168A34] disabled:opacity-50"
                onClick={captureCurrentFrame}
                disabled={!activeVideoId}
                data-testid="roster-capture-frame"
              >
                截取当前画面
              </button>
              <span className="ml-2 text-[11px] text-slate-500">建议暂停在能同时看清四名球员的时刻。</span>
            </div>
          ) : null}

          {displayFrameUrl ? (
            <figure className="mt-3 overflow-hidden rounded-xl border border-[#DDE9D6] bg-white" data-testid="roster-reference-frame">
              <div
                ref={frameStageRef}
                className={`relative mx-auto w-fit max-w-full touch-none select-none ${effectiveSkipped ? "" : "cursor-crosshair"}`}
                data-testid="roster-reference-frame-canvas"
                onPointerDown={handleFramePointerDown}
                onPointerMove={handleFramePointerMove}
                onPointerUp={handleFramePointerUp}
                onPointerCancel={handleFramePointerUp}
              >
                <img
                  src={displayFrameUrl}
                  alt={`视频参考帧（${displayTimestampMs}ms）`}
                  className="block max-h-[62vh] max-w-full bg-slate-950 object-contain"
                  onLoad={(event) => {
                    const { naturalWidth, naturalHeight } = event.currentTarget;
                    setFrameLoadError(false);
                    if (naturalWidth > 0 && naturalHeight > 0) {
                      setReferenceFrameSize({ width: naturalWidth, height: naturalHeight, url: displayFrameUrl });
                    }
                  }}
                  onError={() => {
                    setFrameLoadError(true);
                    setReferenceFrameSize(null);
                  }}
                />
                {referenceFrameSize?.url === displayFrameUrl ? (
                  <svg
                    className="pointer-events-none absolute inset-0 h-full w-full"
                    viewBox={`0 0 ${referenceFrameSize.width} ${referenceFrameSize.height}`}
                    preserveAspectRatio="none"
                    aria-hidden="true"
                    data-testid="roster-reference-overlay"
                  >
                    {Array.from({ length: slotCount }, (_, index) => {
                      const manual = manualAnchors[index];
                      const manualBox = manual?.timestampMs === displayTimestampMs ? manual.bbox : null;
                      const selectedId = assignments[index]?.candidateId;
                      const candidate = selectedId
                        ? bootstrap?.candidates.find((item) => item.canonical_player_id === selectedId)
                        : undefined;
                      const automaticBox = candidate?.anchor_timestamp_ms === displayTimestampMs
                        ? validAnchorBox(candidate)
                        : null;
                      const box = manualBox ?? automaticBox;
                      const activeDrag = dragSelection?.slot === index ? dragSelection : null;
                      const values = activeDrag
                        ? [Math.min(activeDrag.x1, activeDrag.x2), Math.min(activeDrag.y1, activeDrag.y2), Math.max(activeDrag.x1, activeDrag.x2), Math.max(activeDrag.y1, activeDrag.y2)]
                        : box;
                      if (!values) return null;
                      const [x1, y1, x2, y2] = values;
                      const color = ANCHOR_COLORS[index % ANCHOR_COLORS.length];
                      return (
                        <g key={`slot-${index}`} data-testid={`roster-anchor-slot-${index}`}>
                          <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill={color} fillOpacity="0.16" stroke={color} strokeWidth={Math.max(2, referenceFrameSize.width / 480)} />
                          <text x={x1 + 4} y={Math.max(16, y1 - 5)} fill={color} fontSize={Math.max(14, referenceFrameSize.width / 64)} fontWeight="700" paintOrder="stroke" stroke="white" strokeWidth="4" strokeLinejoin="round">P{index + 1}</text>
                        </g>
                      );
                    })}
                  </svg>
              ) : null}
              </div>
              <figcaption className="px-3 py-2 text-[11px] text-slate-500">
                参考画面 · {frameView} 机位 · {displayTimestampMs}ms。先点选下方 P 槽位，再在图中拖出对应球员的框；这一步由你确认画面身份，不做人脸识别。
              </figcaption>
              {frameLoadError ? <p className="px-3 pb-2 text-xs text-amber-700">画面截取或加载失败，请确认视频已加载后重试。</p> : null}
            </figure>
          ) : (
            <p className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">暂无参考画面。请先播放视频并截取一帧。</p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {Array.from({ length: slotCount }, (_, index) => (
              <button
                key={index}
                type="button"
                aria-pressed={activeVisualSlot === index}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold ${activeVisualSlot === index ? "bg-[#168A34] text-white" : "bg-slate-100 text-slate-600"}`}
                onClick={() => setActiveVisualSlot(index)}
              >
                P{index + 1}{manualAnchors[index] ? " · 已截取" : ""}
              </button>
            ))}
            <span className="text-[11px] text-slate-500">当前待框选：P{activeVisualSlot + 1}</span>
          </div>
        </section>
      ) : null}

      {effectiveSkipped ? (
        <p className="mt-3 text-xs text-slate-500" data-testid="roster-skipped-note">
          已跳过：任务创建后不会推断 Team A/B，依赖正式身份的指标会显示 unavailable。
        </p>
      ) : (
        <>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {Array.from({ length: slotCount }, (_, index) => {
              const candidates = bootstrap?.candidates ?? [];
              const selectedCandidateId = assignments[index]?.candidateId;
              const candidate = selectedCandidateId
                ? candidates.find((item) => item.canonical_player_id === selectedCandidateId)
                : selectedCandidateId === null
                  ? undefined
                  : candidates[index];
              const playerId = candidate?.canonical_player_id ?? `Player_${index + 1}`;
              const teamId = assignments[index]?.teamId ?? null;
              const manual = manualAnchors[index];
              const manualCrop = manual?.timestampMs === displayTimestampMs ? manual.bbox : null;
              const automaticCrop = candidate?.anchor_timestamp_ms === displayTimestampMs
                ? validAnchorBox(candidate)
                : null;
              const cropStyle = cropBackgroundStyle(
                manualCrop ?? automaticCrop,
                referenceFrameSize?.url === displayFrameUrl ? referenceFrameSize : null,
                displayFrameUrl,
              );
              return (
                <div
                  key={playerId}
                  className="rounded-xl border border-[#DDE9D6] bg-white p-3"
                  data-testid={`roster-candidate-${playerId}`}
                  data-team-assignment={teamId ?? "unassigned"}
                  data-has-anchor={candidate?.anchor_court_xy ? "true" : "false"}
                >
                  <div className="flex gap-3">
                    <div
                      className="grid h-36 w-28 shrink-0 place-items-center overflow-hidden rounded-lg border border-[#DDE9D6] bg-slate-100 bg-no-repeat"
                      style={cropStyle}
                      aria-label={manualCrop || automaticCrop ? `P${index + 1} 视频裁剪图` : `P${index + 1} 尚无裁剪图`}
                      data-testid={`roster-player-crop-${index}`}
                    >
                      {!cropStyle ? <span className="px-2 text-center text-[11px] text-slate-400">尚未截取球员画面</span> : null}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-[#14241B]">{formatPlayerId(playerId)}</span>
                        {candidate?.confidence != null ? (
                          <span className="text-[11px] text-slate-400">候选置信度 {(candidate.confidence * 100).toFixed(0)}%</span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-[11px] text-slate-500">
                        {candidate?.display_name || (candidate ? "候选身份，需看图确认" : "未识别，待手工补全")}
                      </p>
                      <label className="mt-2 block text-[11px] text-slate-500">
                        <span className="mr-1">本次 P{index + 1} 对应</span>
                        <select
                          className="rounded border border-[#DDE9D6] bg-white px-1.5 py-1 text-[11px] text-slate-700"
                          value={selectedCandidateId ?? ""}
                          onChange={(event) => {
                            const candidateId = event.target.value || null;
                            setAssignments((current) => {
                              const next = { ...current };
                              for (const [slot, assignment] of Object.entries(next)) {
                                if (slot !== String(index) && candidateId && assignment.candidateId === candidateId) {
                                  next[Number(slot)] = { ...assignment, candidateId: null };
                                }
                              }
                              next[index] = { teamId: current[index]?.teamId ?? null, candidateId };
                              return next;
                            });
                          }}
                          data-testid={`roster-player-select-${index}`}
                        >
                          <option value="">未识别/手工指定</option>
                          {candidates.map((option) => {
                            const usedByAnotherSlot = Object.entries(assignments).some(
                              ([slot, assignment]) => slot !== String(index) && assignment.candidateId === option.canonical_player_id,
                            );
                            return (
                              <option key={option.canonical_player_id} value={option.canonical_player_id} disabled={usedByAnotherSlot}>
                                {option.display_name || option.canonical_player_id}
                              </option>
                            );
                          })}
                        </select>
                      </label>
                      {candidate?.anchor_court_xy ? (
                        <p className="mt-1 text-[11px] text-slate-400">
                          锚点 {candidate.anchor_timestamp_ms}ms · 球场坐标 ({candidate.anchor_court_xy[0].toFixed(1)}, {candidate.anchor_court_xy[1].toFixed(1)}) ft
                        </p>
                      ) : null}
                      {manual ? <p className="mt-1 text-[11px] text-[#168A34]">人工确认 · {manual.viewId === "cam_1" ? "A" : "B"} 机位 · {manual.timestampMs}ms</p> : null}
                      <div className="mt-2 flex gap-3">
                        {(["A", "B"] as RosterTeamId[]).map((team) => (
                          <label key={team} className="flex items-center gap-1.5 text-xs text-slate-600">
                            <input
                              type="radio"
                              name={`roster-team-${index}`}
                              checked={teamId === team}
                              onChange={() => {
                                setSkipped(false);
                                setAssignments((current) => ({
                                  ...current,
                                  [index]: { teamId: team, candidateId: current[index]?.candidateId ?? null },
                                }));
                              }}
                              data-testid={`roster-team-${index}-${team}`}
                            />
                            Team {team}
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-4 rounded-xl border border-[#DDE9D6] bg-white p-3">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-[#168A34]">初始端位</p>
            <p className="mb-3 text-xs text-slate-500">请确认 Team A 在录像开始时位于球场的哪一端。换边由录制中的换边操作自动回放。</p>
            <div className="flex flex-wrap gap-4">
              {(
                [
                  { value: "end_a" as CourtEnd, label: "Team A 位于 A 端" },
                  { value: "end_b" as CourtEnd, label: "Team A 位于 B 端" },
                ]
              ).map((option) => (
                <label key={option.value} className="flex items-center gap-1.5 text-xs text-slate-600">
                  <input
                    type="radio"
                    name="court-end-initial"
                    checked={courtEnd === option.value}
                    onChange={() => {
                      setSkipped(false);
                      setCourtEnd(option.value);
                    }}
                    data-testid={`court-end-${option.value}`}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          </div>

          {courtEnd && entries.every((entry) => entry.team_id) && visualAnchorsComplete ? (
            <p className="mt-3 flex items-center gap-2 text-xs text-[#168A34]" data-testid="roster-ready">
              <CheckCircle2 size={14} />
              已为 {entries.length} 名球员确认画面、队伍和初始端位；创建任务时将冻结这份名册。
            </p>
          ) : (
            <p className="mt-3 text-xs text-slate-500" data-testid="roster-incomplete">
              尚未完整：需为每名球员框选视频画面、指定 Team 并选择初始端位，或直接跳过。
            </p>
          )}
        </>
      )}
    </section>
  );
}
