import { useEffect, useMemo, useState } from "react";
import { Search, Upload } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import type { LibraryItemViewModel, LibraryItemKind } from "../services/libraryAdapter";
import { buildLibraryItems } from "../services/libraryAdapter";
import { mergeSyncRecording, deleteRecording, deleteSyncRecording, getVideoStreamUrl } from "../services/analysisClient";
import { libraryAnalysisPathFor } from "../services/libraryAnalysisRouting";
import { LibraryCard } from "../components/library/LibraryCard";

type StatusFilter = "all" | "pending" | "analyzing" | "completed" | "failed";

interface LibraryPageProps {
  onNavigate: NavigateFn;
}

export function LibraryPage({ onNavigate }: LibraryPageProps) {
  const [items, setItems] = useState<LibraryItemViewModel[]>([]);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [kind, setKind] = useState<LibraryItemKind | "all">("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 重新请求时重置加载态
    setLoading(true);
    buildLibraryItems()
      .then((result) => {
        if (!cancelled) setItems(result);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // D6：requiredAction=merge 时触发合并；合并后刷新库
  const handleMerge = async (item: LibraryItemViewModel) => {
    if (item.ref.kind !== "sync_recording") return;
    try {
      await mergeSyncRecording(item.ref.sourceId);
    } catch {
      console.warn(`合并失败：${item.ref.sourceId}`);
    }
    const result = await buildLibraryItems();
    setItems(result);
  };

  // 查看原视频（open stream 在新窗口）
  const handleOpenVideo = (item: LibraryItemViewModel) => {
    const videoId = item.ref.kind === "upload" ? item.ref.sourceId : undefined;
    const url = getVideoStreamUrl(videoId);
    if (url) window.open(url, "_blank", "noopener");
  };

  // 重新分析 / 开始分析：按素材类型分派到对应分析创建入口
  const handleReanalyze = (item: LibraryItemViewModel) => {
    const path = libraryAnalysisPathFor(item);
    if (path) onNavigate(path);
  };

  // 查看技术信息：进入 workspace 技术详情 view
  const handleOpenTechnical = (item: LibraryItemViewModel) => {
    onNavigate(`/library/${item.ref.kind}/${encodeURIComponent(item.ref.sourceId)}?view=technical`);
  };

  // 删除：源视频/录制资产删除为显式独立动作（D5）
  const handleDelete = async (item: LibraryItemViewModel) => {
    const label = item.title || "此素材";
    if (!window.confirm(`确定删除「${label}」吗？此操作不可撤销。`)) return;
    try {
      if (item.ref.kind === "recording") {
        await deleteRecording(item.ref.sourceId);
      } else if (item.ref.kind === "sync_recording") {
        await deleteSyncRecording(item.ref.sourceId);
      }
      // upload 的源视频删除在本次 catalog 迭代暂以「关联 job 删除」占位，避免误删源资产
    } catch (error) {
      console.warn(`删除失败：${item.ref.sourceId}`, error);
    }
    const result = await buildLibraryItems();
    setItems(result);
  };

  const filtered = useMemo(() => {
    let list = items;
    if (kind !== "all") list = list.filter((it) => it.sourceType === kind);
    // P2C：状态筛选基于统一 displayState（待处理/正在分析/分析完成/失败），不再直接读底层多轴状态
    if (status === "pending") list = list.filter((it) => it.displayState === "pending");
    else if (status === "analyzing") list = list.filter((it) => it.displayState === "analyzing");
    else if (status === "completed") list = list.filter((it) => it.displayState === "completed");
    else if (status === "failed") list = list.filter((it) => it.displayState === "failed");
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter(
        (it) => it.title.toLowerCase().includes(q) || (it.courtName ?? "").toLowerCase().includes(q),
      );
    }
    // 最近比赛默认按时间倒序
    return [...list].sort((a, b) => (Date.parse(b.startedAt ?? "") || 0) - (Date.parse(a.startedAt ?? "") || 0));
  }, [items, kind, status, query]);

  const statusTabs: { key: StatusFilter; label: string }[] = [
    { key: "all", label: "全部" },
    { key: "pending", label: "待处理" },
    { key: "analyzing", label: "正在分析" },
    { key: "completed", label: "已完成" },
    { key: "failed", label: "失败" },
  ];

  return (
    <div className="min-h-screen"
      style={{
        background: "linear-gradient(180deg, #F4F8F6 0%, #EEF3F1 100%)",
      }}
    >
      {/* 顶部弱径向渐变氛围 */}
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          background: "radial-gradient(circle at 85% 0%, rgba(87,181,142,0.10), transparent 30%)",
        }}
      />
      <div className="relative mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {/* 页头 */}
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-black text-[var(--capture-text-primary,#182b24)]">比赛库</h1>
            <p className="mt-1 text-sm text-[var(--capture-text-secondary,#64736c)]">统一管理比赛、训练与采集视频及其分析结果</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-card,#ffffff)] px-4 py-2 text-sm font-bold text-[var(--capture-text-primary,#182b24)] transition hover:bg-[var(--capture-surface-soft,#f7faf8)]"
              onClick={() => onNavigate("/upload")}
              type="button"
            >
              <Upload size={16} aria-hidden="true" />
              上传视频
            </button>
            <button
              className="inline-flex items-center gap-1.5 rounded-full bg-[var(--capture-brand-strong,#197947)] px-4 py-2 text-sm font-bold text-white transition hover:bg-[var(--capture-brand-primary-hover,#14683d)]"
              onClick={() => onNavigate("/capture")}
              type="button"
            >
              开始采集
            </button>
          </div>
        </div>

        {/* 搜索与来源筛选 */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--capture-text-muted,#8f9d96)]" aria-hidden="true" />
            <input
              className="w-full rounded-lg border border-[var(--capture-border-default,#d9e3dd)] bg-[#FAFCFB] py-2 pl-9 pr-3 text-sm text-[var(--capture-text-primary,#182b24)] outline-none placeholder:text-[var(--capture-text-muted,#8f9d96)] focus:border-[var(--capture-brand-primary,#23985b)]"
              placeholder="搜索比赛..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-soft,#f7faf8)] p-1">
            {(["all", "upload", "recording", "sync_recording"] as const).map((k) => (
              <button
                key={k}
                className={`rounded-md px-3 py-1 text-xs font-bold transition ${kind === k ? "bg-[#E4F2E9] text-[var(--capture-brand-primary,#23985b)]" : "text-[var(--capture-text-secondary,#64736c)] hover:bg-[var(--capture-border-default,#d9e3dd)]/40"}`}
                onClick={() => setKind(k)}
                type="button"
              >
                {k === "all" ? "全部来源" : k === "upload" ? "上传" : k === "recording" ? "录制" : "双摄"}
              </button>
            ))}
          </div>
        </div>

        {/* 状态 tab */}
        <div className="mb-5 flex items-center gap-1 border-b border-[var(--capture-border-default,#d9e3dd)]">
          {statusTabs.map((tab) => (
            <button
              key={tab.key}
              className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-bold transition ${status === tab.key ? "border-[var(--capture-brand-primary,#23985b)] text-[var(--capture-brand-primary,#23985b)]" : "border-transparent text-[var(--capture-text-secondary,#64736c)] hover:text-[var(--capture-text-primary,#182b24)]"}`}
              onClick={() => setStatus(tab.key)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 内容 */}
        {loading ? (
          <div className="grid place-items-center py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">加载比赛中…</div>
        ) : filtered.length === 0 ? (
          <div className="grid place-items-center py-24 text-center">
            <p className="text-sm font-bold text-[var(--capture-text-secondary,#64736c)]">未找到比赛</p>
            <p className="mt-1 text-xs text-[var(--capture-text-muted,#8f9d96)]">试试调整筛选，或上传/采集一段视频</p>
          </div>
        ) : (
          <LibraryGrid
            items={filtered}
            onNavigate={onNavigate}
            onMerge={handleMerge}
            onDelete={handleDelete}
            onOpenVideo={handleOpenVideo}
            onOpenTechnical={handleOpenTechnical}
            onReanalyze={handleReanalyze}
          />
        )}
      </div>
    </div>
  );
}

/** 场次分组的语义化标题（不暴露 raw fieldSessionId） */
function formatDate(iso?: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (!Number.isFinite(d.getTime())) return "";
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  } catch {
    return "";
  }
}

function groupLabel(list: LibraryItemViewModel[]): string {
  const first = list[0];
  if (!first) return "比赛素材";
  const date = first.startedAt ? formatDate(first.startedAt) : "";
  const venue = first.courtName ?? first.venue;
  if (date && venue) return `${date} · ${venue}`;
  if (date) return date;
  return "比赛素材";
}

/** 按 FieldSession（场次）分组的卡片网格；无场次归属的素材落在「最近比赛」区 */
function LibraryGrid({
  items,
  onNavigate,
  onMerge,
  onDelete,
  onOpenVideo,
  onOpenTechnical,
  onReanalyze,
}: {
  items: LibraryItemViewModel[];
  onNavigate: NavigateFn;
  onMerge?: (item: LibraryItemViewModel) => void;
  onDelete?: (item: LibraryItemViewModel) => void;
  onOpenVideo?: (item: LibraryItemViewModel) => void;
  onOpenTechnical?: (item: LibraryItemViewModel) => void;
  onReanalyze?: (item: LibraryItemViewModel) => void;
}) {
  const grouped = useMemo(() => {
    const groups = new Map<string, LibraryItemViewModel[]>();
    const ungrouped: LibraryItemViewModel[] = [];
    for (const item of items) {
      const key = item.fieldSessionId ?? "";
      if (key) {
        const list = groups.get(key) ?? [];
        list.push(item);
        groups.set(key, list);
      } else {
        ungrouped.push(item);
      }
    }
    return { groups, ungrouped };
  }, [items]);

  const renderGrid = (list: LibraryItemViewModel[]) => (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {list.map((item) => (
        <LibraryCard
          key={`${item.ref.kind}:${item.ref.sourceId}`}
          item={item}
          onNavigate={onNavigate}
          onMerge={onMerge}
          onDelete={onDelete}
          onOpenVideo={onOpenVideo}
          onOpenTechnical={onOpenTechnical}
          onReanalyze={onReanalyze}
        />
      ))}
    </div>
  );

  return (
    <div className="space-y-8">
      {[...grouped.groups.entries()].map(([fieldSessionId, list]) => (
        <section key={fieldSessionId}>
          <h2 className="mb-3 text-sm font-black text-[#182230]">{groupLabel(list)}</h2>
          {renderGrid(list)}
        </section>
      ))}
      {grouped.ungrouped.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-black text-[#182230]">最近比赛</h2>
          {renderGrid(grouped.ungrouped)}
        </section>
      )}
    </div>
  );
}