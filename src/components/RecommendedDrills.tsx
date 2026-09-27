import { ArrowRight } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { supportedReportTypes } from "../app/router";
import { drillRecommendations } from "../data/demoData";
import type { DrillRecommendation } from "../types/report";

export function RecommendedDrills({
  drills = drillRecommendations,
  onNavigate,
}: {
  drills?: DrillRecommendation[];
  onNavigate: NavigateFn;
}) {
  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--ui-brand-deep)]">推荐训练</p>
          <h2 className="mt-2 text-2xl font-black text-[var(--ui-ink)]">数据变成训练任务</h2>
        </div>
        <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/training")} type="button">
          查看完整计划
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
      <DrillGrid drills={drills} onNavigate={onNavigate} />
    </section>
  );
}

function DrillGrid({
  drills,
  onNavigate,
}: {
  drills: DrillRecommendation[];
  onNavigate: NavigateFn;
}) {
  return (
    <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {drills.map((drill) => (
        <article
          className="rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-4 transition hover:-translate-y-1 hover:border-[var(--ui-brand)]/35 hover:bg-[var(--ui-surface-green-tint)]"
          key={drill.id}
        >
          <div className="flex items-start justify-between gap-3">
            <span className="rounded-full border border-[var(--ui-brand)]/30 bg-[var(--ui-brand-solid)]/12 px-2.5 py-1 text-xs font-black text-[var(--ui-brand-deep)]">
              {drill.difficulty}
            </span>
            <span className="text-xs font-bold text-slate-500">{drill.duration}</span>
          </div>
          <h3 className="mt-4 text-lg font-black text-[var(--ui-ink)]">{drill.title}</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">{drill.goal}</p>
          <p className="mt-4 rounded-2xl bg-[#F0F6EA] p-3 text-xs leading-5 text-slate-600">{drill.evidence}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="green-button px-3 py-2 text-xs" onClick={() => onNavigate("/training")} type="button">
              加入训练计划
            </button>
            <button
              className="quiet-button px-3 py-2 text-xs"
              onClick={() => onNavigate(`/reports/${supportedReportTypes.includes(drill.linkedReport) ? drill.linkedReport : "movement"}`)}
              type="button"
            >
              查看依据
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
