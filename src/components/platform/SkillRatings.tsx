import type { SkillRating } from "../../types/report";

interface SkillRatingsProps {
  ratings: SkillRating[];
}

export function SkillRatings({ ratings }: SkillRatingsProps) {
  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--ui-brand-deep)]">能力维度</p>
          <h2 className="mt-2 text-2xl font-black text-[var(--ui-ink)]">六维能力评分</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-600">
          不只看输赢，把每一项能力拆成可以训练的方向。
        </p>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {ratings.map((rating) => (
          <article
            className="rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-4 transition hover:-translate-y-1 hover:border-[var(--ui-brand)]/35 hover:bg-[var(--ui-surface-green-tint)]"
            key={rating.id}
          >
            <div className="flex items-start justify-between gap-4">
              <strong className="text-base leading-6 text-[var(--ui-ink)]">{rating.label}</strong>
              <span className="text-2xl font-black text-[var(--ui-brand-deep)]">{rating.score}</span>
            </div>
            <div className="mt-4 h-2 rounded-full bg-[var(--ui-surface-track-green)]">
              <span className="block h-full rounded-full bg-[var(--ui-brand-solid)]" style={{ width: `${rating.score}%` }} />
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-600">{rating.note}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
