// =============================================================
// PbPlayerSelector —— 最小可用球员切换（设计 D1 / tasks 2.3）
// -------------------------------------------------------------
// 只承载 Player_1..Player_4 的切换，验证各 player evidence 是否正确切。
// 不做 PB 风格视觉优化；被去掉的左侧 Drawer 不再恢复。
// =============================================================
import { usePbReport } from "../../contexts/PbReportContext";

export default function PbPlayerSelector() {
  const { report, selectedPlayerId, setSelectedPlayerId } = usePbReport();
  const subjects =
    report?.performanceInsights?.subjects?.filter((s) => s.kind === "player") ?? [];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm font-semibold text-[var(--pb-text-secondary,#6b7280)]">
        球员
      </span>
      {subjects.length === 0 ? (
        <span className="text-sm text-[var(--pb-text-muted,#9ca3af)]">暂无球员</span>
      ) : (
        subjects.map((s) => {
          const active = s.id === selectedPlayerId;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setSelectedPlayerId(s.id)}
              className={
                "rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors " +
                (active
                  ? "border-[var(--pb-primary,#00FF41)] bg-[var(--pb-primary,#00FF41)]/10 text-[var(--pb-primary,#00FF41)]"
                  : "border-[var(--pb-card-border,#d1d5db)] bg-white text-[var(--pb-text-primary,#111827)] hover:border-[var(--pb-primary,#00FF41)]")
              }
            >
              {s.label || s.id}
            </button>
          );
        })
      )}
    </div>
  );
}