import { useEffect, useRef, useState } from "react";
import { FileText, MoreHorizontal, Play, Trash2, Video } from "lucide-react";
import type { NavigateFn } from "../../app/navigationTypes";
import type { LibraryItemViewModel } from "../../services/libraryAdapter";
import { LibraryCover } from "./LibraryCover";
import { libraryAnalysisPathFor } from "../../services/libraryAnalysisRouting";

const KIND_LABEL: Record<LibraryItemViewModel["sourceType"], string> = {
  upload: "上传",
  recording: "录制",
  sync_recording: "双摄",
};

/** 业务语义状态 tone：UI 不依赖颜色名，只表达状态 */
type StatusTone = "pending" | "processing" | "success" | "merge" | "failed" | "ai" | "recording";

function stateBadge(item: LibraryItemViewModel): { text: string; tone: StatusTone } {
  // 媒体生命周期
  if (item.mediaState === "recording") return { text: "正在录制", tone: "recording" };
  if (item.mediaState === "canceled") return { text: "已取消", tone: "pending" };
  if (item.mediaState === "failed") return { text: "失败", tone: "failed" };
  if (item.mediaState === "processing") {
    if (item.requiredAction === "merge") return { text: "待合并", tone: "merge" };
    if (item.requiredAction === "retry_merge") return { text: "合并失败", tone: "failed" };
    return { text: "视频处理中", tone: "ai" };
  }
  // 分析生命周期
  switch (item.analysisState) {
    case "not_started":
      return { text: "待分析", tone: "pending" };
    case "queued":
      return { text: "队列中", tone: "ai" };
    case "running":
      return { text: "正在分析", tone: "processing" };
    case "succeeded":
      return { text: "分析完成", tone: "success" };
    case "failed":
      return { text: "分析失败", tone: "failed" };
    case "canceled":
      return { text: "分析已取消", tone: "pending" };
    default:
      return { text: "待分析", tone: "pending" };
  }
}

const toneClass: Record<StatusTone, string> = {
  pending: "bg-[var(--capture-status-pending-soft,#eef2f6)] text-[var(--capture-status-pending,#475569)]",
  processing: "bg-[var(--capture-status-processing-soft,#fff3dc)] text-[var(--capture-status-processing,#8a570e)]",
  success: "bg-[var(--capture-status-success-soft,#e5f4ea)] text-[var(--capture-status-success,#176b3c)]",
  merge: "bg-[var(--capture-status-merge-soft,#fff0da)] text-[var(--capture-status-merge,#9a5300)]",
  failed: "bg-[var(--capture-status-failed-soft,#fde8e7)] text-[var(--capture-status-failed,#b42318)]",
  ai: "bg-[var(--capture-status-ai-soft,#e8f4f6)] text-[var(--capture-status-ai,#2f6f7b)]",
  recording: "bg-[var(--capture-status-recording-soft,#fde8e7)] text-[var(--capture-status-recording,#e5484d)]",
};

/** 属性标签去重：source 类型 + 比赛形式；camera 设置若被 source 类型隐含则不重复展示 */
function attributeTags(item: LibraryItemViewModel): string[] {
  const tags: string[] = [];
  const setupShown =
    (item.sourceType === "sync_recording" && item.cameraSetup === "dual") ||
    (item.sourceType === "recording" && item.cameraSetup === "single") ||
    item.sourceType === "upload";
  if (!setupShown && item.cameraSetup) {
    tags.push(item.cameraSetup === "dual" ? "双摄" : "单摄");
  }
  if (item.matchFormat === "singles") tags.push("单打");
  else if (item.matchFormat === "doubles") tags.push("双打");
  return tags;
}

function creditCardRoot(item: LibraryItemViewModel): { label: string; action?: () => void } | null {
  return {
    label: KIND_LABEL[item.sourceType],
  };
}

export function LibraryCard({
  item,
  onNavigate,
  onMerge,
  onReanalyze,
  onDelete,
  onOpenVideo,
  onOpenTechnical,
}: {
  item: LibraryItemViewModel;
  onNavigate: NavigateFn;
  onMerge?: (item: LibraryItemViewModel) => void;
  onReanalyze?: (item: LibraryItemViewModel) => void;
  onDelete?: (item: LibraryItemViewModel) => void;
  onOpenVideo?: (item: LibraryItemViewModel) => void;
  onOpenTechnical?: (item: LibraryItemViewModel) => void;
}) {
  const badge = stateBadge(item);
  const detailPath = `/library/${item.ref.kind}/${encodeURIComponent(item.ref.sourceId)}?view=overview` as const;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭菜单
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const runAction = (action: () => void) => {
    setMenuOpen(false);
    action();
  };

  const kind = creditCardRoot(item)?.label ?? "";
  const extraTags = attributeTags(item);

  // 未接通/无 context 的菜单项直接隐藏，不保留「看似可用其实 no-op」的死项
  const needsMerge = item.requiredAction === "merge" || item.requiredAction === "retry_merge";
  const canOpenVideo = item.ref.kind === "upload" && Boolean(onOpenVideo);
  const canReanalyze = Boolean(onReanalyze) && Boolean(libraryAnalysisPathFor(item));
  const canDelete = item.ref.kind !== "upload" && Boolean(onDelete);
  // 已分析 → 「再次分析」；未分析 → 「开始分析」
  const analyzeLabel = item.analysisState === "succeeded" ? "再次分析" : "开始分析";

  return (
    <article className="group relative overflow-hidden rounded-2xl border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-card,#ffffff)] shadow-sm transition hover:shadow-md">
      {/* 点击区：缩略图 + 信息，作为单一可点击实体（不再包整卡 button，避免 nested button） */}
      <button
        className="block w-full text-left"
        onClick={() => onNavigate(detailPath)}
        type="button"
      >
        {/* 视频缩略图区：有稳定图片端点用图；否则按来源分派渲染首帧封面（单画面 / 双摄左右拼接）；均带会话内缓存 */}
        <div className="relative aspect-video bg-gradient-to-br from-[#E7EEEB] to-[#DCE7E2]">
          {item.thumbnailUrl ? (
            <img
              src={item.thumbnailUrl}
              alt={item.title}
              loading="lazy"
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : item.coverVideoUrl || item.cameraCoverSources ? (
            <div className="absolute inset-0">
              <LibraryCover item={item} />
            </div>
          ) : (
            <div className="absolute inset-0 grid place-items-center text-[var(--capture-text-muted,#8f9d96)]">
              <Video size={36} aria-hidden="true" />
            </div>
          )}
          {!item.thumbnailUrl && !item.coverVideoUrl && !item.cameraCoverSources && (
            /* 无真实封面时叠一层轻球场线纹理，克制占位 */
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full opacity-15"
              viewBox="0 0 100 60"
              preserveAspectRatio="xMidYMid slice"
              aria-hidden="true"
            >
              <rect x="4" y="3" width="92" height="54" fill="none" stroke="#475569" strokeWidth="0.6" />
              <line x1="4" y1="30" x2="96" y2="30" stroke="#475569" strokeWidth="0.6" />
              <line x1="4" y1="20" x2="96" y2="20" stroke="#475569" strokeWidth="0.6" strokeDasharray="2 1.6" />
              <line x1="4" y1="40" x2="96" y2="40" stroke="#475569" strokeWidth="0.6" strokeDasharray="2 1.6" />
              <line x1="50" y1="3" x2="50" y2="57" stroke="#475569" strokeWidth="0.6" />
            </svg>
          )}
          {(item.analysisState === "running" || item.analysisState === "queued") && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-black/45 px-3 text-center text-white">
              <span className="text-xs font-bold">
                {item.analysisState === "queued" ? "排队中" : "正在分析"}
                {typeof item.analysisProgress === "number" ? ` · ${Math.round(item.analysisProgress)}%` : ""}
              </span>
              <div className="h-1 w-24 overflow-hidden rounded-full bg-white/30">
                {typeof item.analysisProgress === "number" ? (
                  <div
                    className="h-full rounded-full bg-[var(--capture-brand-primary,#23985b)]"
                    style={{ width: `${Math.max(0, Math.min(100, item.analysisProgress))}%` }}
                  />
                ) : (
                  <div className="h-full w-1/2 animate-pulse rounded-full bg-[var(--capture-brand-primary,#23985b)]" />
                )}
              </div>
              {item.analysisStage ? (
                <span className="max-w-[92%] truncate text-[10px] text-white/80">{item.analysisStage}</span>
              ) : null}
            </div>
          )}
          <span className={`absolute left-2 top-2 inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-bold ${toneClass[badge.tone]}`}>
            <span className="size-1.5 rounded-full bg-current" />
            {badge.text}
          </span>
        </div>

        {/* 信息区 */}
        <div className="space-y-1.5 p-3">
          <p className="truncate text-sm font-bold text-[var(--capture-text-primary,#182b24)]">{item.title}</p>
          <p className="text-xs text-[var(--capture-text-secondary,#64736c)]">
            {formatDate(item.startedAt)}
            {item.courtName ? ` · ${item.courtName}` : ""}
          </p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--capture-text-muted,#8f9d96)]">
            <span className="inline-flex items-center gap-1 rounded border border-[var(--capture-border-default,#d9e3dd)] px-1.5 py-0.5">
              {kind}
            </span>
            {extraTags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
            {item.primaryAnalysisJobId && (
              <span className="inline-flex items-center gap-1">
                <Play size={10} aria-hidden="true" />
                {item.analysisHistoryCount > 1 ? `${item.analysisHistoryCount} 次分析` : "查看分析"}
              </span>
            )}
            {!item.primaryAnalysisJobId && needsMerge && <span className="text-[var(--capture-status-merge,#9a5300)]">待合并</span>}
          </div>
        </div>
      </button>

      {/* 生命周期动作（如待合并 → 合并视频）；独立于点击实体，避免 nested button */}
      {needsMerge && onMerge && (
        <div className="border-t border-[var(--capture-border-default,#d9e3dd)] px-3 py-2">
          <button
            className="w-full rounded-lg bg-[var(--capture-status-merge-soft,#fff0da)] px-3 py-1.5 text-xs font-bold text-[var(--capture-status-merge,#9a5300)] transition hover:bg-[#FFEAC0]"
            onClick={() => onMerge(item)}
            type="button"
          >
            {item.requiredAction === "retry_merge" ? "重新合并视频" : "合并视频"}
          </button>
        </div>
      )}
      {item.requiredAction === "retry_merge" && !onMerge && (
        <div className="border-t border-[var(--capture-border-default,#d9e3dd)] px-3 py-2">
          <span className="text-xs font-bold text-[var(--capture-status-merge,#9a5300)]">合并失败，请重试</span>
        </div>
      )}

      {/* ··· 操作菜单（低频操作折叠；未接通项隐藏而非禁用） */}
      <div ref={menuRef} className="absolute right-2 top-2 z-10">
        <button
          className="rounded-md p-1 text-white/80 hover:bg-white/20"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((v) => !v);
          }}
          type="button"
          aria-label="更多操作"
        >
          <MoreHorizontal size={16} />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-8 w-48 rounded-xl border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-card,#ffffff)] py-1 shadow-lg">
            {canReanalyze && (
              <MenuItem
                icon={<Play size={14} />}
                label={analyzeLabel}
                onClick={() => runAction(() => onReanalyze?.(item))}
              />
            )}
            {canOpenVideo && (
              <MenuItem
                icon={<Video size={14} />}
                label="查看原视频"
                onClick={() => runAction(() => onOpenVideo?.(item))}
              />
            )}
            <MenuItem
              icon={<FileText size={14} />}
              label="查看技术信息"
              onClick={() => runAction(() => onOpenTechnical?.(item))}
              disabled={!onOpenTechnical}
            />
            {canDelete && (
              <>
                <div className="my-1 border-t border-[var(--capture-border-default,#d9e3dd)]" />
                <MenuItem
                  icon={<Trash2 size={14} />}
                  label="删除"
                  tone="danger"
                  onClick={() => runAction(() => onDelete?.(item))}
                />
              </>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  disabled,
  tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "default" | "danger";
}) {
  return (
    <button
      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-bold ${disabled ? "cursor-not-allowed text-[var(--capture-text-muted,#8f9d96)]" : `${tone === "danger" ? "text-[var(--capture-status-failed,#b42318)] hover:bg-[var(--capture-status-failed-soft,#fde8e7)]" : "text-[var(--capture-text-secondary,#64736c)] hover:bg-[var(--capture-surface-soft,#f7faf8)]"}`}`}
      onClick={onClick}
      disabled={disabled}
      type="button"
    >
      {icon}
      {label}
    </button>
  );
}

function formatDate(iso?: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return `今天 ${d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
    }
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
      return `昨天 ${d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
    }
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  } catch {
    return "";
  }
}