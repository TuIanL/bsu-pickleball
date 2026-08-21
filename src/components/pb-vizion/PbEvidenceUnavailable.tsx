// =============================================================
// PbEvidenceUnavailable —— 缺数据的统一空态
// -------------------------------------------------------------
// 真实 job 缺指标时显示"本次分析暂未生成"，绝不回退近似值（invariant #3）。
// =============================================================
export default function PbEvidenceUnavailable({ reason }: { reason?: string }) {
  return (
    <div className="flex h-full min-h-[120px] w-full items-center justify-center rounded-xl border border-dashed border-gray-200 bg-gray-50/50 p-4 text-center">
      <div>
        <div className="text-sm font-semibold text-[var(--pb-text-secondary,#6b7280)]">
          本次分析暂未生成
        </div>
        {reason ? (
          <div className="mt-1 text-xs text-[var(--pb-text-muted,#9ca3af)]">{reason}</div>
        ) : null}
      </div>
    </div>
  );
}