export function TaskMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[var(--ui-surface-soft)] p-3">
      <span className="block text-xs font-black uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <strong className="mt-1 block break-words text-[var(--ui-ink)]">{value}</strong>
    </div>
  );
}
