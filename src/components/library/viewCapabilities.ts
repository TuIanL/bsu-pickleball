// =============================================================
// LibraryViewCapabilities - Workspace 各 view 的能力门控
// -------------------------------------------------------------
// 结果类 view 可开性依据「素材 Job 状态 + 展示元数据」一次判定：
//   - analysis / report / trajectory / technical → analysisState
//   - video     → source media availability
//   - segments  → 拥有 captureTake
// 禁止初始门控逐 view 拉重产物（trajectory/report/heatmap…）。
// 区分 invalid view（source 不支持 → replace 到 overview）与
// 合法但缺产物（停在原 URL 显示缺产物提示）。
// =============================================================
import type { LibraryItemViewModel } from "../../services/libraryAdapter";
import type { AnalysisPipelineResult } from "../../types/report";
import type { LibraryAnalysisJobView } from "../../services/libraryAdapter";

export type LibraryView = "overview" | "video" | "analysis" | "trajectory" | "report" | "segments" | "technical";

export type CapabilityState = "available" | "unavailable" | "loading";

export interface LibraryViewCapabilities {
  video: CapabilityState;
  analysis: CapabilityState;
  trajectory: CapabilityState;
  report: CapabilityState;
  segments: CapabilityState;
  technical: CapabilityState;
  reasons?: Partial<Record<LibraryView, string>>;
}

export interface SelectedAnalysisCapabilityInput {
  job?: LibraryAnalysisJobView;
  manifest?: AnalysisPipelineResult | null;
  manifestState?: "idle" | "loading" | "loaded" | "error";
}

/** 该素材 source 根本不支持的 view（→ 应 replace 到 overview） */
const INVALID_VIEWS_BY_KIND: Partial<Record<LibraryItemViewModel["ref"]["kind"], LibraryView[]>> = {
  upload: ["segments"],
  recording: [],
  sync_recording: [],
};

/**
 * 依据 LibraryItemViewModel 一次性计算各 view 可开性。
 * 不发起额外重产物请求（只读已加载的展示元数据）。
 */
export function computeLibraryViewCapabilities(
  item: LibraryItemViewModel,
  selected?: SelectedAnalysisCapabilityInput,
): LibraryViewCapabilities {
  const reasons: Partial<Record<LibraryView, string>> = {};
  // 结果门控基于「最新 completed 权威结果」：再次分析进行中旧结果仍可用，不被 active 顶掉
  const selectedJob = selected?.job;
  const legacyResult = Boolean(item.primaryResultAnalysisJobId ?? item.primaryAnalysisJobId);
  const hasSelection = selected ? Boolean(selectedJob) : legacyResult;
  const terminalDiagnostic = selectedJob?.status === "failed" || selectedJob?.status === "canceled";
  const completed = selected ? selectedJob?.status === "completed" : legacyResult;
  const manifestPending = Boolean(selected && completed && (selected.manifestState === "idle" || selected.manifestState === "loading"));
  const manifestReady = selected ? Boolean(completed && selected.manifest) : legacyResult;
  const trajectoryReady = selected
    ? Boolean(
        manifestReady &&
        (selected.manifest?.artifacts.reconstructed_ball_trajectory_url ||
          selected.manifest?.artifacts.cleaned_ball_trajectory_url ||
          selected.manifest?.artifacts.ball_trajectory_url),
      )
    : legacyResult;
  const canPlayVideo = item.availabilityState !== "unavailable";
  const hasTake = Boolean(item.fieldSessionId && item.captureTakeId);

  const resultCaps: LibraryViewCapabilities = {
    video: canPlayVideo ? "available" : "unavailable",
    analysis: manifestPending ? "loading" : manifestReady ? "available" : "unavailable",
    trajectory: manifestPending ? "loading" : trajectoryReady ? "available" : "unavailable",
    report: manifestPending ? "loading" : manifestReady ? "available" : "unavailable",
    segments: hasTake ? "available" : "unavailable",
    technical: hasSelection && (completed || terminalDiagnostic) ? "available" : "unavailable",
    reasons,
  };

  if (!canPlayVideo) reasons.video = "视频存储暂不可用";
  if (!hasSelection) {
    const msg = "该素材尚无可用的分析结果";
    reasons.analysis = msg;
    reasons.report = msg;
    reasons.technical = msg;
  } else if (terminalDiagnostic) {
    const msg = selectedJob?.status === "canceled" ? "该任务已取消，未生成结果" : "分析失败，未生成结果";
    reasons.analysis = msg;
    reasons.trajectory = msg;
    reasons.report = msg;
  } else if (selected && !manifestPending && !manifestReady) {
    const msg = "该历史任务没有可读取的分析产物";
    reasons.analysis = msg;
    reasons.report = msg;
  }
  if (selected && completed && !manifestPending && !trajectoryReady) reasons.trajectory = "该历史任务未生成可用球路";
  if (!hasTake) reasons.segments = "该素材没有可管理的片段数据";

  return resultCaps;
}

/** 该视图对当前素材是否非法（该 source 压根不支持） */
export function isInvalidViewForItem(
  item: LibraryItemViewModel,
  view: LibraryView,
): boolean {
  const invalid = INVALID_VIEWS_BY_KIND[item.ref.kind];
  return invalid ? invalid.includes(view) : false;
}

/**
 * 解析一个 view 的实际可开性：
 * 非法视图 → 应落到 overview；
 * 合法但缺产物 → 停在原 view 显示缺产物提示；
 * 可达 → 正常渲染。
 */
export function resolveViewCapability(
  item: LibraryItemViewModel,
  view: LibraryView,
  caps: LibraryViewCapabilities,
): "invalid" | "missing" | "loading" | "available" {
  if (view === "overview") return "available";
  if (isInvalidViewForItem(item, view)) return "invalid";
  if (caps[view] === "loading") return "loading";
  if (caps[view] !== "available") return "missing";
  return "available";
}
