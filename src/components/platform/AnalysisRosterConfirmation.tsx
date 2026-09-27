import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  PencilRuler,
  SkipForward,
  UserRound,
} from "lucide-react";

import { getPlayerBootstrap, getVideoStreamUrl, resolveAnalysisApiUrl } from "../../services/analysisClient";
import {
  isBootstrapV2,
  type AnalysisRosterConfirmationEntry,
  type CourtEnd,
  type PlayerBootstrapCandidateEvidence,
  type PlayerBootstrapResponse,
  type PlayerBootstrapResultV2,
  type RosterConfirmationRequest,
  type RosterTeamId,
} from "../../types/rallyContext";

/**
 * 分析前的「球员名册与端位确认」步骤。
 *
 * 设计约束（对应 `analysis-roster-confirmation` 规格）：
 * - 名册必须在**创建任务之前**确认并随 Job 冻结，不能在未来的 `rally_start` 上引用。
 * - 默认直接呈现自动预检得到的 P1–P4 人物卡片与主参考画面：正常情况**不需要**
 *   用户播放视频、截帧或逐人画框；只有候选不足或用户主动纠正时才展开手工入口。
 * - 每张卡片的图、时间、机位来自同一次实际观测；主参考画面只叠加该帧真实存在的框。
 * - 三个身份层次彼此分离：`candidate_id`（预检候选）／P 槽位（用户确认）／正式
 *   `Player_N`（只由后端绑定审计产出，前端不推断）。
 * - 用户可跳过；跳过或候选不足都不阻塞普通分析，只在依赖正式身份的消费者上标注 unavailable。
 *
 * 组件是纯受控输入：状态变化通过 `onChange` 回抛，由页面在 `createAnalysisJob` 时提交。
 */
export interface AnalysisRosterConfirmationProps {
  captureTakeId?: string | null;
  videoId?: string | null;
  videoIdB?: string | null;
  matchFormat?: "singles" | "doubles";
  /** 所选分析片段（源视频毫秒）；预检只在片段内采样。 */
  clipStartMs?: number | null;
  clipEndMs?: number | null;
  /** 每次确认状态变化时回抛，供页面组装 Job 请求。 */
  onChange: (request: RosterConfirmationRequest) => void;
}

type ManualAnchor = { timestampMs: number; bbox: [number, number, number, number]; viewId: string };
type DragSelection = { slot: number; x1: number; y1: number; x2: number; y2: number };
type SlotState = { candidateId: string | null; teamId: RosterTeamId | null };

/** 统一后的候选视图模型：v2 直接映射，v1 降级映射。 */
interface CandidateView {
  candidateId: string;
  suggestedSlot: number | null;
  viewId: string;
  timestampMs: number;
  bbox: number[] | null;
  cropUrl: string | null;
  courtXy: number[] | null;
  confidence: number | null;
  evidence: PlayerBootstrapCandidateEvidence | null;
  sourceViews: string[];
}

const ANCHOR_COLORS = ["#2563eb", "#06b6d4", "#f59e0b", "#f97316"];

function slotsFor(matchFormat: "singles" | "doubles"): number {
  return matchFormat === "singles" ? 2 : 4;
}

function validBox(box: number[] | null | undefined): [number, number, number, number] | null {
  if (!box || box.length < 4 || !box.slice(0, 4).every((value) => Number.isFinite(value))) return null;
  const [x1, y1, x2, y2] = box;
  if (x2 <= x1 || y2 <= y1) return null;
  return [x1, y1, x2, y2];
}

function viewLabel(viewId: string | null | undefined, videoIdB?: string | null): string {
  if (!viewId) return "未知机位";
  if (viewId === "cam_2" && videoIdB) return "B 机位";
  if (viewId === "cam_1") return "A 机位";
  return viewId;
}

/** 用 v1 的参考帧 URL 派生"某候选自己那次观测"的画面 URL（保留后端受控取帧语义）。 */
function deriveFrameUrl(
  baseUrl: string | null,
  timestampMs: number,
  bbox: number[] | null,
): string | null {
  if (!baseUrl) return null;
  try {
    const url = new URL(baseUrl, window.location.origin);
    url.searchParams.set("timestampMs", String(Math.max(0, Math.round(timestampMs))));
    if (bbox && bbox.length === 4) {
      url.searchParams.set("bbox", bbox.map((value) => value.toFixed(2)).join(","));
    } else {
      url.searchParams.delete("bbox");
    }
    return `${url.pathname}${url.search}`;
  } catch {
    return baseUrl;
  }
}

function candidatesFromResult(result: PlayerBootstrapResponse | null): CandidateView[] {
  if (!result) return [];
  if (isBootstrapV2(result)) {
    return result.candidates.map((candidate) => ({
      candidateId: candidate.candidate_id,
      suggestedSlot: candidate.suggested_slot ?? null,
      viewId: candidate.view_id,
      timestampMs: candidate.timestamp_ms,
      bbox: validBox(candidate.bbox),
      cropUrl: candidate.crop_url ?? candidate.frame_url ?? null,
      courtXy: candidate.court_xy ?? null,
      confidence: candidate.confidence ?? null,
      evidence: candidate.evidence ?? null,
      sourceViews: candidate.source_views ?? [candidate.view_id],
    }));
  }
  // v1 降级：旧响应只有 canonical_player_id 与统一参考帧。
  return result.candidates.map((candidate, index) => ({
    candidateId: candidate.canonical_player_id,
    suggestedSlot: index + 1,
    viewId: "cam_1",
    timestampMs: candidate.anchor_timestamp_ms,
    bbox: validBox(candidate.anchor_bbox ?? null),
    cropUrl: deriveFrameUrl(
      result.reference_frame_url ?? null,
      candidate.anchor_timestamp_ms,
      validBox(candidate.anchor_bbox ?? null),
    ),
    courtXy: candidate.anchor_court_xy ?? null,
    confidence: candidate.confidence ?? null,
    evidence: null,
    sourceViews: ["cam_1"],
  }));
}

export function AnalysisRosterConfirmation({
  captureTakeId,
  videoId,
  videoIdB,
  matchFormat = "doubles",
  clipStartMs,
  clipEndMs,
  onChange,
}: AnalysisRosterConfirmationProps) {
  const [bootstrap, setBootstrap] = useState<PlayerBootstrapResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 默认"未跳过但未确认"：不预先给任何槽位分配 Team，也**绝不**由算法推断 Team A/B。
  const [skipped, setSkipped] = useState(false);
  const [courtEnd, setCourtEnd] = useState<CourtEnd | null>(null);
  const [slots, setSlots] = useState<Record<number, SlotState>>({});
  // 候选就位标记：确认页在它变 true 之前不把"未分配"当成"候选不足"。
  const [slotsInitialized, setSlotsInitialized] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [manualAnchors, setManualAnchors] = useState<Record<number, ManualAnchor>>({});
  const [captureView, setCaptureView] = useState<"A" | "B">("A");
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [frameTimestampMs, setFrameTimestampMs] = useState<number | null>(null);
  const [frameView, setFrameView] = useState<"A" | "B">("A");
  const [frameLoadError, setFrameLoadError] = useState(false);
  const [activeVisualSlot, setActiveVisualSlot] = useState(0);
  const [dragSelection, setDragSelection] = useState<DragSelection | null>(null);
  const [referenceFrameSize, setReferenceFrameSize] = useState<
    { width: number; height: number; url: string } | null
  >(null);
  const [brokenCrops, setBrokenCrops] = useState<Record<string, boolean>>({});
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameStageRef = useRef<HTMLDivElement | null>(null);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);

  const slotCount = slotsFor(matchFormat);
  const candidates = useMemo(() => candidatesFromResult(bootstrap), [bootstrap]);
  const candidatesById = useMemo(() => {
    const map: Record<string, CandidateView> = {};
    for (const candidate of candidates) map[candidate.candidateId] = candidate;
    return map;
  }, [candidates]);
  const v2 = bootstrap && isBootstrapV2(bootstrap) ? (bootstrap as PlayerBootstrapResultV2) : null;
  const legacyReferenceFrameUrl =
    bootstrap && !isBootstrapV2(bootstrap) && bootstrap.reference_frame_url
      ? resolveAnalysisApiUrl(bootstrap.reference_frame_url)
      : null;
  const activeVideoId = captureView === "B" && videoIdB ? videoIdB : videoId;
  const videoStreamUrl = getVideoStreamUrl(activeVideoId ?? undefined);
  const referenceFrame = v2?.reference_frame ?? null;
  const referenceFrameUrl = referenceFrame?.frame_url ?? null;
  const legacyReferenceTimestampMs =
    bootstrap && !isBootstrapV2(bootstrap) ? bootstrap.reference_timestamp_ms ?? 0 : 0;

  // 自动候选只是预检结果：默认按建议槽位填充，但用户随时可以交换/替换。
  useEffect(() => {
    if (!bootstrap) {
      setSlotsInitialized(false);
      return;
    }
    setSlots((current) => {
      const next: Record<number, SlotState> = {};
      for (let index = 0; index < slotCount; index += 1) {
        const existing = current[index];
        const stillExists =
          existing?.candidateId && candidatesById[existing.candidateId] ? existing.candidateId : null;
        const fallback =
          candidates.find((candidate) => candidate.suggestedSlot === index + 1)?.candidateId ??
          candidates[index]?.candidateId ??
          null;
        const taken = new Set(
          Object.entries(next)
            .filter(([slot]) => Number(slot) !== index)
            .map(([, state]) => state.candidateId)
            .filter((value): value is string => Boolean(value)),
        );
        const chosen = stillExists ?? fallback;
        next[index] = {
          teamId: existing?.teamId ?? null,
          candidateId: chosen && !taken.has(chosen) ? chosen : null,
        };
      }
      return next;
    });
    setSlotsInitialized(true);
  }, [bootstrap, candidates, candidatesById, slotCount]);

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
      .then(() =>
        getPlayerBootstrap({
          captureTakeId,
          videoId,
          videoIdB,
          matchFormat,
          clipStartMs,
          clipEndMs,
          contract: "v2",
        }),
      )
      .then((result) => {
        if (cancelled) return;
        setBootstrap(result ?? null);
        setManualAnchors({});
        setManualMode(false);
        setBrokenCrops({});
        setFrameUrl(null);
        setFrameTimestampMs(null);
        setFrameView("A");
        setFrameLoadError(false);
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
  }, [captureTakeId, videoId, videoIdB, matchFormat, clipStartMs, clipEndMs]);

  const entries = useMemo<AnalysisRosterConfirmationEntry[]>(() => {
    return Array.from({ length: slotCount }, (_, index) => {
      const candidateId = slots[index]?.candidateId ?? null;
      const candidate = candidateId ? candidatesById[candidateId] : undefined;
      const manual = manualAnchors[index];
      return {
        // P 槽位就是用户确认的展示位；正式身份由后端绑定审计另行给出。
        canonical_player_id: `Player_${index + 1}`,
        candidate_id: candidate?.candidateId ?? null,
        slot_index: index,
        display_name: null,
        team_id: slots[index]?.teamId ?? null,
        source_view_id: manual?.viewId ?? candidate?.viewId ?? null,
        anchor_timestamp_ms: manual?.timestampMs ?? candidate?.timestampMs ?? 0,
        anchor_bbox: manual?.bbox ?? candidate?.bbox ?? null,
        anchor_court_xy: candidate?.courtXy ?? null,
        bootstrap_run_id: bootstrap?.bootstrap_run_id ?? null,
        bootstrap_model_version: bootstrap?.bootstrap_model_version ?? null,
        bootstrap_confidence: candidate?.confidence ?? null,
      };
    });
  }, [bootstrap, candidatesById, manualAnchors, slotCount, slots]);

  const captureCurrentFrame = () => {
    const currentVideo = videoRef.current;
    if (!currentVideo || !activeVideoId || !Number.isFinite(currentVideo.currentTime)) return;
    if (
      currentVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
      !currentVideo.videoWidth ||
      !currentVideo.videoHeight
    ) {
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
      setFrameTimestampMs(timestampMs);
      setFrameView(captureView);
      setFrameUrl(canvas.toDataURL("image/jpeg", 0.92));
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
      x: Math.min(
        referenceFrameSize.width,
        Math.max(0, ((event.clientX - bounds.left) / bounds.width) * referenceFrameSize.width),
      ),
      y: Math.min(
        referenceFrameSize.height,
        Math.max(0, ((event.clientY - bounds.top) / bounds.height) * referenceFrameSize.height),
      ),
    };
  };

  const handleFramePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!manualMode || effectiveSkipped || !displayFrameUrl || !referenceFrameSize) return;
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
      Math.min(start.x, point.x),
      Math.min(start.y, point.y),
      Math.max(start.x, point.x),
      Math.max(start.y, point.y),
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
  // 手工入口只在"自动候选不足，或用户主动要求纠正"时展开。
  const autoIncomplete =
    candidates.length < slotCount ||
    Object.keys(slots).some((key) => {
      const index = Number(key);
      if (index >= slotCount) return false;
      return !manualAnchors[index] && !slots[index]?.candidateId;
    });
  const showManualPicker = manualMode || autoIncomplete;
  const displayFrameUrl = frameUrl ?? referenceFrameUrl ?? legacyReferenceFrameUrl;
  const displayTimestampMs =
    frameTimestampMs ?? referenceFrame?.timestamp_ms ?? legacyReferenceTimestampMs;
  const displayFrameView = frameUrl ? frameView : referenceFrame?.view_id ?? "cam_1";
  const visualAnchorsComplete = entries.every((entry) => entry.anchor_bbox?.length === 4);

  /** 主参考画面上的框：只取"该帧真的观测到"的候选，绝不混用异时刻的框。 */
  const referenceBoxes = useMemo(() => {
    const boxes: Array<{ slot: number; box: [number, number, number, number]; color: string }> = [];
    for (let index = 0; index < slotCount; index += 1) {
      const manual = manualAnchors[index];
      if (manual) continue;
      const candidateId = slots[index]?.candidateId;
      if (!candidateId) continue;
      const observed = referenceFrame?.observed_bboxes?.[candidateId];
      const box = validBox(observed ?? null);
      if (!box) continue;
      boxes.push({ slot: index, box, color: ANCHOR_COLORS[index % ANCHOR_COLORS.length] });
    }
    return boxes;
  }, [manualAnchors, referenceFrame, slotCount, slots]);

  /** 指派候选到槽位；同一候选不能占据两个 P 槽位。 */
  const assignCandidate = (index: number, candidateId: string | null) => {
    setSlots((current) => {
      const next: Record<number, SlotState> = {};
      for (const [key, state] of Object.entries(current)) {
        const slotIndex = Number(key);
        next[slotIndex] = {
          teamId: state.teamId,
          // 被"抢走"的槽位回到未识别，而不是让两个槽位指向同一个候选。
          candidateId:
            candidateId && slotIndex !== index && state.candidateId === candidateId
              ? null
              : state.candidateId,
        };
      }
      next[index] = { teamId: current[index]?.teamId ?? null, candidateId };
      return next;
    });
  };

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
      className="mb-6 rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-5"
      data-testid="analysis-roster-confirmation"
      data-roster-status={effectiveSkipped ? "skipped" : (bootstrap?.status ?? "loading")}
      data-court-end={courtEnd ?? "unset"}
      data-skipped={effectiveSkipped ? "true" : "false"}
      data-consumers-enabled={consumersEnabled ? "true" : "false"}
      data-contract={v2 ? "v2" : bootstrap ? "v1" : "none"}
      data-multiview={v2?.multiview_used ? "true" : "false"}
      data-slots-ready={slotsInitialized ? "true" : "false"}
    >
      <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-[var(--ui-ink)]">球员身份确认（可选）</h3>
          <p className="mt-1 text-xs text-slate-500">
            系统已从所选片段中自动挑选 P1–P{slotCount} 的候选画面。核对无误后指定 Team A/B 与初始端位即可；对不上时可交换候选或手工框选。
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
          {skipped ? "改为确认身份" : "跳过身份确认"}
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
          正在所选片段内采样多帧并挑选候选…
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
              ? "自动候选不可用（缺少模型、视频、标定或同步）。可手工框选或跳过。"
              : "自动候选不足：已保留可靠的人，请在下方补全未完成槽位或跳过。"}
            <code className="ml-1 rounded bg-[var(--ui-surface)] px-1 py-0.5 text-[11px] text-slate-500">{diagnostic}</code>
          </span>
        </p>
      ) : null}

      {bootstrap && bootstrap.diagnostics.length > 0 ? (
        <ul className="mt-2 space-y-1" data-testid="roster-quality-diagnostics">
          {bootstrap.diagnostics.map((item) => (
            <li key={item.code} className="flex items-start gap-2 text-[11px] text-amber-700">
              <AlertTriangle className="mt-0.5 shrink-0" size={12} />
              <span>
                <code className="rounded bg-[var(--ui-surface)] px-1 py-0.5">{item.code}</code>
                {item.detail ? <span className="ml-1 text-slate-500">{item.detail}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {effectiveSkipped ? (
        <p className="mt-3 text-xs text-slate-500" data-testid="roster-skipped-note">
          已跳过：任务创建后不会推断 Team A/B，依赖正式身份的指标会显示 unavailable。
        </p>
      ) : (
        <>
          {/* ① 主参考画面：只叠加"该帧实际观测到"的框 */}
          {displayFrameUrl ? (
            <figure className="mt-4 overflow-hidden rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface)]" data-testid="roster-reference-frame">
              <div
                ref={frameStageRef}
                className={`relative mx-auto w-fit max-w-full touch-none select-none ${showManualPicker ? "cursor-crosshair" : ""}`}
                data-testid="roster-reference-frame-canvas"
                onPointerDown={handleFramePointerDown}
                onPointerMove={handleFramePointerMove}
                onPointerUp={handleFramePointerUp}
                onPointerCancel={handleFramePointerUp}
              >
                <img
                  src={displayFrameUrl}
                  alt={`主参考画面（${displayTimestampMs}ms）`}
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
                {referenceFrameSize?.url === displayFrameUrl && (referenceBoxes.length > 0 || dragSelection) ? (
                  <svg
                    className="pointer-events-none absolute inset-0 h-full w-full"
                    viewBox={`0 0 ${referenceFrameSize.width} ${referenceFrameSize.height}`}
                    preserveAspectRatio="none"
                    aria-hidden="true"
                    data-testid="roster-reference-overlay"
                  >
                    {referenceBoxes.map(({ slot, box, color }) => (
                      <g key={`slot-${slot}`} data-testid={`roster-anchor-slot-${slot}`}>
                        <rect
                          x={box[0]}
                          y={box[1]}
                          width={box[2] - box[0]}
                          height={box[3] - box[1]}
                          fill={color}
                          fillOpacity="0.16"
                          stroke={color}
                          strokeWidth={Math.max(2, referenceFrameSize.width / 480)}
                        />
                        <text
                          x={box[0] + 4}
                          y={Math.max(16, box[1] - 5)}
                          fill={color}
                          fontSize={Math.max(14, referenceFrameSize.width / 64)}
                          fontWeight="700"
                          paintOrder="stroke"
                          stroke="white"
                          strokeWidth="4"
                          strokeLinejoin="round"
                        >
                          P{slot + 1}
                        </text>
                      </g>
                    ))}
                    {dragSelection ? (
                      <rect
                        x={Math.min(dragSelection.x1, dragSelection.x2)}
                        y={Math.min(dragSelection.y1, dragSelection.y2)}
                        width={Math.abs(dragSelection.x2 - dragSelection.x1)}
                        height={Math.abs(dragSelection.y2 - dragSelection.y1)}
                        fill={ANCHOR_COLORS[dragSelection.slot % ANCHOR_COLORS.length]}
                        fillOpacity="0.16"
                        stroke={ANCHOR_COLORS[dragSelection.slot % ANCHOR_COLORS.length]}
                        strokeWidth={Math.max(2, referenceFrameSize.width / 480)}
                      />
                    ) : null}
                  </svg>
                ) : null}
              </div>
              <figcaption className="px-3 py-2 text-[11px] text-slate-500">
                主参考画面 · {viewLabel(displayFrameView, videoIdB)} · {displayTimestampMs}ms
                {referenceFrame ? ` · 该帧观测到 ${referenceFrame.candidate_ids.length} 名候选` : ""}
                。画面内的框只标注该帧真实存在的观测，不做人脸识别。
              </figcaption>
              {frameLoadError ? (
                <p className="px-3 pb-2 text-xs text-amber-700">画面截取或加载失败，请确认视频已加载后重试。</p>
              ) : null}
            </figure>
          ) : (
            <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500" data-testid="roster-no-reference-frame">
              暂无参考画面。可展开手工选帧，或直接跳过身份确认。
            </p>
          )}

          {/* ② 四张（单打两张）人物卡片 */}
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {Array.from({ length: slotCount }, (_, index) => {
              const playerId = `Player_${index + 1}`;
              const selectedId = slots[index]?.candidateId ?? null;
              const candidate = selectedId ? candidatesById[selectedId] : undefined;
              const teamId = slots[index]?.teamId ?? null;
              const manual = manualAnchors[index];
              const manualCrop =
                manual && manual.timestampMs === displayTimestampMs && frameUrl ? manual.bbox : null;
              const cropStyle = manualCrop
                ? cropBackgroundStyle(manualCrop, referenceFrameSize?.url === displayFrameUrl ? referenceFrameSize : null, displayFrameUrl)
                : undefined;
              const cropBroken = candidate ? brokenCrops[candidate.candidateId] : false;
              return (
                <div
                  key={playerId}
                  className="rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface)] p-3"
                  data-testid={`roster-candidate-${playerId}`}
                  data-team-assignment={teamId ?? "unassigned"}
                  data-has-anchor={candidate?.courtXy ? "true" : "false"}
                  data-candidate-id={candidate?.candidateId ?? "none"}
                >
                  <div className="flex gap-3">
                    <div
                      className="grid h-36 w-28 shrink-0 place-items-center overflow-hidden rounded-lg border border-[var(--ui-border)] bg-slate-100 bg-no-repeat"
                      style={cropStyle}
                      aria-label={`P${index + 1} 人物画面`}
                      data-testid={`roster-player-crop-${index}`}
                    >
                      {cropStyle ? null : candidate?.cropUrl && !cropBroken ? (
                        <img
                          src={candidate.cropUrl}
                          alt={`P${index + 1} 人物画面`}
                          className="h-full w-full object-cover"
                          data-testid={`roster-candidate-crop-${index}`}
                          onError={() =>
                            setBrokenCrops((current) => ({ ...current, [candidate.candidateId]: true }))
                          }
                        />
                      ) : (
                        <span className="px-2 text-center text-[11px] text-slate-400">尚无人物画面</span>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-[var(--ui-ink)]" data-testid={`roster-slot-label-${index}`}>
                          P{index + 1}
                        </span>
                        {candidate?.confidence != null ? (
                          <span className="text-[11px] text-slate-400">检测置信度 {(candidate.confidence * 100).toFixed(0)}%</span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-[11px] text-slate-500" data-testid={`roster-candidate-source-${index}`}>
                        {manual
                          ? `人工确认 · ${viewLabel(manual.viewId, videoIdB)} · ${manual.timestampMs}ms`
                          : candidate
                            ? `${viewLabel(candidate.viewId, videoIdB)} · ${candidate.timestampMs}ms${
                                candidate.sourceViews.length > 1 ? " · 双摄佐证" : ""
                              }`
                            : "未识别，待补全"}
                      </p>
                      {candidate?.courtXy ? (
                        <p className="mt-1 text-[11px] text-slate-400">
                          球场坐标 ({candidate.courtXy[0].toFixed(1)}, {candidate.courtXy[1].toFixed(1)}) ft
                          {candidate.evidence?.target_court_membership != null
                            ? ` · 场内占比 ${(candidate.evidence.target_court_membership * 100).toFixed(0)}%`
                            : ""}
                        </p>
                      ) : null}
                      <label className="mt-2 block text-[11px] text-slate-500">
                        <span className="mr-1">本次 P{index + 1} 对应</span>
                        <select
                          className="rounded border border-[var(--ui-border)] bg-[var(--ui-surface)] px-1.5 py-1 text-[11px] text-slate-700"
                          value={selectedId ?? ""}
                          onChange={(event) => assignCandidate(index, event.target.value || null)}
                          data-testid={`roster-player-select-${index}`}
                        >
                          <option value="">未识别/手工指定</option>
                          {candidates.map((option) => {
                            const usedByAnotherSlot = Object.entries(slots).some(
                              ([slot, state]) => Number(slot) !== index && state.candidateId === option.candidateId,
                            );
                            return (
                              <option key={option.candidateId} value={option.candidateId} disabled={usedByAnotherSlot}>
                                {option.candidateId}（{viewLabel(option.viewId, videoIdB)} · {option.timestampMs}ms）
                              </option>
                            );
                          })}
                        </select>
                      </label>
                      <div className="mt-2 flex gap-3">
                        {(["A", "B"] as RosterTeamId[]).map((team) => (
                          <label key={team} className="flex items-center gap-1.5 text-xs text-slate-600">
                            <input
                              type="radio"
                              name={`roster-team-${index}`}
                              checked={teamId === team}
                              onChange={() => {
                                setSkipped(false);
                                setSlots((current) => ({
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

          {/* ③ 手工入口：仅在候选不足或用户主动纠正时展开 */}
          <div className="mt-4">
            <button
              type="button"
              className="quiet-button inline-flex items-center gap-1.5 text-xs"
              onClick={() => setManualMode((value) => !value)}
              data-testid="roster-manual-toggle"
            >
              <PencilRuler size={14} />
              {manualMode ? "收起手工选帧" : autoIncomplete ? "手工补全未识别的槽位" : "手工纠正（选帧并画框）"}
            </button>
          </div>

          {showManualPicker ? (
            <section className="mt-3 rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface)] p-3" data-testid="roster-manual-picker">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] text-slate-500">
                  暂停在球员清楚的一帧并截取；先点选槽位，再在静帧上拖框。远景可框住整个人。
                </p>
                <div className="flex gap-1" aria-label="名册参考机位">
                  {(["A", "B"] as const)
                    .filter((view) => view === "A" || Boolean(videoIdB))
                    .map((view) => (
                      <button
                        key={view}
                        type="button"
                        aria-pressed={captureView === view}
                        className={`rounded-lg px-3 py-1.5 text-xs font-bold ${captureView === view ? "bg-[var(--ui-surface-mint)] text-[var(--ui-brand-deep)]" : "bg-slate-100 text-slate-600"}`}
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
                    className="mt-2 rounded-lg border border-[#B7E4C7] bg-[var(--ui-surface-soft)] px-3 py-2 text-xs font-bold text-[var(--ui-brand-deep)] disabled:opacity-50"
                    onClick={captureCurrentFrame}
                    disabled={!activeVideoId}
                    data-testid="roster-capture-frame"
                  >
                    截取当前画面
                  </button>
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {Array.from({ length: slotCount }, (_, index) => (
                  <button
                    key={index}
                    type="button"
                    aria-pressed={activeVisualSlot === index}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold ${activeVisualSlot === index ? "bg-[var(--ui-brand-solid-deep)] text-white" : "bg-slate-100 text-slate-600"}`}
                    onClick={() => setActiveVisualSlot(index)}
                  >
                    P{index + 1}
                    {manualAnchors[index] ? " · 已框选" : ""}
                  </button>
                ))}
                <span className="text-[11px] text-slate-500">当前待框选：P{activeVisualSlot + 1}</span>
              </div>
            </section>
          ) : null}

          {/* ④ Team A/B 与初始端位：身份卡片之后的简短确认区 */}
          <div className="mt-4 rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface)] p-3">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-[var(--ui-brand-deep)]">初始端位</p>
            <p className="mb-3 text-xs text-slate-500">
              请确认 Team A 在录像开始时位于球场的哪一端。换边由录制中的换边操作自动回放。
            </p>
            <div className="flex flex-wrap gap-4">
              {[
                { value: "end_a" as CourtEnd, label: "Team A 位于 A 端" },
                { value: "end_b" as CourtEnd, label: "Team A 位于 B 端" },
              ].map((option) => (
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
            <p className="mt-2 text-[11px] text-slate-400">
              本阶段只确认 P1–P{slotCount} 与队伍归属，姓名留待后续功能补充。
            </p>
          </div>

          {courtEnd && entries.every((entry) => entry.team_id) && visualAnchorsComplete ? (
            <p className="mt-3 flex items-center gap-2 text-xs text-[var(--ui-brand-deep)]" data-testid="roster-ready">
              <CheckCircle2 size={14} />
              已为 {entries.length} 名球员确认画面来源、队伍和初始端位；创建任务时将冻结这份名册。
            </p>
          ) : (
            <p className="mt-3 text-xs text-slate-500" data-testid="roster-incomplete">
              尚未完整：需为每名球员指定 Team 并选择初始端位（候选不足时请手工框选），或直接跳过。
            </p>
          )}
        </>
      )}
    </section>
  );
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
