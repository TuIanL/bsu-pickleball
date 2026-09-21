import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, SkipForward, UserRound } from "lucide-react";

import { getPlayerBootstrap } from "../../services/analysisClient";
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
  matchFormat?: "singles" | "doubles";
  /** 每次确认状态变化时回抛，供页面组装 Job 请求。 */
  onChange: (request: RosterConfirmationRequest) => void;
}

type SlotAssignment = { teamId: RosterTeamId | null; candidateId?: string | null };

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

export function AnalysisRosterConfirmation({
  captureTakeId,
  videoId,
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
  const [referenceFrameSize, setReferenceFrameSize] = useState<
    { width: number; height: number; url: string } | null
  >(null);

  const slotCount = slotsFor(matchFormat);

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
        if (!cancelled) setBootstrap(result ?? null);
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
        source_view_id: null,
        anchor_timestamp_ms: candidate?.anchor_timestamp_ms ?? 0,
        anchor_bbox: candidate?.anchor_bbox ?? null,
        anchor_court_xy: candidate?.anchor_court_xy ?? null,
        bootstrap_run_id: bootstrap?.bootstrap_run_id ?? null,
        bootstrap_model_version: bootstrap?.bootstrap_model_version ?? null,
        bootstrap_confidence: candidate?.confidence ?? null,
      };
    });
  }, [assignments, bootstrap, slotCount]);

  // feature gate 关闭时后端不会冻结任何上下文；此时一律按"跳过"提交，避免误导。
  const consumersEnabled = bootstrap?.consumers_enabled ?? true;
  const effectiveSkipped = skipped || !consumersEnabled;

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
            确认 P1–P4 的 Team A/B 归属与初始端位，任务创建时会冻结这份名册。跳过不影响普通分析。
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

      {bootstrap?.reference_frame_url ? (
        <figure className="mt-4 overflow-hidden rounded-xl border border-[#DDE9D6] bg-white" data-testid="roster-reference-frame">
          <div className="relative mx-auto w-fit max-w-full" data-testid="roster-reference-frame-canvas">
            <img
              src={bootstrap.reference_frame_url}
              alt={`候选参考帧（${bootstrap.reference_timestamp_ms}ms）`}
              className="block max-h-64 max-w-full bg-slate-950 object-contain"
              onLoad={(event) => {
                const { naturalWidth, naturalHeight } = event.currentTarget;
                if (naturalWidth > 0 && naturalHeight > 0) {
                  setReferenceFrameSize({
                    width: naturalWidth,
                    height: naturalHeight,
                    url: bootstrap.reference_frame_url ?? "",
                  });
                }
              }}
            />
            {referenceFrameSize?.url === bootstrap.reference_frame_url ? (
              <svg
                className="pointer-events-none absolute inset-0 h-full w-full"
                viewBox={`0 0 ${referenceFrameSize.width} ${referenceFrameSize.height}`}
                preserveAspectRatio="none"
                aria-hidden="true"
                data-testid="roster-reference-overlay"
              >
                {bootstrap.candidates.map((candidate, index) => {
                  const box = validAnchorBox(candidate);
                  if (!box) return null;
                  const [x1, y1, x2, y2] = box;
                  const color = ANCHOR_COLORS[index % ANCHOR_COLORS.length];
                  const label = `P${index + 1}`;
                  return (
                    <g key={candidate.canonical_player_id} data-testid={`roster-anchor-${candidate.canonical_player_id}`}>
                      <rect
                        x={x1}
                        y={y1}
                        width={x2 - x1}
                        height={y2 - y1}
                        fill={color}
                        fillOpacity="0.16"
                        stroke={color}
                        strokeWidth={Math.max(2, referenceFrameSize.width / 480)}
                      />
                      <text
                        x={x1 + 4}
                        y={Math.max(16, y1 - 5)}
                        fill={color}
                        fontSize={Math.max(14, referenceFrameSize.width / 64)}
                        fontWeight="700"
                        paintOrder="stroke"
                        stroke="white"
                        strokeWidth="4"
                        strokeLinejoin="round"
                      >
                        {label}
                      </text>
                    </g>
                  );
                })}
              </svg>
            ) : null}
          </div>
          <figcaption className="px-3 py-2 text-[11px] text-slate-500">
            候选参考帧 · {bootstrap.reference_timestamp_ms}ms。标框对应候选 P1–P4；画面只用于确认身份，Team A/B 与初始端位仍由你确认。
          </figcaption>
        </figure>
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
              return (
                <div
                  key={playerId}
                  className="rounded-xl border border-[#DDE9D6] bg-white p-3"
                  data-testid={`roster-candidate-${playerId}`}
                  data-team-assignment={teamId ?? "unassigned"}
                  data-has-anchor={candidate?.anchor_court_xy ? "true" : "false"}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-[#14241B]">{formatPlayerId(playerId)}</span>
                    {candidate?.confidence != null ? (
                      <span className="text-[11px] text-slate-400">置信度 {(candidate.confidence * 100).toFixed(0)}%</span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {candidate?.display_name || (candidate ? "已识别候选" : "未识别，待手工补全")}
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
                          <option
                            key={option.canonical_player_id}
                            value={option.canonical_player_id}
                            disabled={usedByAnotherSlot}
                          >
                            {option.display_name || option.canonical_player_id}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                  {candidate?.anchor_court_xy ? (
                    <p className="mt-1 text-[11px] text-slate-400">
                      锚点 {candidate.anchor_timestamp_ms}ms · 球场坐标 ({candidate.anchor_court_xy[0].toFixed(1)},{" "}
                      {candidate.anchor_court_xy[1].toFixed(1)}) ft
                    </p>
                  ) : null}
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

          {courtEnd && entries.every((entry) => entry.team_id) ? (
            <p className="mt-3 flex items-center gap-2 text-xs text-[#168A34]" data-testid="roster-ready">
              <CheckCircle2 size={14} />
              将冻结 {entries.length} 名球员的名册与初始端位。
            </p>
          ) : (
            <p className="mt-3 text-xs text-slate-500" data-testid="roster-incomplete">
              尚未完整：需为每名球员指定 Team 并选择初始端位，或直接跳过。
            </p>
          )}
        </>
      )}
    </section>
  );
}
