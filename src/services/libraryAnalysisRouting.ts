/**
 * Library 分析入口路由（纯函数）
 *
 * 统一计算「开始分析 / 再次分析」的目标 URL，按素材类型分派到既有分析创建页：
 * - `sync_recording`（双摄）：主入口为双摄协同 `MultiViewAnalysisSetupPage`；另提供 A/B 机位单摄 `RecordingAnalyzePage`。
 * - `recording`（单摄）：复用预填 videoId 的上传分析流程（NewAnalysisPage）。
 * - `upload`：复用预填 videoId 的上传分析流程。
 *
 * 目标不可确定（如双摄缺 captureTakeId）时返回 `null`，由调用方隐藏/禁用，不伪造可用。
 */

import type { LibraryItemViewModel } from "./libraryAdapter";
import type { NavigatePath } from "../app/navigationTypes";

export interface LibraryAnalysisEntryPoint {
  /** 入口文案（如「双摄协同分析」「A 机位分析」） */
  label: string;
  /** 目标 URL；不可用时为 null */
  path: NavigatePath | null;
}

/**
 * 媒体生命周期是否可发起分析：就绪、非待合并、存储可用。
 *
 * 说明：`availabilityState === "unavailable"` 只在「尚未分析」时阻断——源视频流不可用则不该发起首次分析；
 * 但「已分析素材的再次分析」可基于已注册/已落盘的视频重跑，因此不因视频流暂不可用而隐藏入口（否则会出现
 * 卡片显示"分析完成"却没有「再次分析」按钮的死角，如双摄某一路源视频不可用）。
 */
function analyzableMedia(item: LibraryItemViewModel): boolean {
  if (item.mediaState === "recording") return false;
  if (item.requiredAction === "merge" || item.requiredAction === "retry_merge") return false;
  if (item.availabilityState === "unavailable" && !item.primaryAnalysisJobId) return false;
  return true;
}

/** 从 Library 进入分析创建页时的返回地址（该素材工作区概览）。 */
export function libraryItemOverviewPath(item: LibraryItemViewModel): string {
  return `/library/${item.ref.kind}/${encodeURIComponent(item.ref.sourceId)}?view=overview`;
}

/** 追加 `return` 参数（分析创建页取消/退出/完成时用于回到来源工作区）。 */
function withReturn(path: string, item: LibraryItemViewModel): NavigatePath {
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}return=${encodeURIComponent(libraryItemOverviewPath(item))}` as NavigatePath;
}

/** 依据素材类型返回全部可用的分析创建入口；媒体未就绪或无任何可用入口时返回空数组。 */
export function libraryAnalysisEntryPoints(item: LibraryItemViewModel): LibraryAnalysisEntryPoint[] {
  if (!analyzableMedia(item)) return [];
  if (item.ref.kind === "sync_recording") {
    const sessionId = item.ref.sourceId;
    const points: LibraryAnalysisEntryPoint[] = [];
    if (item.captureTakeId) {
      points.push({
        label: "双摄协同分析",
        path: withReturn(
          `/capture/takes/${encodeURIComponent(item.captureTakeId)}/analyze?session=${encodeURIComponent(sessionId)}`,
          item,
        ),
      });
    }
    points.push({
      label: "A 机位分析",
      path: withReturn(`/capture/${encodeURIComponent(sessionId)}/analyze?cam=cam_1`, item),
    });
    points.push({
      label: "B 机位分析",
      path: withReturn(`/capture/${encodeURIComponent(sessionId)}/analyze?cam=cam_2`, item),
    });
    return points;
  }

  if (item.ref.kind === "recording") {
    if (!item.videoId) return [];
    return [
      {
        label: "开始分析",
        path: withReturn(
          `/analysis/new?videoId=${encodeURIComponent(item.videoId)}&source=recording&sessionId=${encodeURIComponent(item.ref.sourceId)}`,
          item,
        ),
      },
    ];
  }

  // upload：源视频 id 即 ref.sourceId
  return [
    {
      label: "开始分析",
      path: withReturn(`/upload?videoId=${encodeURIComponent(item.ref.sourceId)}`, item),
    },
  ];
}

/** 返回主入口目标 URL；无任何可用入口时为 null。 */
export function libraryAnalysisPathFor(item: LibraryItemViewModel): NavigatePath | null {
  const primary = libraryAnalysisEntryPoints(item)[0];
  return primary?.path ?? null;
}