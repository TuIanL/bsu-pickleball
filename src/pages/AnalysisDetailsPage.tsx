import { useState, useEffect, useMemo } from "react";
import { ArrowRight, LineChart } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { taskListPathForJob, withTaskListContext, taskContextForJob } from "../app/navigationContext";
import type { AnalysisJobSummary, AnalysisPipelineResult, AnalysisReport } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { ProjectionReadiness } from "../components/ProjectionReadiness";
import { RailMeta } from "../components/RailMeta";
import { StatusState } from "../components/StatusState";
import { AnalysisJobPage } from "./AnalysisJobPage";
import { demoAnalysisReport as demoReport, getAnalysisJob, getAnalysisReport, getAnalysisResult, getVideoStreamUrl } from "../services/analysisClient";
import { buildCourtTrackSummaries, type CourtTrackSummary } from "../services/courtProjectionTracks";
import { formatPercent, formatSeconds } from "../services/analysisDiagnostics";
import { isPipelineResult } from "../services/pipelineReportAdapter";
import { isActiveAnalysisJob, analysisStatusMeta, cameraAngleLabel, analysisModeLabel, formatDateTime, errorToNotice, formatPlayerId } from "../utils/analysisHelpers";

export function AnalysisDetailsPage({ jobId, onNavigate, embedded }: { jobId: string; onNavigate: NavigateFn; embedded?: boolean }) {
  const { error, job, report, result } = useAnalysisResultReport(jobId);

  if (job === undefined || report === undefined) {
    return <StatusState title="正在加载分析详情" body="正在读取任务元数据、报告和算法结果。" onNavigate={onNavigate} backPath={taskListPathForJob(job)} />;
  }

  if (error) {
    return <StatusState title={error.title} body={error.body} notice={error} onNavigate={onNavigate} backPath={taskListPathForJob(job)} />;
  }

  if (!job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，可能已经被删除。`} onNavigate={onNavigate} backPath={taskListPathForJob(job)} />;
  }

  if (isActiveAnalysisJob(job)) {
    return <AnalysisJobPage jobId={jobId} onNavigate={onNavigate} />;
  }

  if (job.status === "failed") {
    return (
      <StatusState
        title="分析任务失败"
        body={job.publicErrorMessage ?? job.errorMessage ?? "该任务没有生成可用分析详情，请返回任务管理或重新上传。"}
        notice={{
          title: "失败位置",
          body: job.publicErrorMessage ?? job.errorMessage ?? "请重新上传或检查后端日志。",
          detailItems: [
            ["错误码", job.errorCode],
            ["任务 ID", job.id],
            ["失败阶段", job.stages.find((stage) => stage.status === "failed")?.label ?? job.stage],
          ],
        }}
        onNavigate={onNavigate}
        backPath={taskListPathForJob(job)}
      />
    );
  }

  if (job.status === "canceled") {
    return (
      <StatusState
        title="分析任务已取消"
        body="该任务没有生成分析详情。可以返回任务管理删除记录，或重新上传创建新任务。"
        notice={{
          title: "取消记录",
          body: "任务在完成前被取消，保留记录用于追踪执行过程。",
          detailItems: [
            ["任务 ID", job.id],
            ["取消时间", job.canceledAt ? formatDateTime(job.canceledAt) : undefined],
          ],
        }}
        onNavigate={onNavigate}
        backPath={taskListPathForJob(job)}
      />
    );
  }

  const analysis = report ?? demoReport;
  const stageSummary = job.stages.filter((stage) => stage.status === "done").length;
  const trackCount = result?.tracks.length ?? 0;
  const trackIds = new Set(result?.tracks.map((track) => track.track_id) ?? []);
  const hasProjection = trackCount > 0;
  const analysisWindow = result?.analysis_window;
  const returnPath = taskListPathForJob(job);
  const contextualPath = (path: string) => withTaskListContext(path, taskContextForJob(job));
  const formatWindow = (start?: number, end?: number) => (
    start != null && end != null ? `${formatSeconds(start / 1000)} - ${formatSeconds(end / 1000)}` : "未启用"
  );

  return (
    <PageFrame>
      {!embedded && (
        <section className="sport-card overflow-hidden">
          <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.42fr] lg:p-8">
            <div>
              <button
                className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
                onClick={() => onNavigate(returnPath)}
                type="button"
              >
                <ArrowRight className="rotate-180" size={16} aria-hidden="true" />
                返回任务管理
              </button>
              <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
                <LineChart size={16} aria-hidden="true" />
                分析详情
              </p>
              <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">{job.metadata.matchTitle}</h1>
              <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
                当前页面保留任务元数据、算法状态和标准匹克球场二维平面图。坐标转换和人员位移捕捉完成后，会在同一张 20 x 44 ft 球场上投影可视化。
              </p>
            </div>
            <div className="rounded-3xl border border-[#22C55E]/25 bg-[#22C55E]/10 p-6">
              <span className="text-sm font-bold text-[#168A34]">状态摘要</span>
              <strong className="mt-4 block text-4xl font-black text-[#13A12C]">{analysisStatusMeta(job.status).label}</strong>
              <p className="mt-3 text-sm font-semibold leading-6 text-slate-600">
                {stageSummary} 个阶段完成 · {trackIds.size} 条球员轨迹 · {trackCount} 个投影点
              </p>
              <button className="mt-5 green-button w-full" onClick={() => onNavigate(contextualPath(`/analysis/${job.id}/vision`))} type="button">
                打开视频分析
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </section>
      )}

      <section className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_380px]">
        <StandardCourtPlan tracks={result?.tracks ?? []} />
        <aside className="grid gap-5">
          <article className="sport-card p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">任务元数据</p>
            <dl className="mt-4 grid gap-2 text-sm">
              <RailMeta label="视频文件" value={job.metadata.fileName} />
              <RailMeta label="比赛日期" value={job.metadata.matchDate} />
              <RailMeta label="场地" value={job.metadata.venue} />
              <RailMeta label="球员/队伍" value={job.metadata.athleteLabel} />
              <RailMeta label="比赛形式" value={job.metadata.matchFormat === "doubles" ? "双打" : "单打"} />
              <RailMeta label="拍摄角度" value={cameraAngleLabel(job.metadata.cameraAngle)} />
              <RailMeta label="分析模式" value={analysisModeLabel(job.analysisMode)} />
              <RailMeta label="报告 ID" value={analysis.reportId} />
            </dl>
          </article>

          <article className="sport-card p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">投影准备</p>
            <div className="mt-4 grid gap-3">
              <ProjectionReadiness label="四角标定" ready={Boolean(job.calibrationId)} body={job.calibrationId ?? "缺少标定时无法进行真实坐标投影"} />
              <ProjectionReadiness label="球员轨迹" ready={hasProjection} body={hasProjection ? `${trackCount} 个标准球场坐标点` : "尚未生成可用人员位移轨迹"} />
              <ProjectionReadiness label="可视化状态" ready={false} body="热力图、位移轨迹和人员分布后续接入" />
            </div>
          </article>

          <article className="sport-card p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">分析范围</p>
            <dl className="mt-4 grid gap-2 text-sm">
              <RailMeta
                label="请求窗口"
                value={formatWindow(analysisWindow?.requested_clip?.start_ms, analysisWindow?.requested_clip?.end_ms)}
              />
              <RailMeta
                label="实际解码范围"
                value={formatWindow(analysisWindow?.decoded_range?.start_ms, analysisWindow?.decoded_range?.end_ms)}
              />
              <RailMeta
                label="源视频"
                value={
                  analysisWindow?.source_duration_ms != null
                    ? `${formatSeconds(analysisWindow.source_duration_ms / 1000)} · ${analysisWindow.source_frame_count ?? 0} 帧`
                    : "未提供"
                }
              />
              <RailMeta
                label="处理帧数"
                value={analysisWindow?.processed_frame_count != null ? String(analysisWindow.processed_frame_count) : "结果未记录"}
              />
            </dl>
          </article>
        </aside>
      </section>
    </PageFrame>
  );
}

export function StandardCourtPlan({ tracks }: { tracks: AnalysisPipelineResult["tracks"] }) {
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [showFragments, setShowFragments] = useState(false);
  const [inspectedPointKey, setInspectedPointKey] = useState<string | null>(null);
  const trackSummaries = useMemo(() => buildCourtTrackSummaries(tracks), [tracks]);
  const selectedTrack = trackSummaries.find((track) => track.trackId === selectedTrackId);
  const visibleTracks = useMemo(() => {
    const baseTracks = showFragments ? trackSummaries : trackSummaries.filter((track) => !track.isShortFragment);
    const fallbackTracks = baseTracks.length > 0 ? baseTracks : trackSummaries.slice(0, Math.min(trackSummaries.length, 6));
    return fallbackTracks.slice(0, 6);
  }, [showFragments, trackSummaries]);
  const inspectedPoint = (() => {
    if (!inspectedPointKey) {
      return null;
    }

    for (const summary of trackSummaries) {
      const point = summary.sampledPoints.find((item) => courtPointKey(summary.trackId, item) === inspectedPointKey);
      if (point) {
        return { point, summary };
      }
    }

    return null;
  })();
  const highlightedTracks = selectedTrack ? [selectedTrack, ...visibleTracks.filter((track) => track.trackId !== selectedTrack.trackId)] : visibleTracks;
  const hiddenFragmentCount = trackSummaries.filter((track) => track.isShortFragment).length;
  const renderedPointCount = highlightedTracks.reduce((total, track) => total + track.sampledPoints.length, 0);
  const hasProjectedTracks = trackSummaries.length > 0;

  return (
    <article className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">标准球场二维平面图</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">20 ft x 44 ft 投影底图</h2>
        </div>
        <span className="rounded-full border border-[#DDE9D6] bg-white/80 px-3 py-1 text-xs font-black text-slate-500">
          坐标系：x 0-20 · y 0-44
        </span>
      </div>

      <div className="mt-4 rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
        <p className="text-sm font-semibold leading-6 text-slate-600">
          圆点表示算法估计的球员脚点，经过标定投影到标准场地坐标；它们不是球的落点、击球点或人工标注事件。
          轨迹编号来自视觉跟踪器，代表一段检测到的移动轨迹，不等同于确认的球员姓名。
        </p>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(260px,420px)_minmax(0,1fr)]">
        <div className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
          <svg className="mx-auto block aspect-[28/60] max-h-[760px] w-full max-w-[420px]" viewBox="-4 -8 28 60" role="img" aria-label="标准匹克球球场二维平面图（含跟踪缓冲区）">
            <rect x="-4" y="-8" width="28" height="60" rx="0.2" fill="#F0F4EE" stroke="#BCCFBB" strokeWidth="0.12" strokeDasharray="0.6 0.3" />
            <rect x="0" y="0" width="20" height="44" rx="0.2" fill="#DDEFE2" stroke="#173321" strokeWidth="0.24" />
            <rect x="0" y="15" width="20" height="14" fill="#C7E7D5" opacity="0.85" />
            <line x1="0" x2="20" y1="22" y2="22" stroke="#173321" strokeWidth="0.32" />
            <line x1="0" x2="20" y1="15" y2="15" stroke="#173321" strokeWidth="0.22" />
            <line x1="0" x2="20" y1="29" y2="29" stroke="#173321" strokeWidth="0.22" />
            <line x1="10" x2="10" y1="0" y2="15" stroke="#173321" strokeWidth="0.18" />
            <line x1="10" x2="10" y1="29" y2="44" stroke="#173321" strokeWidth="0.18" />

            <text x="10" y="-0.75" textAnchor="middle" fontSize="1.1" fontWeight="800" fill="#173321">远端底线</text>
            <text x="10" y="22.95" textAnchor="middle" fontSize="1.05" fontWeight="800" fill="#173321">Net</text>
            <text x="10" y="45.4" textAnchor="middle" fontSize="1.1" fontWeight="800" fill="#173321">近端底线</text>
            <text x="10" y="18.3" textAnchor="middle" fontSize="1" fontWeight="800" fill="#168A34">非截击区 7 ft</text>
            <text x="5" y="8" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">远端左发球区</text>
            <text x="15" y="8" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">远端右发球区</text>
            <text x="5" y="37" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">近端左发球区</text>
            <text x="15" y="37" textAnchor="middle" fontSize="0.9" fontWeight="700" fill="#315640">近端右发球区</text>

            {hasProjectedTracks ? (
              highlightedTracks.map((summary) => (
                <CourtTrackSvgLayer
                  dimmed={Boolean(selectedTrack && selectedTrack.trackId !== summary.trackId)}
                  inspectedPointKey={inspectedPointKey}
                  key={summary.trackId}
                  onInspectPoint={setInspectedPointKey}
                  selected={selectedTrack?.trackId === summary.trackId}
                  summary={summary}
                />
              ))
            ) : (
              <g>
                <rect x="2.3" y="19.6" width="15.4" height="4.8" rx="0.6" fill="white" opacity="0.88" />
                <text x="10" y="21.35" textAnchor="middle" fontSize="0.86" fontWeight="800" fill="#64748B">
                  暂无人员位移投影
                </text>
                <text x="10" y="22.75" textAnchor="middle" fontSize="0.68" fontWeight="700" fill="#64748B">
                  需要完成标定和球员脚点投影
                </text>
              </g>
            )}
          </svg>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs font-black text-slate-500">
            <span className="rounded-2xl bg-white/80 px-2 py-2">起点：空心圆</span>
            <span className="rounded-2xl bg-white/80 px-2 py-2">最新：实心圆</span>
            <span className="rounded-2xl bg-white/80 px-2 py-2">中间：小点</span>
          </div>
        </div>

        <div className="grid content-start gap-4">
          <div className="grid gap-3 rounded-3xl border border-[#DDE9D6] bg-white/78 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">轨迹图例</p>
                <p className="mt-1 text-sm font-semibold text-slate-500">
                  {trackSummaries.length} 条轨迹 · {tracks.length} 个原始投影点 · 当前绘制 {renderedPointCount} 个采样点
                </p>
              </div>
              <button className="quiet-button px-3 py-2 text-xs" onClick={() => setSelectedTrackId(null)} type="button">
                显示全部
              </button>
            </div>
            <label className="inline-flex items-center gap-2 text-sm font-bold text-slate-600">
              <input checked={showFragments} className="size-4 accent-[#168A34]" onChange={(event) => setShowFragments(event.target.checked)} type="checkbox" />
              显示短片段
              {hiddenFragmentCount > 0 ? <span className="text-xs text-slate-400">({hiddenFragmentCount} 条)</span> : null}
            </label>
            <p className="text-xs font-semibold leading-5 text-slate-500">
              默认优先显示持续时间更长、点数更多的主要轨迹；短片段可能来自遮挡或漏检后的跟丢重连。
            </p>
          </div>

          {hasProjectedTracks ? (
            <div className="grid max-h-[430px] gap-3 overflow-y-auto pr-1">
              {trackSummaries.map((summary) => (
                <button
                  className={`rounded-2xl border p-4 text-left transition ${
                    selectedTrackId === summary.trackId
                      ? "border-[#168A34] bg-[#22C55E]/12 shadow-sm"
                      : "border-[#DDE9D6] bg-white/80 hover:border-[#22C55E]/60"
                  }`}
                  key={summary.trackId}
                  onClick={() => setSelectedTrackId(selectedTrackId === summary.trackId ? null : summary.trackId)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <span className="inline-flex items-center gap-2 text-base font-black text-[#14241B]">
                        <span className="size-3 rounded-full" style={{ backgroundColor: summary.color }} />
                        {summary.label}
                      </span>
                      <p className="mt-1 text-xs font-semibold text-slate-500">身份：{formatPlayerId(summary.trackId) || "—"}</p>
                    </div>
                    {summary.isShortFragment ? (
                      <span className="shrink-0 rounded-full bg-[#FF9500]/12 px-2.5 py-1 text-xs font-black text-[#A45A00]">短片段</span>
                    ) : (
                      <span className="shrink-0 rounded-full bg-[#22C55E]/14 px-2.5 py-1 text-xs font-black text-[#168A34]">主要</span>
                    )}
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-bold text-slate-600">
                    <span>点数 {summary.pointCount}</span>
                    <span>采样 {summary.sampledPoints.length}</span>
                    <span>{formatTrackTimeRange(summary)}</span>
                    <span>置信度 {formatPercent(summary.averageConfidence) ?? "未知"}</span>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-[#DDE9D6] bg-white/72 p-5">
              <p className="text-sm font-black text-[#14241B]">没有可解释的轨迹点</p>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">
                当前任务可能缺少标定、未检测到球员脚点，或后端没有生成标准场地坐标。
              </p>
            </div>
          )}

          <div className="rounded-3xl border border-[#DDE9D6] bg-white/78 p-4">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">点位检查</p>
            {inspectedPoint ? (
              <dl className="mt-3 grid gap-2 text-sm">
                <RailMeta label="轨迹" value={`${inspectedPoint.summary.label} · ${formatPlayerId(inspectedPoint.summary.trackId) || "—"}`} />
                <RailMeta label="时间" value={formatSeconds(inspectedPoint.point.timestamp_seconds) ?? "未知"} />
                <RailMeta label="帧号" value={`#${inspectedPoint.point.frame_index}`} />
                <RailMeta label="场地坐标" value={`x ${inspectedPoint.point.court_point.x.toFixed(2)} ft · y ${inspectedPoint.point.court_point.y.toFixed(2)} ft`} />
                <RailMeta label="置信度" value={formatPercent(inspectedPoint.point.confidence) ?? "未知"} />
              </dl>
            ) : (
              <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">点击场地图上的任意轨迹点，可查看它来自哪条轨迹、哪个时间和哪个标准场地坐标。</p>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function CourtTrackSvgLayer({
  dimmed,
  inspectedPointKey,
  onInspectPoint,
  selected,
  summary,
}: {
  dimmed: boolean;
  inspectedPointKey: string | null;
  onInspectPoint: (key: string) => void;
  selected: boolean;
  summary: CourtTrackSummary;
}) {
  const opacity = dimmed ? 0.24 : 0.9;
  const { insideSegments, outsideSegments } = splitCourtSegments(summary.sampledPoints);

  return (
    <g opacity={opacity}>
      {insideSegments.map((segment, i) => (
        <polyline
          fill="none"
          key={`inside-${i}`}
          points={segment.map((p) => `${p.court_point.x},${p.court_point.y}`).join(" ")}
          stroke={summary.color}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={selected ? 0.42 : 0.28}
        />
      ))}
      {outsideSegments.map((segment, i) => (
        <polyline
          fill="none"
          key={`outside-${i}`}
          points={segment.map((p) => `${p.court_point.x},${p.court_point.y}`).join(" ")}
          stroke={summary.color}
          strokeDasharray="0.25 0.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={selected ? 0.36 : 0.22}
        />
      ))}
      {summary.sampledPoints.map((point) => {
        const key = courtPointKey(summary.trackId, point);
        const inspected = inspectedPointKey === key;
        const inBounds = point.court_point.x >= 0 && point.court_point.x <= 20 && point.court_point.y >= 0 && point.court_point.y <= 44;
        return (
          <circle
            aria-label={`${summary.label} ${formatSeconds(point.timestamp_seconds) ?? `#${point.frame_index}`}`}
            cx={point.court_point.x}
            cy={point.court_point.y}
            fill={inspected ? "#D9FF3F" : inBounds ? summary.color : "#A0C8A5"}
            key={key}
            onClick={() => onInspectPoint(key)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onInspectPoint(key);
              }
            }}
            r={inspected ? 0.36 : inBounds ? (selected ? 0.24 : 0.2) : 0.16}
            role="button"
            stroke="#071008"
            strokeWidth={inspected ? 0.1 : inBounds ? 0.06 : 0.04}
            tabIndex={0}
          />
        );
      })}
      <circle cx={summary.startPoint.court_point.x} cy={summary.startPoint.court_point.y} fill="#F5FAF1" r="0.38" stroke={summary.color} strokeWidth="0.16" />
      <circle cx={summary.latestPoint.court_point.x} cy={summary.latestPoint.court_point.y} fill={summary.color} r="0.42" stroke="#071008" strokeWidth="0.08" />
    </g>
  );
}

function splitCourtSegments(points: AnalysisPipelineResult["tracks"]) {
  const inside: AnalysisPipelineResult["tracks"][] = [];
  const outside: AnalysisPipelineResult["tracks"][] = [];
  let currentInside: AnalysisPipelineResult["tracks"] = [];
  let currentOutside: AnalysisPipelineResult["tracks"] = [];

  for (const point of points) {
    const inBounds = point.court_point.x >= 0 && point.court_point.x <= 20 && point.court_point.y >= 0 && point.court_point.y <= 44;
    if (inBounds) {
      if (currentOutside.length > 0) {
        outside.push(currentOutside);
        currentOutside = [];
      }
      currentInside.push(point);
    } else {
      if (currentInside.length > 0) {
        inside.push(currentInside);
        currentInside = [];
      }
      currentOutside.push(point);
    }
  }
  if (currentInside.length > 0) inside.push(currentInside);
  if (currentOutside.length > 0) outside.push(currentOutside);

  return { insideSegments: inside, outsideSegments: outside };
}

function courtPointKey(trackId: string, point: AnalysisPipelineResult["tracks"][number]) {
  return `${trackId}-${point.frame_index}-${point.timestamp_seconds}`;
}

function formatTrackTimeRange(summary: CourtTrackSummary) {
  const start = formatSeconds(summary.startTimeSeconds);
  const end = formatSeconds(summary.endTimeSeconds);

  if (start && end) {
    return `${start} - ${end}`;
  }
  if (start) {
    return `${start} 起`;
  }
  return "时间未知";
}

export function useAnalysisResultReport(jobId?: string) {
  const [loadedResult, setLoadedResult] = useState<{
    error: DiagnosticNotice | null;
    job: AnalysisJobSummary | null;
    jobId: string;
    report: AnalysisReport | null;
    result: AnalysisPipelineResult | null;
    videoSrc?: string;
  } | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let alive = true;

    const load = async () => {
      try {
        const [nextJob, nextReport, nextResult] = await Promise.all([getAnalysisJob(jobId), getAnalysisReport(jobId), getAnalysisResult(jobId)]);
        const pipelineResult = isPipelineResult(nextResult) ? nextResult : null;
        // real-job 报告只消费权威 /report API；报告缺失时走显式状态，
        // 不再前端拼装近似报告（pipelineReportAdapter 已 deprecated）。
        const adaptedReport = nextReport ?? null;

        if (alive) {
          setLoadedResult({
            error: null,
            job: nextJob,
            jobId,
            report: adaptedReport,
            result: pipelineResult,
            videoSrc: getVideoStreamUrl(pipelineResult?.video_id ?? nextJob?.videoId),
          });
        }
      } catch (error) {
        if (alive) {
          setLoadedResult({
            error: errorToNotice("读取分析结果失败", "无法读取该任务生成的报告或算法结果，请检查后端服务和任务产物。", error),
            job: null,
            jobId,
            report: null,
            result: null,
          });
        }
      }
    };

    load();

    return () => {
      alive = false;
    };
  }, [jobId]);

  if (!jobId) {
    return { error: null, job: null, report: demoReport, result: null, videoSrc: undefined };
  }

  if (loadedResult?.jobId !== jobId) {
    return {
      error: null,
      job: undefined,
      report: undefined,
      result: undefined,
      videoSrc: undefined,
    };
  }

  return {
    error: loadedResult.error,
    job: loadedResult.job,
    report: loadedResult.report,
    result: loadedResult.result,
    videoSrc: loadedResult.videoSrc,
  };
}
