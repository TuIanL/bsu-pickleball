import { useEffect, useRef } from "react";
import { ANALYSIS_MODES, analysisModeLabel } from "../../utils/analysisHelpers";
import type { AnalysisModeValue } from "../../utils/analysisHelpers";

/** 「按类型选择」弹层中的一行：分析模式 + 可删任务计数 + 勾选三态 */
export interface AnalysisModeSelectRow {
  mode: AnalysisModeValue;
  eligibleCount: number;
  state: "checked" | "indeterminate" | "unchecked";
}

/** 列表分类筛选值：全部，或某一分析模式 */
export type AnalysisModeFilter = AnalysisModeValue | "all";

interface AnalysisModeSelectPopoverProps {
  /** 是否打开弹层 */
  open: boolean;
  /** 关闭回调：点击外部或按 Escape 时触发，面板内点击不会触发 */
  onClose: () => void;
  /** 三个分析模式的行数据（含计数与三态） */
  rows: AnalysisModeSelectRow[];
  /** 勾选/取消勾选某模式：参数为该模式与目标勾选状态 */
  onToggleMode: (mode: AnalysisModeValue, check: boolean) => void;
  /** 当前列表筛选值（「全部」或某分析模式） */
  modeFilter: AnalysisModeFilter;
  /** 点击筛选项：选择某个分析模式或「全部」；点击当前激活项表示回到「全部」由调用方处理 */
  onSelectModeFilter: (mode: AnalysisModeFilter) => void;
}

/**
 * 按分析模式「分类筛选 + 批量选择」的轻量弹层，分两区：
 * - 筛选区（单选）：全部 / 样例任务 / 有限分析 / 真实视频分析，点击即过滤下方任务列表；
 * - 选择区（多选）：勾选某模式 = 选中该类全部可删除任务，取消 = 同步移除。
 * 行为：点击外部（mousedown/touchstart）或 Escape 关闭；面板内点击不关闭。
 */
export function AnalysisModeSelectPopover({
  open,
  onClose,
  rows,
  onToggleMode,
  modeFilter,
  onSelectModeFilter,
}: AnalysisModeSelectPopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (panelRef.current && !panelRef.current.contains(target)) {
        onClose();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div
      ref={panelRef}
      aria-label="按类型筛选与选择"
      className="absolute right-0 top-full z-30 mt-2 w-72 rounded-2xl border border-[#DDE9D6] bg-white p-3 shadow-lg"
      role="menu"
    >
      <p className="px-2 pb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#168A34]">按类型筛选</p>
      <div className="flex flex-wrap gap-1.5 px-1">
        <button
          aria-pressed={modeFilter === "all"}
          className={`rounded-full px-2.5 py-1 text-xs font-bold transition ${
            modeFilter === "all" ? "bg-[#17231D] text-white" : "bg-[#F1F7EC] text-slate-600 hover:bg-[#E8F2DC]"
          }`}
          onClick={() => onSelectModeFilter("all")}
          type="button"
        >
          全部
        </button>
        {ANALYSIS_MODES.map((mode) => (
          <button
            aria-pressed={modeFilter === mode}
            className={`rounded-full px-2.5 py-1 text-xs font-bold transition ${
              modeFilter === mode ? "bg-[#17231D] text-white" : "bg-[#F1F7EC] text-slate-600 hover:bg-[#E8F2DC]"
            }`}
            key={mode}
            onClick={() => onSelectModeFilter(mode)}
            type="button"
          >
            {analysisModeLabel(mode)}
          </button>
        ))}
      </div>

      <p className="mt-3 px-2 pb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#168A34]">批量选择</p>
      <div className="grid gap-1">
        {rows.map((row) => (
          <label
            className="flex cursor-pointer items-center justify-between gap-3 rounded-xl px-2 py-2 transition hover:bg-[#F5FAF1]"
            key={row.mode}
          >
            <span className="inline-flex items-center gap-2.5 text-sm font-semibold text-[#14241B]">
              <input
                checked={row.state === "checked"}
                className="size-4 accent-[#22C55E]"
                disabled={row.eligibleCount === 0}
                onChange={(event) => onToggleMode(row.mode, event.target.checked)}
                ref={(element) => {
                  if (element) {
                    element.indeterminate = row.state === "indeterminate";
                  }
                }}
                type="checkbox"
              />
              {analysisModeLabel(row.mode)}
            </span>
            <span className="rounded-full bg-[#F1F7EC] px-2 py-0.5 text-xs font-bold text-[#168A34]">
              {row.eligibleCount}
            </span>
          </label>
        ))}
      </div>
      <p className="mt-2 border-t border-[#EEF3E8] px-2 pt-2 text-xs leading-5 text-slate-500">
        筛选点击类型后列表只显示该类；勾选类型即选中该类全部可删除任务，删除请使用「批量删除」。
      </p>
    </div>
  );
}
