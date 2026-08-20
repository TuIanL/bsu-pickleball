import { useEffect, useRef, useState } from "react";
import { Copy, Download, ExternalLink, FileText, MoreHorizontal, Play, Trash2, Video } from "lucide-react";
import type { NavigateFn } from "../../app/navigationTypes";
import type { LibraryItemViewModel } from "../../services/libraryAdapter";

const KIND_LABEL: Record<LibraryItemViewModel["sourceType"], string> = {
  upload: "上传",
  recording: "录制",
  sync_recording: "双摄",
};

function stateBadge(item: LibraryItemViewModel): { text: string; tone: "green" | "blue" | "amber" | "gray" | "red" } {
  // 媒体生命周期
  if (item.mediaState === "recording") return { text: "正在录制", tone: "red" };
  if (item.mediaState === "canceled") return { text: "已取消", tone: "gray" };
  if (item.mediaState === "failed") return { text: "失败", tone: "red" };
  if (item.mediaState === "processing") {
    if (item.requiredAction === "merge") return { text: "待合并", tone: "amber" };
    if (item.requiredAction === "retry_merge") return { text: "合并失败", tone: "red" };
    return { text: "视频处理中", tone: "blue" };
  }
  // 分析生命周期
  switch (item.analysisState) {
    case "not_started":
      return { text: "待分析", tone: "gray" };
    case "queued":
      return { text: "队列中", tone: "blue" };
    case "running":
      return { text: "正在分析", tone: "amber" };
    case "succeeded":
      return { text: "分析完成", tone: "green" };
    case "failed":
      return { text: "分析失败", tone: "red" };
    case "canceled":
      return { text: "分析已取消", tone: "gray" };
    default:
      return { text: "待分析", tone: "gray" };
  }
}

const toneClass: Record<string, string> = {
  green: "bg-[#E7F7EC] text-[#168A34]",
  blue: "bg-[#EAF2FF] text-[#2563EB]",
  amber: "bg-[#FFF4E5] text-[#B45309]",
  gray: "bg-[#F2F4F7] text-[#667085]",
  red: "bg-[#FEE4E2] text-[#D92D20]",
};

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

  return (
    <div className="group overflow-hidden rounded-2xl border border-[#E4E7EC] bg-white shadow-sm transition hover:shadow-md">
      <button
        className="block w-full text-left"
        onClick={() => onNavigate(detailPath)}
        type="button"
      >
        {/* 视频缩略图区（placeholder；有 thumbnailUrl/previewUrl 时接入真实画面） */}
        <div className="relative aspect-video bg-gradient-to-br from-[#EAF7EE] to-[#D1FADF]">
          <div className="absolute inset-0 grid place-items-center text-[#168A34]/60">
            <Video size={36} aria-hidden="true" />
          </div>
          {item.analysisState === "running" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/45 text-white">
              <span className="text-xs font-bold">正在分析中</span>
              <div className="h-1 w-24 overflow-hidden rounded-full bg-white/30">
                <div className="h-full w-2/3 rounded-full bg-[#21C55D]" />
              </div>
            </div>
          )}
          <span className={`absolute left-2 top-2 inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-bold ${toneClass[badge.tone]}`}>
            <span className="size-1.5 rounded-full bg-current" />
            {badge.text}
          </span>
        </div>

        {/* 生命周期动作（D6 requiredAction）：如待合并 → 合并视频 */}
        {(item.requiredAction === "merge" || item.requiredAction === "retry_merge") && onMerge && (
          <div className="border-b border-[#F2F4F7] px-3 py-2">
            <button
              className="w-full rounded-lg bg-[#FFF4E5] px-3 py-1.5 text-xs font-bold text-[#B45309] transition hover:bg-[#FFEAC0]"
              onClick={(e) => {
                e.stopPropagation();
                onMerge(item);
              }}
              type="button"
            >
              {item.requiredAction === "retry_merge" ? "重新合并视频" : "合并视频"}
            </button>
          </div>
        )}
        {item.requiredAction === "retry_merge" && !onMerge && (
          <div className="border-b border-[#F2F4F7] px-3 py-2">
            <span className="text-xs font-bold text-[#B45309]">合并失败，请重试</span>
          </div>
        )}

        {/* 信息区 */}
        <div className="space-y-1.5 p-3">
          <p className="truncate text-sm font-bold text-[#182230]">{item.title}</p>
          <p className="text-xs text-[#667085]">
            {formatDate(item.startedAt)}
            {item.courtName ? ` · ${item.courtName}` : ""}
          </p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[#98A2B3]">
            <span className="inline-flex items-center gap-1 rounded border border-[#E4E7EC] px-1.5 py-0.5">
              {KIND_LABEL[item.sourceType]}
            </span>
            {item.cameraSetup === "dual" ? (
              <span>双摄</span>
            ) : item.cameraSetup === "single" ? (
              <span>单摄</span>
            ) : null}
            {item.matchFormat === "singles" ? <span>单打</span> : item.matchFormat === "doubles" ? <span>双打</span> : null}
            {item.primaryAnalysisJobId ? (
              <span className="inline-flex items-center gap-1">
                <Play size={10} aria-hidden="true" />
                {item.analysisHistoryCount > 1 ? `${item.analysisHistoryCount} 次分析` : "查看分析"}
              </span>
            ) : item.requiredAction === "merge" ? (
              <span className="text-[#B45309]">待合并</span>
            ) : null}
          </div>
        </div>
      </button>

      {/* ··· 操作菜单（低频操作折叠；源视频删除为显式独立动作） */}
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
          <div className="absolute right-0 top-8 w-48 rounded-xl border border-[#E4E7EC] bg-white py-1 shadow-lg">
            <MenuItem icon={<Copy size={14} />} label="重命名" disabled />
            <MenuItem icon={<FileText size={14} />} label="加入场次/文件夹" disabled />
            <MenuItem
              icon={<Play size={14} />}
              label="重新分析"
              onClick={() => runAction(() => onReanalyze?.(item))}
              disabled={!onReanalyze}
            />
            <MenuItem
              icon={<Video size={14} />}
              label="查看原视频"
              onClick={() => runAction(() => onOpenVideo?.(item))}
              disabled={!onOpenVideo}
            />
            <MenuItem icon={<Download size={14} />} label="下载" disabled />
            <MenuItem icon={<ExternalLink size={14} />} label="分享" disabled />
            <MenuItem
              icon={<FileText size={14} />}
              label="查看技术信息"
              onClick={() => runAction(() => onOpenTechnical?.(item))}
              disabled={!onOpenTechnical}
            />
            <div className="my-1 border-t border-[#F2F4F7]" />
            <MenuItem
              icon={<Trash2 size={14} />}
              label="删除"
              tone="danger"
              onClick={() => runAction(() => onDelete?.(item))}
              disabled={!onDelete}
            />
          </div>
        )}
      </div>
    </div>
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
      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-bold ${disabled ? "cursor-not-allowed text-[#C0C5CE]" : `${tone === "danger" ? "text-[#D92D20] hover:bg-[#FEE4E2]" : "text-[#475467] hover:bg-[#F2F4F7]"}`}`}
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