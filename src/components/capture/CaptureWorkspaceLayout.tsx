import type { ReactNode } from "react";

interface CaptureWorkspaceLayoutProps {
  children: ReactNode;
}

export function CaptureWorkspaceLayout({ children }: CaptureWorkspaceLayoutProps) {
  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-6 py-6" style={{ background: "var(--capture-surface-page)", minHeight: "100vh" }}>
      {children}
    </div>
  );
}
