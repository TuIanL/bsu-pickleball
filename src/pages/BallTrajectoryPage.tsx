import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowLeft, CircleDot, Loader2, Route, SlidersHorizontal } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { taskContextForJob, taskListPathForJob, withTaskListContext } from "../app/navigationContext";
import { PageFrame } from "../components/PageFrame";
import { BallTrajectoryScene } from "../components/platform/BallTrajectoryScene";
import {
  getAnalysisJob,
  getAnalysisResult,
  getBallTrajectory,
  getReconstructedBallTrajectory,
} from "../services/analysisClient";
import {
  buildBallTrajectoryVisualization,
  buildReconstructedBallTrajectoryVisualization,
  filterTrajectories,
  type BallTrajectoryVisualizationData,
  type EstimatedBallShot,
  type EstimatedBallTrajectory,
} from "../services/ballTrajectoryVisualization";
import { isPipelineResult } from "../services/pipelineReportAdapter";
import type { AnalysisJobSummary, ReconstructedBallTrajectoryArtifact } from "../types/report";

type LoadState = "loading" | "available" | "empty" | "failed";
type ConfidenceFilter = "all" | "high";
type DisplayLimit = 12 | 24 | 48 | "all";
type PlayerFilter = "all" | "unassigned" | string;

interface BallTrajectoryPageProps {
  jobId: string;
  onNavigate: NavigateFn;
  /** embedded：嵌入 Library Workspace 时隐藏页面级头部外壳（返回按钮/标题） */
  embedded?: boolean;
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.max(0, seconds - minutes * 60);
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(1).padStart(4, "0")}`;
}

function confidenceLabel(value: number | null): string {
  return value === null ? "未知" : `${Math.round(value * 100)}%`;
}

function directionLabel(trajectory: EstimatedBallTrajectory): string {
  return trajectory.direction === "near-to-far" ? "近端 → 远端" : "远端 → 近端";
}

function shotLabel(shot: EstimatedBallShot): string {
  const hitter = shot.hitterPlayerId === null ? "未归属" : shot.hitterPlayerId.replace("Player_", "P");
  return `球路 ${shot.sequence} · ${hitter} · ${shot.segments.length} 个飞行段 · ${shot.durationSeconds.toFixed(1)}s`;
}

function ownershipBadge(status: string): { label: string; className: string } | null {
  switch (status) {
    case "confirmed":
      return { label: "归属确认", className: "bg-[#EAF8F0] text-[#168A34]" };
    case "ambiguous":
      return { label: "归属不明", className: "bg-[#FEF6E7] text-[#B54708]" };
    case "unassigned":
      return { label: "击球者不明", className: "bg-[#F2F4F7] text-[#667085]" };
    case "not_applicable":
      return { label: "无 Shot 上下文", className: "bg-[#F2F4F7] text-[#667085]" };
    default:
      return null;
  }
}

export function BallTrajectoryPage({ jobId, onNavigate, embedded }: BallTrajectoryPageProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [v3Artifact, setV3Artifact] = useState<ReconstructedBallTrajectoryArtifact | null>(null);
  const [job, setJob] = useState<AnalysisJobSummary | null>(null);
  const [data, setData] = useState<BallTrajectoryVisualizationData | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [webGlError, setWebGlError] = useState("");
  const [filter, setFilter] = useState<ConfidenceFilter>("all");
  const [playerFilter, setPlayerFilter] = useState<PlayerFilter>("all");
  const [displayLimit, setDisplayLimit] = useState<DisplayLimit>(24);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);

  const roster = useMemo(() => data?.playerRoster ?? [], [data]);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      try {
        const [nextJob, rawResult] = await Promise.all([getAnalysisJob(jobId), getAnalysisResult(jobId)]);
        const result = isPipelineResult(rawResult) ? rawResult : null;
        if (!nextJob) throw new Error("分析任务不存在或已被删除");
        if (!result) throw new Error("该任务尚未生成可读取的分析结果");

        const trajectoryArtifact = await getReconstructedBallTrajectory(result);
        const isV3 = trajectoryArtifact?.reconstruction_mode === "multiview_estimated_3d";
        setV3Artifact(isV3 ? trajectoryArtifact : null);
        let nextData = buildReconstructedBallTrajectoryVisualization(trajectoryArtifact);
        // v3（多视角估算 3D）：即使可视化尚空，也按整体状态展示 v3 面板 + 明确降级，
        // 不伪造 2.5D；非 v3 且无轨迹时才降级到原始轨迹模式。
        if (!isV3 && nextData.trajectories.length === 0) {
          const legacyArtifact = await getBallTrajectory(result);
          nextData = buildBallTrajectoryVisualization(legacyArtifact);
        }
        if (!alive) return;
        setJob(nextJob);
        setData(nextData);
        setSelectedShotId(nextData.shots[0]?.shotId ?? nextData.trajectories[0]?.id ?? null);
        setLoadState(isV3 ? "available" : nextData.trajectories.length ? "available" : "empty");
      } catch (error) {
        if (!alive) return;
        setErrorMessage(error instanceof Error ? error.message : "无法读取球轨迹数据");
        setLoadState("failed");
      }
    };

    load();
    return () => {
      alive = false;
    };
  }, [jobId]);

  const { trajectories: filteredTrajectories, shots: filteredShots } = useMemo(
    () => filterTrajectories(data?.trajectories ?? [], data?.shots ?? [], {
      playerFilter,
      confidence: filter,
      displayLimit,
    }),
    [data, displayLimit, filter, playerFilter],
  );

  const effectiveSelectedShotId = useMemo(() => {
    if (selectedShotId !== null) {
      const matches = filteredTrajectories.some((t) => t.shotId === selectedShotId || t.id === selectedShotId);
      if (matches) return selectedShotId;
    }
    return filteredShots[0]?.shotId ?? filteredTrajectories[0]?.id ?? null;
  }, [filteredShots, filteredTrajectories, selectedShotId]);

  const selectedShot = useMemo(() => {
    if (effectiveSelectedShotId === null) return null;
    const shot = filteredShots.find((s) => s.shotId === effectiveSelectedShotId);
    if (shot) return shot;
    const single = filteredTrajectories.find((t) => t.id === effectiveSelectedShotId);
    return single ? {
      shotId: single.shotId ?? single.id,
      hitterPlayerId: single.hitterPlayerId,
      hitterRenderSlot: single.hitterRenderSlot,
      ownershipStatus: single.ownershipStatus,
      ownershipConfidence: single.ownershipConfidence,
      segmentIds: [single.id],
      segments: [single],
      startTimeSeconds: single.startTimeSeconds,
      endTimeSeconds: single.endTimeSeconds,
      durationSeconds: single.durationSeconds,
      pointCount: single.pointCount,
      sequence: single.sequence,
    } : null;
  }, [effectiveSelectedShotId, filteredShots, filteredTrajectories]);

  const selectedTrajectory = selectedShot?.segments[0] ?? null;
  const totalShots = data?.shots.length ?? 0;
  const highConfidenceShots = data?.shots.filter((shot) => shot.segments.some((segment) => segment.highConfidence)).length ?? 0;
  const totalDuration = data?.shots.reduce((total, shot) => total + shot.durationSeconds, 0) ?? 0;
  const perPlayerCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const shot of data?.shots ?? []) {
      if (shot.hitterPlayerId === null) continue;
      counts.set(shot.hitterPlayerId, (counts.get(shot.hitterPlayerId) ?? 0) + 1);
    }
    return counts;
  }, [data]);

  const handleSelectShot = useCallback((shotId: string | null) => setSelectedShotId(shotId), []);
  const handleWebGlError = useCallback((message: string) => setWebGlError(message), []);
  const visionPath = withTaskListContext(`/analysis/${jobId}/vision`, taskContextForJob(job));

  if (loadState === "loading") {
    return (
      <PageFrame>
        <div className="grid min-h-[62vh] place-items-center text-center">
          <div>
            <Loader2 className="mx-auto animate-spin text-[#168A34]" size={28} aria-hidden="true" />
            <h1 className="mt-4 text-xl font-bold text-[#182230]">正在构建球路</h1>
            <p className="mt-2 text-sm text-[#667085]">读取清洗轨迹并生成球路视图…</p>
          </div>
        </div>
      </PageFrame>
    );
  }

  if (loadState === "failed" || loadState === "empty") {
    const failed = loadState === "failed";
    return (
      <PageFrame>
        <div className="mx-auto grid min-h-[62vh] max-w-xl place-items-center text-center">
          <div>
            <span className="mx-auto grid size-12 place-items-center rounded-lg bg-[#F2F4F7] text-[#667085]">
              {failed ? <AlertCircle size={24} aria-hidden="true" /> : <Route size={24} aria-hidden="true" />}
            </span>
            <h1 className="mt-5 text-2xl font-bold text-[#182230]">{failed ? "球路读取失败" : "暂无可用球路"}</h1>
            <p className="mt-3 text-sm leading-6 text-[#667085]">
              {failed
                ? errorMessage
                : "当前任务没有足够的有效球场坐标形成连续轨迹。可以返回视觉分析检查球检测、轨迹清洗和场地标定状态。"}
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <button className="green-button px-4 py-2.5" onClick={() => onNavigate(taskListPathForJob(job))} type="button">
                返回任务管理
              </button>
              <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(visionPath)} type="button">
                返回视觉分析
              </button>
            </div>
          </div>
        </div>
      </PageFrame>
    );
  }

  return (
    <PageFrame>
      {v3Artifact ? (
        <section className="mb-5 rounded-xl border border-[#16B364]/20 bg-[#EAF8F0]/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-bold text-[#182230]">多视角估算 3D 球路</h3>
            <span className="rounded bg-[#168A34] px-2 py-0.5 text-[10px] font-bold text-white">
              {v3Artifact.overall_status ?? "UNAVAILABLE"}
            </span>
          </div>
          {v3Artifact.overall_status === "UNAVAILABLE" ? (
            <p className="mt-2 text-xs leading-5 text-[#667085]">
              双摄三维证据不足以重建可信 3D 球路，系统未伪造球路。落点/球速按各自可用性单独给出（如有）。
            </p>
          ) : (
            <div className="mt-2 grid gap-2 text-xs text-[#344054] sm:grid-cols-3">
              <div>
                <span className="text-[#98A2B3]">落点</span>
                <div className="font-semibold">
                  {v3Artifact.landing_point?.landing_x_ft != null && v3Artifact.landing_point?.landing_y_ft != null
                    ? `(${v3Artifact.landing_point.landing_x_ft.toFixed(1)}, ${v3Artifact.landing_point.landing_y_ft.toFixed(1)}) ft`
                    : "—"}
                </div>
                <div className="text-[#98A2B3]">{v3Artifact.landing_point?.landing_source ?? "—"}</div>
              </div>
              <div>
                <span className="text-[#98A2B3]">段数</span>
                <div className="font-semibold">{v3Artifact.segments?.length ?? 0}</div>
                <div className="text-[#98A2B3]">
                  {v3Artifact.segments?.[0]?.stereo_coverage != null
                    ? `覆盖率 ${(v3Artifact.segments[0].stereo_coverage * 100).toFixed(0)}%`
                    : "—"}
                </div>
              </div>
              <div>
                <span className="text-[#98A2B3]">平均球速</span>
                <div className="font-semibold">
                  {v3Artifact.segments?.[0]?.metrics?.average_speed_kmh != null
                    ? `${v3Artifact.segments[0].metrics.average_speed_kmh.toFixed(0)} km/h`
                    : "—"}
                </div>
                <div className="text-[#98A2B3]">{v3Artifact.segments?.[0]?.metrics?.average_speed_validity ?? "—"}</div>
              </div>
            </div>
          )}
        </section>
      ) : null}
      {!embedded && (
        <header className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <button
              className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-[#667085] transition hover:text-[#168A34]"
              onClick={() => onNavigate(visionPath)}
              type="button"
            >
              <ArrowLeft size={16} aria-hidden="true" />
              返回视觉分析
            </button>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-[#98A2B3]">任务 {jobId}</span>
            </div>
            <h1 className="mt-3 text-3xl font-black text-[#182230] sm:text-4xl">球路可视化</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#667085]">
              {job?.metadata.matchTitle ?? "比赛分析"}
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 border-y border-[#E4E7EC] py-3 lg:border-y-0 lg:py-0">
            <Metric label="球路（Shot）" value={`${totalShots}`} />
            <Metric label="较高可信" value={`${highConfidenceShots}`} />
            <Metric label="累计时长" value={`${totalDuration.toFixed(1)}s`} />
            {[...perPlayerCounts.entries()].map(([playerId, count]) => (
              <Metric key={playerId} label={playerId.replace("Player_", "P")} value={`${count}`} />
            ))}
          </div>
        </header>
      )}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_304px]">
        <div className="min-w-0">
          {webGlError ? (
            <div className="grid min-h-[430px] place-items-center rounded-lg border border-[#FECACA] bg-[#FFF7F7] p-8 text-center">
              <div>
                <AlertCircle className="mx-auto text-[#D92D20]" size={26} aria-hidden="true" />
                <h2 className="mt-4 text-lg font-bold text-[#182230]">3D 渲染不可用</h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-[#667085]">{webGlError}</p>
              </div>
            </div>
          ) : filteredTrajectories.length ? (
            <BallTrajectoryScene
              trajectories={filteredTrajectories}
              selectedShotId={effectiveSelectedShotId}
              onSelectShot={handleSelectShot}
              onWebGlError={handleWebGlError}
            />
          ) : (
            <div className="grid min-h-[430px] place-items-center rounded-lg border border-[#DDE5E0] bg-[#F8FAF9] p-8 text-center">
              <div>
                <SlidersHorizontal className="mx-auto text-[#667085]" size={24} aria-hidden="true" />
                <h2 className="mt-4 text-lg font-bold text-[#182230]">筛选后没有球路</h2>
                <p className="mt-2 text-sm text-[#667085]">切换到“全部轨迹”以查看低可信度或插值较多的结果。</p>
              </div>
            </div>
          )}
        </div>

        <aside className="min-w-0 border-t border-[#E4E7EC] pt-4 xl:border-l xl:border-t-0 xl:pl-4 xl:pt-0">
          <section className="border-b border-[#E4E7EC] pb-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-bold text-[#182230]">显示设置</h2>
              <SlidersHorizontal size={16} className="text-[#98A2B3]" aria-hidden="true" />
            </div>
            {roster.length > 0 && (
              <div className="mt-3" aria-label="球员筛选">
                <div className="grid grid-cols-3 rounded-lg bg-[#F2F4F7] p-1">
                  {["all", ...roster.map((entry) => entry.player_id)].map((playerId) => (
                    <button
                      aria-pressed={playerFilter === playerId}
                      className={`min-h-9 rounded-md px-1 text-xs font-bold transition ${playerFilter === playerId ? "bg-white text-[#182230] shadow-sm" : "text-[#667085]"}`}
                      key={playerId}
                      onClick={() => setPlayerFilter(playerId)}
                      type="button"
                    >
                      {playerId === "all" ? "全部" : playerId.replace("Player_", "P")}
                    </button>
                  ))}
                </div>
                <button
                  aria-pressed={playerFilter === "unassigned"}
                  className={`mt-2 min-h-9 w-full rounded-md px-2 text-xs font-bold transition ${playerFilter === "unassigned" ? "bg-[#EAF8F0] text-[#168A34]" : "bg-[#F2F4F7] text-[#667085]"}`}
                  onClick={() => setPlayerFilter("unassigned")}
                  type="button"
                >
                  未归属（击球者不明 / 无 Shot 上下文）
                </button>
              </div>
            )}
            <div className="mt-3 grid grid-cols-2 rounded-lg bg-[#F2F4F7] p-1" aria-label="轨迹可信度筛选">
              {(["all", "high"] as ConfidenceFilter[]).map((mode) => (
                <button
                  aria-pressed={filter === mode}
                  className={`min-h-9 rounded-md px-2 text-xs font-bold transition ${filter === mode ? "bg-white text-[#182230] shadow-sm" : "text-[#667085]"}`}
                  key={mode}
                  onClick={() => setFilter(mode)}
                  type="button"
                >
                  {mode === "all" ? "全部轨迹" : "较高可信"}
                </button>
              ))}
            </div>
            <label className="mt-3 flex items-center justify-between gap-3 text-xs font-semibold text-[#667085]">
              场景数量
              <select
                className="h-9 rounded-md border border-[#D0D5DD] bg-white px-2 text-xs text-[#344054] outline-none focus:border-[#25B86A]"
                onChange={(event) => setDisplayLimit(event.target.value === "all" ? "all" : Number(event.target.value) as 12 | 24 | 48)}
                value={displayLimit}
              >
                <option value={12}>最近 12 条</option>
                <option value={24}>最近 24 条</option>
                <option value={48}>最近 48 条</option>
                <option value="all">全部</option>
              </select>
            </label>
          </section>

          <section className="border-b border-[#E4E7EC] py-4">
            <h2 className="text-sm font-bold text-[#182230]">图例</h2>
            <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs text-[#667085]">
              <Legend color="#25B86A" label="近端到远端" />
              <Legend color="#F04438" label="远端到近端" />
              <Legend color="#A7B0AA" label="推算点（虚线）" dash />
              <Legend color="#F97316" label="弹地点（圆环）" ring />
              <Legend color="#8B5CF6" label="击球点（菱形）" diamond />
            </div>
          </section>

          {selectedShot ? (
            <section className="border-b border-[#E4E7EC] py-4" aria-live="polite">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-bold text-[#182230]">球路 {selectedShot.sequence}</h2>
                <span className={`rounded-md px-2 py-1 text-[11px] font-bold ${selectedTrajectory?.highConfidence ? "bg-[#EAF8F0] text-[#168A34]" : "bg-[#F2F4F7] text-[#667085]"}`}>
                  {selectedTrajectory?.highConfidence ? "较高可信" : "谨慎参考"}
                </span>
              </div>
              <dl className="mt-3 grid gap-2 text-xs">
                <Detail label="击球者" value={selectedShot.hitterPlayerId === null ? "未归属" : selectedShot.hitterPlayerId.replace("Player_", "P")} />
                <Detail label="归属" value={ownershipBadge(selectedShot.ownershipStatus)?.label ?? selectedShot.ownershipStatus} />
                <Detail label="归属置信" value={confidenceLabel(selectedShot.ownershipConfidence)} />
                <Detail label="飞行段" value={`${selectedShot.segments.length} 段`} />
                <Detail label="时间" value={`${formatTime(selectedShot.startTimeSeconds)} – ${formatTime(selectedShot.endTimeSeconds)}`} />
                <Detail label="持续" value={`${selectedShot.durationSeconds.toFixed(2)} 秒`} />
                <Detail label="轨迹点" value={`${selectedShot.pointCount}`} />
                {selectedTrajectory ? <Detail label="方向" value={directionLabel(selectedTrajectory)} /> : null}
              </dl>
            </section>
          ) : null}

          <section className="pt-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-sm font-bold text-[#182230]">可见球路</h2>
              <span className="text-xs text-[#98A2B3]">{filteredShots.length || filteredTrajectories.length}</span>
            </div>
            <div className="max-h-64 space-y-1 overflow-y-auto pr-1 xl:max-h-[calc(100vh-620px)] xl:min-h-36">
              {filteredShots.length ? filteredShots.map((shot) => {
                const badge = ownershipBadge(shot.ownershipStatus);
                return (
                  <button
                    className={`flex min-h-12 w-full items-center gap-3 rounded-md px-2.5 py-2 text-left transition ${shot.shotId === effectiveSelectedShotId ? "bg-[#EAF8F0]" : "hover:bg-[#F7F9F8]"}`}
                    key={shot.shotId}
                    onClick={() => setSelectedShotId(shot.shotId)}
                    type="button"
                  >
                    <CircleDot
                      size={15}
                      color={shot.segments[0]?.direction === "near-to-far" ? "#25B86A" : "#F04438"}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <strong className="block text-xs text-[#344054]">{shotLabel(shot)}</strong>
                      <span className="mt-0.5 flex items-center gap-2 text-[11px] text-[#98A2B3]">
                        {badge ? <em className={`rounded px-1.5 py-0.5 text-[10px] font-bold not-italic ${badge.className}`}>{badge.label}</em> : null}
                        {formatTime(shot.startTimeSeconds)} · {shot.pointCount} 点
                      </span>
                    </span>
                  </button>
                );
              }) : filteredTrajectories.map((trajectory) => (
                <button
                  className={`flex min-h-12 w-full items-center gap-3 rounded-md px-2.5 py-2 text-left transition ${trajectory.id === effectiveSelectedShotId ? "bg-[#EAF8F0]" : "hover:bg-[#F7F9F8]"}`}
                  key={trajectory.id}
                  onClick={() => setSelectedShotId(trajectory.id)}
                  type="button"
                >
                  <CircleDot
                    size={15}
                    color={trajectory.direction === "near-to-far" ? "#25B86A" : "#F04438"}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <strong className="block text-xs text-[#344054]">球路 {trajectory.sequence}</strong>
                    <span className="mt-0.5 block truncate text-[11px] text-[#98A2B3]">
                      {formatTime(trajectory.startTimeSeconds)} · {confidenceLabel(trajectory.averageConfidence)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </PageFrame>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-lg font-black text-[#182230]">{value}</div>
      <div className="text-[11px] text-[#98A2B3]">{label}</div>
    </div>
  );
}

function Legend({ color, label, dot = false, dash = false, ring = false, diamond = false }: {
  color: string;
  label: string;
  dot?: boolean;
  dash?: boolean;
  ring?: boolean;
  diamond?: boolean;
}) {
  const marker = diamond ? (
    <span className="inline-block size-2 rotate-45" style={{ backgroundColor: color }} />
  ) : ring ? (
    <span className="inline-block size-2.5 rounded-full border-2" style={{ borderColor: color }} />
  ) : dash ? (
    <span className="inline-block h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: color }} />
  ) : dot ? (
    <span className="size-2 rounded-full" style={{ backgroundColor: color }} />
  ) : (
    <span className="h-0.5 w-4" style={{ backgroundColor: color }} />
  );
  return (
    <span className="flex items-center gap-2">
      {marker}
      {label}
    </span>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-[#98A2B3]">{label}</dt>
      <dd className="text-right font-semibold text-[#475467]">{value}</dd>
    </div>
  );
}
