import type { ReactNode } from "react";

export function PageFrame({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return (
    <div className={`mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 ${compact ? "py-8" : "py-10 lg:py-12"}`}>
      {children}
    </div>
  );
}
