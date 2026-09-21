export type AnalysisFlowMode = "new" | "legacy";

interface AnalysisFlowSelectorProps {
  value: AnalysisFlowMode;
  onChange: (value: AnalysisFlowMode) => void;
}

/** 任务级流程选择；默认值由入口页面设为 new。 */
export function AnalysisFlowSelector({ value, onChange }: AnalysisFlowSelectorProps) {
  return (
    <section
      aria-label="分析流程选择"
      className="rounded-3xl border border-[#DDE9D6] bg-white/70 p-4"
      data-testid="analysis-flow-selector"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">分析流程</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            新流程会冻结本次任务的 P1–P4 名册、发球队、比分和回合上下文；旧流程用于兼容历史分析。
          </p>
        </div>
        <span className="rounded-full bg-[#EAF8EA] px-2.5 py-1 text-xs font-bold text-[#168A34]">
          默认：新流程
        </span>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2" role="group" aria-label="选择分析流程">
        <button
          aria-pressed={value === "new"}
          className={`rounded-2xl border px-3 py-3 text-left transition ${
            value === "new"
              ? "border-[#22C55E] bg-[#F0FFF0] text-[#14241B] shadow-sm"
              : "border-[#DDE9D6] bg-white text-slate-500 hover:border-[#8FD39D]"
          }`}
          data-testid="analysis-flow-new"
          onClick={() => onChange("new")}
          type="button"
        >
          <span className="block text-sm font-bold">新流程 · 冻结上下文</span>
          <span className="mt-1 block text-xs leading-5">推荐：支持场地控制画像等依赖回合语义的分析。</span>
        </button>
        <button
          aria-pressed={value === "legacy"}
          className={`rounded-2xl border px-3 py-3 text-left transition ${
            value === "legacy"
              ? "border-[#F4B860] bg-[#FFF8EA] text-[#14241B] shadow-sm"
              : "border-[#DDE9D6] bg-white text-slate-500 hover:border-[#D8B26E]"
          }`}
          data-testid="analysis-flow-legacy"
          onClick={() => onChange("legacy")}
          type="button"
        >
          <span className="block text-sm font-bold">旧流程 · 兼容模式</span>
          <span className="mt-1 block text-xs leading-5">不冻结新上下文，保留原有分析链路。</span>
        </button>
      </div>
    </section>
  );
}
