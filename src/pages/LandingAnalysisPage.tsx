import { useEffect, useMemo, useState } from "react";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { LandingCourtMap } from "../components/platform/landing/LandingCourtMap";
import { LandingZoneGrid } from "../components/platform/landing/LandingZoneGrid";
import { getAnalysisResult, getShotLandings } from "../services/analysisClient";
import { ALL_LANDING_FILTERS, filterLandings, groupLandingStatuses, landingSummary, type LandingFilters } from "../services/landingVisualization";
import { isPipelineResult } from "../services/pipelineReportAdapter";
import type { ShotLanding, ShotLandingsArtifact } from "../types/shotLandings";

const STATUS_LABEL: Record<string, string> = { available: "有坐标", no_bounce_before_next_contact: "下一次触球前无弹地", bounce_without_court_coordinate: "弹地但无坐标", ambiguous_bounce: "弹地点存在歧义", unavailable: "不可用" };

export function LandingAnalysisPage({ jobId, onNavigate, videoPath }: { jobId: string; onNavigate: NavigateFn; embedded?: boolean; videoPath: (timeMs: number) => NavigatePath }) {
  const [artifact, setArtifact] = useState<ShotLandingsArtifact | null>(null);
  const [error, setError] = useState<string>();
  const [filters, setFilters] = useState<LandingFilters>(ALL_LANDING_FILTERS);
  const [selectedId, setSelectedId] = useState<string>();
  useEffect(() => {
    let alive = true;
    getAnalysisResult(jobId).then((result) => {
      if (!isPipelineResult(result)) throw new Error("该任务没有可读取的分析结果");
      return getShotLandings(result);
    }).then((value) => { if (alive) setArtifact(value); }).catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : "落点数据加载失败"); });
    return () => { alive = false; };
  }, [jobId]);
  const shown = useMemo(() => artifact ? filterLandings(artifact.landings, filters) : [], [artifact, filters]);
  const selected = shown.find((item) => item.shot_id === selectedId) ?? shown[0];
  if (error) return <State title="落点分析加载失败" detail={error} />;
  if (!artifact) return <State title="正在加载落点分析…" />;
  if (artifact.status === "failed") return <State title="落点组合失败" detail={artifact.detail} />;
  if (artifact.status !== "available") return <State title="本次分析暂无可用落点" detail={artifact.detail} />;
  const summary = landingSummary(artifact, shown); const statuses = groupLandingStatuses(shown);
  const options = (key: keyof ShotLanding) => [...new Set(artifact.landings.map((item) => item[key]).filter(Boolean) as string[])];
  return <div className="space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-black">球落点分析</h2><p className="text-xs text-slate-500">连续坐标为永久事实；项目十二区由 project12.v1 派生。论文六区待配置。</p></div><button disabled className="rounded-lg border px-3 py-2 text-xs text-slate-400">论文六区 · 待配置</button></div>
    <div className="flex flex-wrap gap-2 rounded-xl border bg-white p-3">
      <Select label="球员" value={filters.player} values={options("hitter_player_id")} onChange={(player) => setFilters({ ...filters, player })} />
      <Select label="回合" value={filters.rally} values={options("rally_id")} onChange={(rally) => setFilters({ ...filters, rally })} />
      <Select label="拍序" value={filters.stage} values={options("shot_stage")} onChange={(stage) => setFilters({ ...filters, stage })} />
      <label className="text-xs font-bold">最低置信度 <input className="ml-2 w-20" type="number" min="0" max="1" step="0.1" value={filters.minConfidence} onChange={(event) => setFilters({ ...filters, minConfidence: Number(event.target.value) })} /></label>
    </div>
    <div className="grid gap-3 sm:grid-cols-4">{[["当前筛选", `${summary.displayed}/${summary.total}`], ["有坐标", summary.measurable], ["可入十二区", summary.zoned], ["无弹地", statuses.no_bounce_before_next_contact]].map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><div className="text-xs text-slate-500">{label}</div><div className="text-2xl font-black">{value}</div></div>)}</div>
    {shown.length === 0 ? <State title="当前筛选下没有落点" detail="可降低置信度或清除筛选条件。" /> : <div className="grid gap-5 lg:grid-cols-2"><div className="rounded-2xl border bg-white p-4"><LandingCourtMap landings={shown} selectedId={selected?.shot_id} onSelect={setSelectedId} /><p className="mt-2 text-xs text-slate-500">黄：对方半场；蓝：己方半场；橙：界外。界外坐标保留且不裁剪。</p></div><div className="rounded-2xl border bg-white p-4"><h3 className="mb-3 font-black">项目十二区</h3><LandingZoneGrid landings={shown} /></div></div>}
    <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]"><div className="max-h-96 overflow-auto rounded-2xl border bg-white"><table className="w-full text-left text-xs"><thead><tr className="border-b"><th className="p-3">Shot</th><th>状态</th><th>区域</th></tr></thead><tbody>{shown.map((item) => <tr key={item.shot_id} onClick={() => setSelectedId(item.shot_id)} className={`cursor-pointer border-b ${selected?.shot_id === item.shot_id ? "bg-emerald-50" : ""}`}><td className="p-3 font-bold">{item.shot_id}</td><td>{STATUS_LABEL[item.landing_status]}</td><td>{item.zone_12 ?? (item.court_location === "outside_court" ? "界外" : item.target_relation === "own_half" ? "己方" : "—")}</td></tr>)}</tbody></table></div>{selected ? <Detail item={selected} onVideo={() => onNavigate(videoPath(Math.max(0, (selected.timestamp_ms ?? 0) - 1200)), { replace: true })} /> : null}</div>
  </div>;
}

function Select({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (value: string) => void }) { return <label className="text-xs font-bold">{label} <select className="ml-1 rounded border p-1" value={value} onChange={(event) => onChange(event.target.value)}><option value="all">全部</option>{values.map((item) => <option key={item}>{item}</option>)}</select></label>; }
function State({ title, detail }: { title: string; detail?: string }) { return <div className="rounded-2xl border border-dashed bg-white p-16 text-center"><p className="font-black">{title}</p>{detail ? <p className="mt-2 text-xs text-slate-500">{detail}</p> : null}</div>; }
function Detail({ item, onVideo }: { item: ShotLanding; onVideo: () => void }) { const rows = [["Shot", item.shot_id], ["Rally", item.rally_id], ["拍序", item.ordinal_in_rally], ["球员", item.hitter_player_id], ["时间", item.timestamp_ms == null ? null : `${(item.timestamp_ms / 1000).toFixed(2)} s`], ["绝对坐标", item.landing_x_ft == null ? null : `(${item.landing_x_ft.toFixed(2)}, ${item.landing_y_ft?.toFixed(2)}) ft`], ["十二区", item.zone_12], ["质量", item.bounce_confidence], ["证据", `${item.source_segment_id ?? "—"} / ${item.source_event_id ?? "—"}`]]; return <div className="rounded-2xl border bg-white p-5"><h3 className="font-black">落点详情</h3><dl className="mt-3 grid grid-cols-2 gap-2 text-xs">{rows.map(([key, value]) => <div key={String(key)}><dt className="text-slate-500">{key}</dt><dd className="font-bold">{value ?? "证据不足"}</dd></div>)}</dl><button className="mt-4 rounded-lg bg-emerald-700 px-4 py-2 text-xs font-bold text-white" onClick={onVideo}>查看视频</button></div>; }
