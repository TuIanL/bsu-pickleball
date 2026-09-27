import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, Video } from "lucide-react";
import type { NavigateFn, NavigatePath, ReportType } from "../../app/navigationTypes";
import { supportedReportTypes } from "../../app/router";
import { taskListPathForJob, taskContextForJob, withTaskListContext } from "../../app/navigationContext";
import type { LibraryView } from "../library/viewCapabilities";
import {
  getCaptureTake,
  getFormalSegmentationSummary,
  listSegments,
} from "../../services/analysisClient";
import type { ReportCapability } from "../../services/reportCapability";
import type {
  AnalysisJobSummary,
  AnalysisReport,
  CaptureSegmentSummary,
  CaptureTakeSummary,
  FormalSegmentationSummary,
} from "../../types/report";
import {
  buildAutoRallySegments,
  type AutoRallySegment,
} from "../../hooks/useAutoRallyPlayback";

type SegmentFilter = "all" | "set" | "game" | "rally";
type LoadState = "idle" | "loading" | "loaded" | "failed" | "unavailable";

interface AnalysisSegmentPanelProps {
  job: AnalysisJobSummary | null | undefined;
  activeRallyId: string | null;
  onRallySelect: (rally: AutoRallySegment) => void;
  onPlaybackDataChange: (rallies: AutoRallySegment[], unavailableReason: string | null) => void;
  reportActions: AnalysisReport["reportActions"];
  reportCapability: ReportCapability;
  reportPath: (type: ReportType) => NavigatePath;
  onNavigate: NavigateFn;
  embedded?: boolean;
  onSelectView?: (view: LibraryView) => void;
}

const FILTERS: Array<{ id: SegmentFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "set", label: "盘" },
  { id: "game", label: "局" },
  { id: "rally", label: "分" },
];

export function AnalysisSegmentPanel({
  job,
  activeRallyId,
  onRallySelect,
  onPlaybackDataChange,
  reportActions,
  reportCapability,
  reportPath,
  onNavigate,
  embedded = false,
  onSelectView,
}: AnalysisSegmentPanelProps) {
  const captureTakeId = job?.metadata.capture_take_id ?? null;
  const [take, setTake] = useState<CaptureTakeSummary | null>(null);
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const [summary, setSummary] = useState<FormalSegmentationSummary | null>(null);
  const [takeLoadState, setTakeLoadState] = useState<LoadState>("idle");
  const [segmentsLoadState, setSegmentsLoadState] = useState<LoadState>("idle");
  const [summaryLoadState, setSummaryLoadState] = useState<LoadState>("idle");
  const [filter, setFilter] = useState<SegmentFilter>("all");

  useEffect(() => {
    let alive = true;
    if (!captureTakeId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets data when the selected job changes.
      setTake(null);
      setSegments([]);
      setSummary(null);
      setTakeLoadState("unavailable");
      setSegmentsLoadState("unavailable");
      setSummaryLoadState("unavailable");
      return () => { alive = false; };
    }

    setTake(null);
    setSegments([]);
    setSummary(null);
    setTakeLoadState("loading");
    setSegmentsLoadState("loading");
    setSummaryLoadState("loading");

    void Promise.all([
      getCaptureTake(captureTakeId)
        .then((value) => {
          if (!alive) return;
          setTake(value);
          setTakeLoadState("loaded");
        })
        .catch(() => {
          if (!alive) return;
          setTakeLoadState("failed");
        }),
      listSegments(captureTakeId)
        .then((value) => {
          if (!alive) return;
          setSegments(value ?? []);
          setSegmentsLoadState("loaded");
        })
        .catch(() => {
          if (!alive) return;
          setSegments([]);
          setSegmentsLoadState("failed");
        }),
      getFormalSegmentationSummary(captureTakeId)
        .then((value) => {
          if (!alive) return;
          setSummary(value);
          setSummaryLoadState("loaded");
        })
        .catch(() => {
          if (!alive) return;
          setSummary(null);
          setSummaryLoadState("failed");
        }),
    ]);
    return () => { alive = false; };
  }, [captureTakeId]);

  const autoRallySegments = useMemo(
    () => buildAutoRallySegments(segments, summary?.run_id),
    [segments, summary?.run_id],
  );
  const autoSkipUnavailableReason = !captureTakeId
    ? "该分析不关联采集片段"
    : summaryLoadState === "failed"
      ? "正式切分摘要暂不可用"
      : segmentsLoadState === "failed"
        ? "片段列表暂不可用"
        : !summary?.run_id
          ? "无正式切分结果"
          : autoRallySegments.length === 0
            ? "当前切分结果没有自动回合"
            : null;

  useEffect(() => {
    onPlaybackDataChange(autoRallySegments, autoSkipUnavailableReason);
  }, [autoRallySegments, autoSkipUnavailableReason, onPlaybackDataChange]);

  const filteredSegments = useMemo(() => segments
    .filter((segment) => segment.edit_status === "active")
    .filter((segment) => filter === "all" || segment.segment_type === filter)
    .sort((left, right) =>
      (left.effective_start_ms ?? left.start_ms) - (right.effective_start_ms ?? right.start_ms)),
  [filter, segments]);
  const modelSegments = filteredSegments.filter((segment) =>
    segment.source === "algorithm"
      && (summary?.run_id
        ? segment.segmentation_run_id === summary.run_id
        : summaryLoadState === "failed"),
  );
  const manualSegments = filteredSegments.filter((segment) =>
    segment.source !== "algorithm" && !segment.segmentation_run_id,
  );

  const handleDetails = useCallback(() => {
    if (!job?.id) return;
    if (embedded && onSelectView) onSelectView("technical");
    else onNavigate(withTaskListContext(`/analysis/${job.id}/details`, taskContextForJob(job)));
  }, [embedded, job, onNavigate, onSelectView]);

  const status = summary?.status;
  const statusLabel = status === "succeeded" || status === "valid_no_rallies"
    ? "正式结果"
    : status && status !== "unavailable"
      ? formatSegmentationStatus(status)
      : null;
  const supportedActions = reportActions.filter((action) => supportedReportTypes.includes(action.type));

  return (
    <aside className="grid min-w-0 content-start gap-4">
      <section className="sport-card min-w-0 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[var(--ui-brand-deep)]">素材片段</p>
            <h2 className="mt-1 text-lg font-black text-[var(--ui-ink)]">回合与标记</h2>
          </div>
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[var(--ui-brand-solid)]/12 text-[var(--ui-brand-deep)]">
            <Video size={17} aria-hidden="true" />
          </span>
        </div>

        <div aria-label="片段类型筛选" className="mt-4 flex flex-wrap gap-2" role="group">
          {FILTERS.map((item) => (
            <button
              aria-pressed={filter === item.id}
              className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${filter === item.id ? "bg-[var(--ui-info-solid)] text-white" : "bg-[var(--ui-surface-neutral)] text-slate-600 hover:bg-[var(--ui-surface-green-tint)]"}`}
              key={item.id}
              onClick={() => setFilter(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>

        {!captureTakeId ? (
          <div className="mt-4 rounded-xl border border-dashed border-[var(--ui-border)] bg-[var(--ui-surface)] p-3 text-sm text-slate-600" role="status">
            该素材无片段数据：此分析没有关联采集片段。
          </div>
        ) : null}

        {captureTakeId && takeLoadState === "failed" ? (
          <p className="mt-3 text-xs text-amber-700" role="status">素材详情暂不可用；片段与切分摘要仍会单独显示。</p>
        ) : null}
        {takeLoadState === "loaded" && take?.duration_ms != null ? (
          <p className="mt-2 text-[11px] text-slate-500">素材时长 {formatMs(take.duration_ms)}</p>
        ) : null}

        <section aria-label="自动回合切分摘要" className="mt-4 border-y border-[var(--ui-border)] py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-black text-[var(--ui-ink)]">自动回合切分（只读）</h3>
            {statusLabel ? (
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${status === "succeeded" || status === "valid_no_rallies" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
                {statusLabel}
              </span>
            ) : null}
          </div>
          {summaryLoadState === "loading" ? (
            <p className="mt-2 text-xs text-slate-500">正在读取正式切分摘要…</p>
          ) : summary && summary.status !== "unavailable" ? (
            <div className="mt-2 grid gap-1 text-[11px] text-slate-500">
              <span>模型 {summary.model_version ?? summary.model_package_id ?? "未知版本"}</span>
              <span>生成于 {formatGeneratedAt(summary.generated_at)}</span>
              <span>{summary.segment_count} 个模型回合</span>
              {summary.detail && !["succeeded", "valid_no_rallies"].includes(summary.status) ? <span className="text-amber-700">{summary.detail}</span> : null}
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-500">尚未生成正式模型结果。</p>
          )}
        </section>

        <section aria-label="模型回合列表" className="mt-3">
          <h3 className="mb-2 text-xs font-black text-[var(--ui-ink)]">模型回合</h3>
          {segmentsLoadState === "loading" ? <p className="text-xs text-slate-500">正在读取片段列表…</p> : null}
          {segmentsLoadState === "failed" ? <p className="text-xs text-amber-700" role="status">片段列表暂不可用。</p> : null}
          {segmentsLoadState === "loaded" && modelSegments.length === 0 ? <p className="text-xs text-slate-500">当前筛选下没有模型片段。</p> : null}
          <div className="grid max-h-[min(34vh,24rem)] gap-1 overflow-y-auto pr-1">
            {modelSegments.map((segment) => {
              const rally = autoRallySegments.find((item) => item.id === segment.id);
              const active = activeRallyId === segment.id;
              const endMs = segment.effective_end_ms ?? segment.end_ms;
              const timeRange = `${formatMs(segment.effective_start_ms ?? segment.start_ms)}→${endMs == null ? "?" : formatMs(endMs)}`;
              return rally ? (
                <button
                  aria-current={active ? "true" : undefined}
                  className={`flex w-full items-center gap-2 rounded-lg border px-2 py-2 text-left transition ${active ? "border-[var(--ui-info)] bg-[var(--ui-info-soft)] ring-1 ring-[var(--ui-info)]/30" : "border-transparent hover:bg-[var(--ui-surface-green-tint)]"}`}
                  key={segment.id}
                  onClick={() => onRallySelect(rally)}
                  title="定位到该回合并开始播放"
                  type="button"
                >
                  <span className="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--ui-ink)]">{segment.label}</span>
                  <span className="shrink-0 text-[10px] tabular-nums text-slate-500">
                    {timeRange}
                  </span>
                </button>
              ) : (
                <div className="flex items-center gap-2 rounded-lg px-2 py-2" key={segment.id}>
                  <span className="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--ui-ink)]">{segment.label}</span>
                  <span className="shrink-0 text-[10px] tabular-nums text-slate-500">
                    {timeRange}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        <section aria-label="拍摄阶段人工标记" className="mt-4 border-t border-[var(--ui-border)] pt-3">
          <h3 className="mb-2 text-xs font-black text-[var(--ui-ink)]">拍摄阶段人工标记</h3>
          {segmentsLoadState === "loaded" && manualSegments.length === 0 ? <p className="text-xs text-slate-500">暂无人工标记。</p> : null}
          <div className="grid max-h-36 gap-1 overflow-y-auto pr-1">
            {manualSegments.map((segment) => {
              const endMs = segment.effective_end_ms ?? segment.end_ms;
              const timeRange = `${formatMs(segment.effective_start_ms ?? segment.start_ms)}→${endMs == null ? "?" : formatMs(endMs)}`;
              return (
                <div className="flex items-center gap-2 rounded-lg bg-[var(--ui-surface)] px-2 py-2" key={segment.id}>
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-[var(--ui-ink)]">{segment.label}</span>
                  <span className="shrink-0 text-[10px] tabular-nums text-slate-500">{timeRange}</span>
                </div>
              );
            })}
          </div>
        </section>
      </section>

      <section className="sport-card p-4">
        <h2 className="text-xs font-bold uppercase tracking-[0.16em] text-[var(--ui-brand-deep)]">下级报告</h2>
        <div className="mt-3 grid gap-2">
          {job?.id ? (
            <button
              className="flex items-center justify-between gap-3 rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/75 px-3 py-2.5 text-left text-sm font-bold text-[var(--ui-ink)] transition hover:border-[var(--ui-brand)]/35 hover:bg-[var(--ui-surface-green-tint)]"
              onClick={handleDetails}
              type="button"
            >
              分析详情 <ChevronRight size={15} aria-hidden="true" />
            </button>
          ) : null}
          {supportedActions.map((action) => (
            <button
              className="flex items-center justify-between gap-3 rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/75 px-3 py-2.5 text-left text-sm font-bold text-[var(--ui-ink)] transition hover:border-[var(--ui-brand)]/35 hover:bg-[var(--ui-surface-green-tint)] disabled:cursor-not-allowed disabled:opacity-45"
              disabled={reportCapability.state !== "available"}
              key={action.type}
              onClick={() => {
                if (reportCapability.state !== "available") return;
                if (embedded && onSelectView) onSelectView("report");
                else onNavigate(reportPath(action.type));
              }}
              title={reportCapability.state === "available" ? undefined : reportCapability.reason}
              type="button"
            >
              {action.title} <ChevronRight size={15} aria-hidden="true" />
            </button>
          ))}
        </div>
        {!embedded ? (
          <button className="quiet-button mt-3 w-full px-3 py-2 text-xs" onClick={() => onNavigate(taskListPathForJob(job))} type="button">
            返回任务管理
          </button>
        ) : null}
      </section>
    </aside>
  );
}

function formatMs(ms: number): string {
  const seconds = Math.floor(Math.max(0, ms) / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function formatGeneratedAt(value: string | null): string {
  if (!value) return "未知时间";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { dateStyle: "short", timeStyle: "short" });
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
