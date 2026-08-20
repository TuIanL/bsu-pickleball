import { lazy, Suspense, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type { NavigateFn } from "../../app/navigationTypes";
import type { LibraryItemRef, LibraryItemViewModel } from "../../services/libraryAdapter";
import { resolveLibraryItemByRef } from "../../services/libraryAdapter";
import { VisionPage } from "../../pages/VisionPage";
import { ReportPage } from "../../pages/ReportPage";

const BallTrajectoryView = lazy(() =>
  import("../../pages/BallTrajectoryPage").then((m) => ({ default: m.BallTrajectoryPage })),
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

type LibraryView = "overview" | "video" | "analysis" | "trajectory" | "report" | "segments" | "technical";

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

  const ref: LibraryItemRef = { kind, sourceId };

  useEffect(() => {
    let cancelled = false;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, sourceId]);

  // D14：无成功分析时，结果类 view 落到 overview + 待分析提示（stable fallback，不空白）
  const hasAnalysis = item?.primaryAnalysisJobId != null;
  const reportLikeView = view === "analysis" || view === "trajectory" || view === "report" || view === "technical";
  const effectiveView: LibraryView = reportLikeView && !hasAnalysis ? "overview" : view;

  const goView = (v: LibraryView) => {
    // D3：view 切换用 replace（同一素材对象内）
    onNavigate(`/library/${ref.kind}/${encodeURIComponent(ref.sourceId)}?view=${v}`, { replace: true });
  };

  const title = item?.title ?? (ref.kind === "upload" ? "上传视频" : ref.kind === "recording" ? "录制" : "双摄录制");

  if (loading) {
    return <div className="grid min-h-[60vh] place-items-center text-sm text-[#98A2B3]">加载素材…</div>;
  }

  if (!item) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <p className="text-sm font-bold text-[#667085]">未找到该素材</p>
        <button className="mt-4 text-sm font-bold text-[#168A34]" onClick={() => onNavigate("/library")} type="button">
          返回比赛库
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* 顶栏 */}
      <div className="border-b border-[#E4E7EC]">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
          <button
            className="mb-3 inline-flex items-center gap-1 text-xs font-bold text-[#667085] hover:text-[#182230]"
            onClick={() => onNavigate("/library")}
            type="button"
          >
            <ArrowLeft size={14} aria-hidden="true" />
            比赛库
          </button>
          <h1 className="text-xl font-black text-[#182230]">{title}</h1>
          <p className="mt-1 text-xs text-[#667085]">
            {item.matchFormat === "singles" ? "单打" : item.matchFormat === "doubles" ? "双打" : ""}
            {item.cameraSetup ? ` · ${item.cameraSetup === "dual" ? "双摄" : "单摄"}` : ""}
            {item.startedAt ? ` · ${new Date(item.startedAt).toLocaleString("zh-CN", { hour12: false })}` : ""}
          </p>
        </div>

        {/* Tab 栏 */}
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="flex gap-1 overflow-x-auto">
            {VIEW_TABS.map((tab) => {
              // 素材层面结果类 view 依据状态门控（D14）：无分析时不可点
              const locked = ["analysis", "trajectory", "report", "technical"].includes(tab.key) && !hasAnalysis;
              return (
                <button
                  key={tab.key}
                  disabled={locked}
                  className={`-mb-px shrink-0 border-b-2 px-4 py-2.5 text-sm font-bold transition disabled:cursor-not-allowed disabled:text-[#C0C5CE] ${effectiveView === tab.key ? "border-[#168A34] text-[#168A34]" : "border-transparent text-[#667085] hover:text-[#182230]"}`}
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

      {/* 内容区 */}
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {effectiveView === "overview" && (
          <OverviewView item={item} hasAnalysis={hasAnalysis} onNavigate={onNavigate} />
        )}
        {effectiveView === "video" && item.ref.kind === "recording" ? (
          <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[#98A2B3]">正在加载视频回放…</div>}>
            <RecordingWorkspaceView sessionId={item.ref.sourceId} onNavigate={onNavigate} />
          </Suspense>
        ) : (
          <div className="grid place-items-center py-24 text-sm text-[#98A2B3]">暂无可用视频回放</div>
        )}
        {effectiveView === "analysis" && item.primaryAnalysisJobId ? (
          <VisionPage jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} recentJob={null} />
        ) : (
          <div className="grid place-items-center py-24 text-sm text-[#98A2B3]">暂无可用分析结果</div>
        )}
        {effectiveView === "trajectory" && item.primaryAnalysisJobId ? (
          <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[#98A2B3]">正在加载球路视图…</div>}>
            <BallTrajectoryView key={item.primaryAnalysisJobId} jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} />
          </Suspense>
        ) : (
          <div className="grid place-items-center py-24 text-sm text-[#98A2B3]">暂无可用球路</div>
        )}
        {effectiveView === "report" && item.primaryAnalysisJobId ? (
          <ReportPage jobId={item.primaryAnalysisJobId} reportType="movement" onNavigate={onNavigate} />
        ) : (
          <div className="grid place-items-center py-24 text-sm text-[#98A2B3]">暂无可用报告</div>
        )}
        {effectiveView === "segments" && item.fieldSessionId && item.captureTakeId ? (
          <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[#98A2B3]">正在加载片段…</div>}>
            <SegmentManagerView fieldSessionId={item.fieldSessionId} takeId={item.captureTakeId} onNavigate={onNavigate} />
          </Suspense>
        ) : (
          <div className="grid place-items-center py-24 text-sm text-[#98A2B3]">暂无可用片段</div>
        )}
        {effectiveView === "technical" && item.primaryAnalysisJobId ? (
          item.sourceType === "sync_recording" ? (
            <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[#98A2B3]">正在加载技术详情…</div>}>
              <MultiviewObservabilityView jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} />
            </Suspense>
          ) : (
            <Suspense fallback={<div className="grid place-items-center py-24 text-sm text-[#98A2B3]">正在加载技术详情…</div>}>
              <AnalysisDetailsView jobId={item.primaryAnalysisJobId} onNavigate={onNavigate} />
            </Suspense>
          )
        ) : (
          <div className="grid place-items-center py-24 text-sm text-[#98A2B3]">暂无可用技术详情</div>
        )}
      </div>
    </div>
  );
}

function OverviewView({ item, hasAnalysis, onNavigate }: {
  item: LibraryItemViewModel;
  hasAnalysis: boolean;
  onNavigate: NavigateFn;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <div className="rounded-2xl border border-[#E4E7EC] bg-white p-4">
        <p className="text-xs font-bold text-[#98A2B3]">分析状态</p>
        <p className="mt-1 text-lg font-black text-[#182230]">{statusText(item)}</p>
        {!hasAnalysis && (
          <button
            className="mt-3 rounded-full bg-[#19B84C] px-4 py-1.5 text-xs font-bold text-white hover:bg-[#168A34]"
            onClick={() => onNavigate(`/library/${item.ref.kind}/${encodeURIComponent(item.ref.sourceId)}?view=analysis`, { replace: true })}
            type="button"
          >
            进入分析
          </button>
        )}
      </div>
      <div className="rounded-2xl border border-[#E4E7EC] bg-white p-4">
        <p className="text-xs font-bold text-[#98A2B3]">资产标识</p>
        <p className="mt-1 text-sm font-bold text-[#182230]">
          {item.ref.kind}:{item.ref.sourceId}
        </p>
        <p className="mt-2 text-xs text-[#98A2B3]">
          {item.courtName ? `场地：${item.courtName}` : ""}
          {item.fieldSessionId ? ` · 场次：${item.fieldSessionId}` : ""}
        </p>
      </div>
    </div>
  );
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