import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowLeft, CircleDot, Loader2, Route, SlidersHorizontal } from "lucide-react";
import type { AppPath, NavigateFn } from "../app/navigationTypes";
import { PageFrame } from "../components/PageFrame";
import { BallTrajectoryScene } from "../components/platform/BallTrajectoryScene";
import {
  getAnalysisJob,
  getAnalysisResult,
  getBallTrajectory,
} from "../services/analysisClient";
import {
  buildBallTrajectoryVisualization,
  type BallTrajectoryVisualizationData,
  type EstimatedBallTrajectory,
} from "../services/ballTrajectoryVisualization";
import { isPipelineResult } from "../services/pipelineReportAdapter";
import type { AnalysisJobSummary } from "../types/report";

type LoadState = "loading" | "available" | "empty" | "failed";
type ConfidenceFilter = "all" | "high";
type DisplayLimit = 12 | 24 | 48 | "all";

interface BallTrajectoryPageProps {
  jobId: string;
  onNavigate: NavigateFn;
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

export function BallTrajectoryPage({ jobId, onNavigate }: BallTrajectoryPageProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [job, setJob] = useState<AnalysisJobSummary | null>(null);
  const [data, setData] = useState<BallTrajectoryVisualizationData | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [webGlError, setWebGlError] = useState("");
  const [filter, setFilter] = useState<ConfidenceFilter>("all");
  const [displayLimit, setDisplayLimit] = useState<DisplayLimit>(24);
  const [selectedTrajectoryId, setSelectedTrajectoryId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      try {
        const [nextJob, rawResult] = await Promise.all([getAnalysisJob(jobId), getAnalysisResult(jobId)]);
        const result = isPipelineResult(rawResult) ? rawResult : null;
        if (!nextJob) throw new Error("分析任务不存在或已被删除");
        if (!result) throw new Error("该任务尚未生成可读取的分析结果");

        const trajectoryArtifact = await getBallTrajectory(result);
        const nextData = buildBallTrajectoryVisualization(trajectoryArtifact);
        if (!alive) return;
        setJob(nextJob);
        setData(nextData);
        setSelectedTrajectoryId(nextData.trajectories[0]?.id ?? null);
        setLoadState(nextData.trajectories.length ? "available" : "empty");
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

  const filteredTrajectories = useMemo(() => {
    const filtered = (data?.trajectories ?? []).filter((trajectory) => filter === "all" || trajectory.highConfidence);
    return displayLimit === "all" ? filtered : filtered.slice(-displayLimit);
  }, [data, displayLimit, filter]);

  const effectiveSelectedTrajectoryId = filteredTrajectories.some((trajectory) => trajectory.id === selectedTrajectoryId)
    ? selectedTrajectoryId
    : filteredTrajectories[0]?.id ?? null;
  const selectedTrajectory = filteredTrajectories.find((trajectory) => trajectory.id === effectiveSelectedTrajectoryId) ?? null;
  const totalDuration = data?.trajectories.reduce((total, trajectory) => total + trajectory.durationSeconds, 0) ?? 0;
  const highConfidenceCount = data?.trajectories.filter((trajectory) => trajectory.highConfidence).length ?? 0;
  const handleSelectTrajectory = useCallback((trajectoryId: string) => setSelectedTrajectoryId(trajectoryId), []);
  const handleWebGlError = useCallback((message: string) => setWebGlError(message), []);
  const visionPath = `/analysis/${jobId}/vision` as AppPath;

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
            <button className="green-button mt-6 px-4 py-2.5" onClick={() => onNavigate(visionPath)} type="button">
              返回视觉分析
            </button>
          </div>
        </div>
      </PageFrame>
    );
  }

  return (
    <PageFrame>
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
          <Metric label="球路" value={`${data?.trajectories.length ?? 0}`} />
          <Metric label="较高可信" value={`${highConfidenceCount}`} />
          <Metric label="累计时长" value={`${totalDuration.toFixed(1)}s`} />
        </div>
      </header>

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
              selectedTrajectoryId={effectiveSelectedTrajectoryId}
              onSelectTrajectory={handleSelectTrajectory}
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
              <Legend color="#A7B0AA" label="插值点" dot />
            </div>
          </section>

          {selectedTrajectory ? (
            <section className="border-b border-[#E4E7EC] py-4" aria-live="polite">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-bold text-[#182230]">球路 {selectedTrajectory.sequence}</h2>
                <span className={`rounded-md px-2 py-1 text-[11px] font-bold ${selectedTrajectory.highConfidence ? "bg-[#EAF8F0] text-[#168A34]" : "bg-[#F2F4F7] text-[#667085]"}`}>
                  {selectedTrajectory.highConfidence ? "较高可信" : "谨慎参考"}
                </span>
              </div>
              <dl className="mt-3 grid gap-2 text-xs">
                <Detail label="方向" value={directionLabel(selectedTrajectory)} />
                <Detail label="时间" value={`${formatTime(selectedTrajectory.startTimeSeconds)} – ${formatTime(selectedTrajectory.endTimeSeconds)}`} />
                <Detail label="持续" value={`${selectedTrajectory.durationSeconds.toFixed(2)} 秒`} />
                <Detail label="轨迹点" value={`${selectedTrajectory.pointCount}`} />
                <Detail label="平均置信" value={confidenceLabel(selectedTrajectory.averageConfidence)} />
                <Detail label="插值比例" value={`${Math.round(selectedTrajectory.interpolatedRatio * 100)}%`} />
              </dl>
            </section>
          ) : null}

          <section className="pt-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-sm font-bold text-[#182230]">可见球路</h2>
              <span className="text-xs text-[#98A2B3]">{filteredTrajectories.length}</span>
            </div>
            <div className="max-h-64 space-y-1 overflow-y-auto pr-1 xl:max-h-[calc(100vh-620px)] xl:min-h-36">
              {filteredTrajectories.map((trajectory) => (
                <button
                  className={`flex min-h-12 w-full items-center gap-3 rounded-md px-2.5 py-2 text-left transition ${trajectory.id === effectiveSelectedTrajectoryId ? "bg-[#EAF8F0]" : "hover:bg-[#F7F9F8]"}`}
                  key={trajectory.id}
                  onClick={() => setSelectedTrajectoryId(trajectory.id)}
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

function Legend({ color, label, dot = false }: { color: string; label: string; dot?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <span className={`${dot ? "size-2 rounded-full" : "h-0.5 w-4"}`} style={{ backgroundColor: color }} />
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
