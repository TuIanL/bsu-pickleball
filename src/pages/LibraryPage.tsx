import { useEffect, useMemo, useState } from "react";
import { Search, Upload } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import type { LibraryItemViewModel, LibraryItemKind } from "../services/libraryAdapter";
import { buildLibraryItems } from "../services/libraryAdapter";
import { mergeSyncRecording, deleteRecording, deleteSyncRecording, getVideoStreamUrl } from "../services/analysisClient";
import { LibraryCard } from "../components/library/LibraryCard";

type StatusFilter = "all" | "recording" | "processing" | "ready" | "failed";

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

  // 重新分析：跳转到对应分析创建入口
  const handleReanalyze = (item: LibraryItemViewModel) => {
    if (item.ref.kind === "upload") {
      onNavigate(`/upload?videoId=${encodeURIComponent(item.ref.sourceId)}` as never);
    } else {
      onNavigate("/analysis/new");
    }
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
    if (status === "recording") list = list.filter((it) => it.mediaState === "recording");
    else if (status === "processing") list = list.filter((it) => it.mediaState === "processing");
    else if (status === "failed") list = list.filter((it) => it.mediaState === "failed" || it.analysisState === "failed");
    else if (status === "ready") list = list.filter((it) => it.mediaState === "ready");
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
    { key: "processing", label: "正在分析" },
    { key: "ready", label: "已完成" },
    { key: "failed", label: "失败" },
  ];

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {/* 页头 */}
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-black text-[#182230]">比赛库</h1>
            <p className="mt-1 text-sm text-[#667085]">统一管理比赛、训练与采集视频及其分析结果</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="inline-flex items-center gap-1.5 rounded-full border border-[#E4E7EC] bg-white px-4 py-2 text-sm font-bold text-[#182230] transition hover:bg-[#F9FAFB]"
              onClick={() => onNavigate("/upload")}
              type="button"
            >
              <Upload size={16} aria-hidden="true" />
              上传视频
            </button>
            <button
              className="inline-flex items-center gap-1.5 rounded-full bg-[#19B84C] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#168A34]"
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
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#98A2B3]" aria-hidden="true" />
            <input
              className="w-full rounded-lg border border-[#E4E7EC] bg-white py-2 pl-9 pr-3 text-sm text-[#182230] outline-none placeholder:text-[#98A2B3] focus:border-[#22C55E]"
              placeholder="搜索比赛..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-[#E4E7EC] bg-white p-1">
            {(["all", "upload", "recording", "sync_recording"] as const).map((k) => (
              <button
                key={k}
                className={`rounded-md px-3 py-1 text-xs font-bold transition ${kind === k ? "bg-[#EAF7EE] text-[#168A34]" : "text-[#667085] hover:bg-[#F2F4F7]"}`}
                onClick={() => setKind(k)}
                type="button"
              >
                {k === "all" ? "全部来源" : k === "upload" ? "上传" : k === "recording" ? "录制" : "双摄"}
              </button>
            ))}
          </div>
        </div>

        {/* 状态 tab */}
        <div className="mb-5 flex items-center gap-1 border-b border-[#E4E7EC]">
          {statusTabs.map((tab) => (
            <button
              key={tab.key}
              className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-bold transition ${status === tab.key ? "border-[#168A34] text-[#168A34]" : "border-transparent text-[#667085] hover:text-[#182230]"}`}
              onClick={() => setStatus(tab.key)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 内容 */}
        {loading ? (
          <div className="grid place-items-center py-24 text-sm text-[#98A2B3]">加载比赛中…</div>
        ) : filtered.length === 0 ? (
          <div className="grid place-items-center py-24 text-center">
            <p className="text-sm font-bold text-[#667085]">未找到比赛</p>
            <p className="mt-1 text-xs text-[#98A2B3]">试试调整筛选，或上传/采集一段视频</p>
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
          <h2 className="mb-3 text-sm font-black text-[#182230]">场次 {fieldSessionId}</h2>
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