import type { ReactNode } from "react";

export function FusionBlock({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[var(--ui-border)] bg-[var(--ui-surface)]/70 p-4">
      <span className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-[var(--ui-brand-deep)]">
        {icon}
        {label}
      </span>
      <strong className="mt-3 block text-base leading-6 text-[var(--ui-ink)]">{value}</strong>
    </div>
  );
}
