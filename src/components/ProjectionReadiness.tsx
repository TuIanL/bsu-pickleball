export function ProjectionReadiness({ body, label, ready }: { body: string; label: string; ready: boolean }) {
  return (
    <div className="rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-3">
      <div className="flex items-center justify-between gap-3">
        <strong className="text-sm text-[var(--ui-ink)]">{label}</strong>
        <span className={`rounded-full px-2.5 py-1 text-xs font-black ${ready ? "bg-[var(--ui-brand-solid)]/14 text-[var(--ui-brand-deep)]" : "bg-slate-100 text-slate-600"}`}>
          {ready ? "就绪" : "待接入"}
        </span>
      </div>
      <p className="mt-2 text-xs font-semibold leading-5 text-slate-500">{body}</p>
    </div>
  );
}
