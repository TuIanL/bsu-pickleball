import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type { NavigateFn } from "../../app/navigationTypes";
import type { LibraryItemRef, LibraryItemViewModel, LibraryAnalysisJobView } from "../../services/libraryAdapter";
import { resolveLibraryItemByRef } from "../../services/libraryAdapter";
import { SourceVideoContent } from "./SourceVideoContent";
import { computeLibraryViewCapabilities, resolveViewCapability, type LibraryView } from "./viewCapabilities";
import { VisionPage } from "../../pages/VisionPage";
import { libraryAnalysisEntryPoints, libraryAnalysisPathFor } from "../../services/libraryAnalysisRouting";
import { deleteAnalysisJob, cancelAnalysisJob } from "../../services/analysisClient";

const BallTrajectoryView = lazy(() =>
  import("../../pages/BallTrajectoryPage").then((m) => ({ default: m.BallTrajectoryPage })),
);
const ReportContentView = lazy(() =>
  import("../report/ReportContent").then((m) => ({ default: m.ReportContent })),
);
const RecordingWorkspaceView = lazy(() =>
  import("../../pages/RecordingWorkspacePage").then((m) => ({ default: m.RecordingWorkspacePage })),
);
const SegmentManagerView = lazy(() =>
  import("../../pages/SegmentManagerPage").then((m) => ({ default: m.SegmentManagerPage })),
);
const MultiviewObservabilityView = lazy(() =>
  import("../../pages/MultiviewObservabilityPage").then((m) => ({ default: m.MultiviewObservabilityPage })),
);
const AnalysisDetailsView = lazy(() =>
  import("../../pages/AnalysisDetailsPage").then((m) => ({ default: m.AnalysisDetailsPage })),
);

const VIEW_TABS: { key: LibraryView; label: string }[] = [
  { key: "overview", label: "概览" },
  { key: "video", label: "视频" },
  { key: "analysis", label: "数据分析" },
  { key: "trajectory", label: "球路" },
  { key: "report", label: "报告" },
  { key: "segments", label: "片段" },
  { key: "technical", label: "技术详情" },
];

interface LibraryItemWorkspaceProps {
  kind: LibraryItemRef["kind"];
  sourceId: string;
  view: LibraryView;
  onNavigate: NavigateFn;
}

export function LibraryItemWorkspace({ kind, sourceId, view, onNavigate }: LibraryItemWorkspaceProps) {
  const [item, setItem] = useState<LibraryItemViewModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  const ref: LibraryItemRef = { kind, sourceId };

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 重新请求时重置加载态
    setLoading(true);
    // 按 ref 单条直查，不跑全量 buildLibraryItems（那会拉全部 580 视频 + 33 sync，
    // 在 workspace 这个「已知单个素材」的场景是重负载且非必要）。单条解析最稳健、最快。
    resolveLibraryItemByRef({ kind, sourceId })
      .then((resolved) => {
        if (!cancelled) setItem(resolved);
      })
      .catch(() => {
        if (!cancelled) setItem(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, sourceId, reloadToken]);

  // D14：无成功分析时，结果类 view 落到 overview + 待分析提示（stable fallback，不空白）
  const hasAnalysis = item?.primaryAnalysisJobId != null;
  // P1C：view capability 门控 —— 非法 view（该 source 不支持）→ replace 到 overview；
  //       合法但缺产物 → 停在原 view 显示缺产物提示；可达 → 正常渲染。
  const caps = useMemo(() => (item ? computeLibraryViewCapabilities(item) : null), [item]);
  const resolution = !item || view === "overview" ? "available" : caps ? resolveViewCapability(item, view, caps) : "loading";
  const effectiveView: LibraryView = resolution === "invalid" ? "overview" : view;
  const missingReason = caps?.reasons?.[view];

  // 非法 view：修正 URL 回到 overview，避免 URL/UI 二次不一致
  useEffect(() => {
    if (item && view !== "overview" && resolution === "invalid") {
      onNavigate(`/library/${ref.kind}/${encodeURIComponent(ref.sourceId)}?view=overview`, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item, resolution, view, ref.kind, ref.sourceId]);

  const goView = (v: LibraryView) => {
    // D3：view 切换用 replace（同一素材对象内）
    onNavigate(`/library/${ref.kind}/${encodeURIComponent(ref.sourceId)}?view=${v}`, { replace: true });
  };

  const title = item?.title ?? (ref.kind === "upload" ? "上传视频" : ref.kind === "recording" ? "录制" : "双摄录制");

  if (loading) {
    return <div className="grid min-h-[60vh] place-items-center text-sm text-[var(--capture-text-muted,#8f9d96)]">加载素材…</div>;
  }

  if (!item) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <p className="text-sm font-bold text-[var(--capture-text-secondary,#64736c)]">未找到该素材</p>
        <button className="mt-4 text-sm font-bold text-[var(--capture-brand-primary,#23985b)]" onClick={() => onNavigate("/library")} type="button">
          返回比赛库
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--capture-surface-soft,#f7faf8)]">
      {/* 顶栏 */}
      <div className="border-b border-[var(--capture-border-default,#d9e3dd)]">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
          <button
            className="mb-3 inline-flex items-center gap-1 text-xs font-bold text-[var(--capture-text-secondary,#64736c)] hover:text-[var(--capture-text-primary,#182b24)]"
            onClick={() => onNavigate("/library")}
            type="button"
          >
            <ArrowLeft size={14} aria-hidden="true" />
            比赛库
          </button>
          <h1 className="text-xl font-black text-[var(--capture-text-primary,#182b24)]">{title}</h1>
          <p className="mt-1 text-xs text-[var(--capture-text-secondary,#64736c)]">
            {item.matchFormat === "singles" ? "单打" : item.matchFormat === "doubles" ? "双打" : ""}
            {item.cameraSetup ? ` · ${item.cameraSetup === "dual" ? "双摄" : "单摄"}` : ""}
            {item.startedAt ? ` · ${new Date(item.startedAt).toLocaleString("zh-CN", { hour12: false })}` : ""}
          </p>
        </div>

        {/* Tab 栏 */}
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="flex gap-1 overflow-x-auto">
            {VIEW_TABS.map((tab) => {
              // P1C：素材层面结果类 view 依据 capability 门控，缺产物时不可点。
              // video 例外：availability 不可用时不禁用（内容区给出明确不可用提示）。
              const lockable = ["analysis", "trajectory", "report", "segments", "technical"].includes(tab.key);
              const locked = Boolean(caps && lockable && caps[tab.key as Exclude<LibraryView, "overview">] !== "available");
              return (
                <button
                  key={tab.key}
                  disabled={locked}
                  className={`-mb-px shrink-0 border-b-2 px-4 py-2.5 text-sm font-bold transition disabled:cursor-not-allowed disabled:text-[var(--capture-text-muted,#8f9d96)]/60 ${effectiveView === tab.key ? "border-[var(--capture-brand-primary,#23985b)] text-[var(--capture-brand-primary,#23985b)]" : "border-transparent text-[var(--capture-text-secondary,#64736c)] hover:text-[var(--capture-text-primary,#182b24)]"}`}
                  onClick={() => goView(tab.key)}
                  type="button"
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* 内容区：每个 view 都用 `effectiveView === xxx && ...` 两段式守卫，
          避免「非当前 view 也走 else 渲染空态」的三目 bug。 */}
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {view !== "overview" && resolution === "missing" && (
          <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
            <p className="text-sm font-bold text-[var(--capture-text-secondary,#64736c)]">本次分析未生成该数据</p>
            <p className="text-xs text-[var(--capture-text-muted,#8f9d96)]">{missingReason ?? "请返回概览查看素材状态，或检查分析产物。"}</p>
          </div>
        )}
        {!(view !== "overview" && resolution === "missing") && (
          <>
        {effectiveView === "overview" && (
          <OverviewView
            item={item}
            hasAnalysis={hasAnalysis}
            onNavigate={onNavigate}
            onRefresh={() => setReloadToken((t) => t + 1)}
          />
        )}

        {effectiveView === "video" && (
          item.availabilityState === "unavailable" ? (
            <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">视频暂不可用</div>
          ) : item.ref.kind === "upload" ? (
            <SourceVideoContent videoId={item.ref.sourceId} />
          ) : item.ref.kind === "recording" || item.ref.kind === "sync_recording" ? (
            <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">正在加载视频回放…</div>}>
              <RecordingWorkspaceView sessionId={item.ref.sourceId} onNavigate={onNavigate} embedded />
            </Suspense>
          ) : (
            <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">暂无可用视频回放</div>
          )
        )}

        {effectiveView === "analysis" && (
          item.primaryAnalysisJobId ? (
            <VisionPage jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} recentJob={null} embedded />
          ) : (
            <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">暂无可用分析结果</div>
          )
        )}

        {effectiveView === "trajectory" && (
          item.primaryAnalysisJobId ? (
            <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">正在加载球路视图…</div>}>
              <BallTrajectoryView key={item.primaryAnalysisJobId} jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} embedded />
            </Suspense>
          ) : (
            <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">暂无可用球路</div>
          )
        )}

        {effectiveView === "report" && (
          item.primaryAnalysisJobId ? (
            <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">正在加载报告…</div>}>
              <ReportContentView jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} backPath="/library" />
            </Suspense>
          ) : (
            <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">暂无可用报告</div>
          )
        )}

        {effectiveView === "segments" && (
          item.fieldSessionId && item.captureTakeId ? (
            <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">正在加载片段…</div>}>
              <SegmentManagerView fieldSessionId={item.fieldSessionId} takeId={item.captureTakeId} onNavigate={onNavigate} embedded />
            </Suspense>
          ) : (
            <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">暂无可用片段</div>
          )
        )}

        {effectiveView === "technical" && (
          item.primaryAnalysisJobId ? (
            item.sourceType === "sync_recording" ? (
              <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">正在加载技术详情…</div>}>
                <MultiviewObservabilityView jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} embedded />
              </Suspense>
            ) : (
              <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">正在加载技术详情…</div>}>
                <AnalysisDetailsView jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} embedded />
              </Suspense>
            )
          ) : (
            <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">暂无可用技术详情</div>
          )
        )}
          </>
        )}
      </div>
    </div>
  );
}

function OverviewView({ item, hasAnalysis, onNavigate, onRefresh }: {
  item: LibraryItemViewModel;
  hasAnalysis: boolean;
  onNavigate: NavigateFn;
  onRefresh: () => void;
}) {
  const entryPoints = libraryAnalysisEntryPoints(item);
  const startPath = libraryAnalysisPathFor(item);
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const handleDeleteJob = async (job: LibraryAnalysisJobView) => {
    if (busyJobId) return;
    const confirmed = window.confirm(
      `确定删除该分析任务吗？后端会同步删除它的本地产物（报告/球路/覆盖图等），原视频保留且无法恢复。`,
    );
    if (!confirmed) return;
    setBusyJobId(job.id);
    setNotice(null);
    try {
      await deleteAnalysisJob(job.id);
      onRefresh();
    } catch {
      setNotice("删除分析任务失败，请检查后端服务后重试");
    } finally {
      setBusyJobId(null);
    }
  };

  const handleCancelJob = async (job: LibraryAnalysisJobView) => {
    if (busyJobId) return;
    const confirmed = window.confirm(`确定取消该分析任务吗？运行中的分析会在安全检查点停止。`);
    if (!confirmed) return;
    setBusyJobId(job.id);
    setNotice(null);
    try {
      await cancelAnalysisJob(job.id);
      onRefresh();
    } catch {
      setNotice("取消分析任务失败，请刷新后重试");
    } finally {
      setBusyJobId(null);
    }
  };

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <div className="rounded-2xl border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-card,#ffffff)] p-4">
        <p className="text-xs font-bold text-[var(--capture-text-muted,#8f9d96)]">分析状态</p>
        <p className="mt-1 text-lg font-black text-[var(--capture-text-primary,#182b24)]">{statusText(item)}</p>
        {!hasAnalysis ? (
          startPath ? (
            <button
              className="mt-3 rounded-full bg-[var(--capture-brand-strong,#197947)] px-4 py-1.5 text-xs font-bold text-white hover:bg-[var(--capture-brand-primary-hover,#14683d)]"
              onClick={() => onNavigate(startPath)}
              type="button"
            >
              开始分析
            </button>
          ) : (
            <p className="mt-3 text-xs text-[var(--capture-text-muted,#8f9d96)]">视频就绪后即可开始分析</p>
          )
        ) : (
          <div className="mt-3 flex flex-col gap-1.5">
            <p className="text-xs font-bold text-[var(--capture-text-muted,#8f9d96)]">再次分析</p>
            {entryPoints.map((ep) => {
              const path = ep.path;
              if (!path) return null;
              return (
                <button
                  key={ep.label}
                  className="rounded-full border border-[var(--capture-border-default,#d9e3dd)] px-4 py-1.5 text-left text-xs font-bold text-[var(--capture-brand-primary,#23985b)] transition hover:bg-[var(--capture-surface-soft,#f7faf8)]"
                  onClick={() => onNavigate(path)}
                  type="button"
                >
                  {ep.label}
                </button>
              );
            })}
          </div>
        )}

        {/* 历史分析任务：逐任务删除/取消（保留视频） */}
        {item.analysisJobs.length > 0 && (
          <div className="mt-4 border-t border-[var(--capture-border-default,#d9e3dd)] pt-3">
            <p className="text-xs font-bold text-[var(--capture-text-muted,#8f9d96)]">历史分析任务</p>
            <ul className="mt-2 space-y-1.5">
              {item.analysisJobs.map((job) => {
                const active = ["uploaded", "queued", "processing"].includes(job.status);
                return (
                  <li
                    key={job.id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-[var(--capture-border-default,#d9e3dd)] px-2.5 py-1.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs font-bold text-[var(--capture-text-primary,#182b24)]">
                        {analysisJobKindLabel(job)}
                      </p>
                      <p className="text-[11px] text-[var(--capture-text-muted,#8f9d96)]">
                        {analysisJobStatusLabel(job.status)}
                      </p>
                    </div>
                    <button
                      className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-bold transition disabled:opacity-50 ${
                        active
                          ? "bg-[var(--capture-status-processing-soft,#fff3dc)] text-[var(--capture-status-processing,#8a570e)] hover:bg-[#FFEAC0]"
                          : "bg-[var(--capture-status-failed-soft,#fde8e7)] text-[var(--capture-status-failed,#b42318)] hover:bg-[#FBD3D1]"
                      }`}
                      onClick={() => (active ? handleCancelJob(job) : handleDeleteJob(job))}
                      disabled={busyJobId !== null}
                      type="button"
                    >
                      {active ? "取消" : "删除"}
                    </button>
                  </li>
                );
              })}
            </ul>
            {notice && <p className="mt-2 text-[11px] text-[var(--capture-status-failed,#b42318)]">{notice}</p>}
          </div>
        )}
      </div>
      <div className="rounded-2xl border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-card,#ffffff)] p-4">
        <p className="text-xs font-bold text-[var(--capture-text-muted,#8f9d96)]">比赛信息</p>
        <p className="mt-1 text-sm font-bold text-[var(--capture-text-primary,#182b24)]">
          {item.ref.kind === "upload" ? "上传视频" : item.ref.kind === "recording" ? "录制素材" : "双摄录制"}
          {item.matchFormat === "singles" ? " · 单打" : item.matchFormat === "doubles" ? " · 双打" : ""}
        </p>
        <p className="mt-2 text-xs text-[var(--capture-text-muted,#8f9d96)]">
          {item.courtName ? `场地：${item.courtName}` : ""}
          {item.startedAt ? ` · ${new Date(item.startedAt).toLocaleString("zh-CN", { hour12: false })}` : ""}
        </p>
      </div>
    </div>
  );
}

function analysisJobKindLabel(job: LibraryAnalysisJobView): string {
  if (job.analysisKind === "multiview") return "双摄协同分析";
  if (job.analysisKind === "single_view") return "单视角分析";
  return "分析任务";
}

function analysisJobStatusLabel(status: LibraryAnalysisJobView["status"]): string {
  switch (status) {
    case "uploaded":
    case "queued":
      return "排队中";
    case "processing":
      return "分析中";
    case "completed":
      return "已完成";
    case "failed":
      return "已失败";
    case "canceled":
      return "已取消";
    default:
      return status;
  }
}

function statusText(item: LibraryItemViewModel): string {
  if (item.mediaState === "recording") return "正在录制";
  if (item.mediaState === "processing") {
    if (item.requiredAction === "merge") return "待合并";
    return "视频处理中";
  }
  if (item.mediaState === "failed") return "视频失败";
  if (item.mediaState === "canceled") return "已取消";
  switch (item.analysisState) {
    case "not_started": return "待分析";
    case "running": return "正在分析";
    case "succeeded": return "分析完成";
    case "failed": return "分析失败";
    default: return "待分析";
  }
}