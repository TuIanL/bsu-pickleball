import { usePbReport } from "../../contexts/PbReportContext";
import {
  PB_SHOT_TYPE_OPTIONS,
  PB_STAGE_OPTIONS,
} from "../../types/pbReport";

export default function PbFilterToolbar() {
  const {
    stageFilter,
    setStageFilter,
    typeFilter,
    setTypeFilter,
    qualityThreshold,
    setQualityThreshold,
  } = usePbReport();

  const selectBaseClass =
    "rounded-lg border border-[var(--pb-card-border,#d1d5db)] bg-white px-3 py-2 text-sm font-medium text-[var(--pb-text-primary,#111827)] focus:outline-none focus:ring-2 focus:ring-[var(--pb-primary,#00FF41)] focus:border-[var(--pb-primary,#00FF41)] transition-colors";

  return (
    <div className="pb-card p-3 sm:p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--pb-text-secondary,#6b7280)] whitespace-nowrap">
            📍 击球阶段
          </span>
          <select
            className={selectBaseClass}
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value as typeof stageFilter)}
          >
            {PB_STAGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--pb-text-secondary,#6b7280)] whitespace-nowrap">
            🎯 击球类型
          </span>
          <select
            className={selectBaseClass}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)}
          >
            {PB_SHOT_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          className="pb-btn-primary flex items-center gap-2"
          onClick={() => {
            console.warn(
              "击球探索按钮占位，待接入详情页面跳转逻辑"
            );
          }}
        >
          <span>击球探索</span>
          <span className="text-xs">↗</span>
        </button>

        <div className="flex items-center gap-3 flex-1 min-w-[240px]">
          <span className="text-sm font-semibold text-[var(--pb-text-secondary,#6b7280)] whitespace-nowrap">
            ✨ 击球质量
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={qualityThreshold}
            onChange={(e) => setQualityThreshold(Number(e.target.value))}
            className="pb-range-slider flex-1 min-w-[180px]"
          />
          <span className="text-sm font-semibold text-[var(--pb-text-primary,#111827)] whitespace-nowrap tabular-nums min-w-[48px] text-right">
            {qualityThreshold} %
          </span>
        </div>
      </div>
    </div>
  );
}
