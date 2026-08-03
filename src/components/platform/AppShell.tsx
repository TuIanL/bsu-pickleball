import {
  Activity,
  ListTodo,
} from "lucide-react";
import type { ReactNode } from "react";
import type { AppShellMode, NavigationSection, AppPath } from "../../app/navigationTypes";
import { AppSidebar } from "./AppSidebar";

interface AppShellProps {
  shellMode: AppShellMode;
  navigationSection: NavigationSection | null;
  children: ReactNode;
  onNavigate: (path: AppPath | `/upload` | `/upload?${string}`) => void;
}

export function AppShell({ shellMode, navigationSection, children, onNavigate }: AppShellProps) {
  const isLanding = shellMode === "landing";

  return (
    <div className="min-h-screen overflow-x-hidden text-[#17231D]">
      {/* Sidebar: visible in standard + capture mode */}
      {!isLanding && (
        <AppSidebar navigationSection={navigationSection} onNavigate={onNavigate} />
      )}

      {/* Topbar: only in landing mode */}
      {isLanding && (
        <header className="sticky top-0 z-50 border-b border-[#DDE9D6]/90 bg-white/88 backdrop-blur-2xl">
          <div className="mx-auto flex max-w-[1480px] items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
            <button
              className="group flex min-w-0 items-center gap-3 text-left"
              onClick={() => onNavigate("/")}
              type="button"
            >
              <span className="grid size-11 shrink-0 place-items-center rounded-2xl border border-[#22C55E]/30 bg-[#19B84C]/14 text-[#168A34] shadow-[0_0_28px_rgba(34,197,94,0.22)] transition group-hover:scale-105">
                <Activity size={22} aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-base font-black tracking-[0.02em]">
                  拍动视析
                </span>
                <span className="block truncate text-xs text-slate-400">匹克球运动表现智能分析平台</span>
              </span>
            </button>
            <div className="ml-auto flex items-center gap-2">
              <button
                className="quiet-button px-4 py-2.5"
                onClick={() => onNavigate("/analysis/tasks")}
                type="button"
              >
                <ListTodo size={16} aria-hidden="true" />
                任务历史
              </button>
            </div>
          </div>
        </header>
      )}

      {/* Main content area */}
      <main className={!isLanding ? "ml-16 sm:ml-[216px]" : undefined}>
        {children}
      </main>

      {/* Footer: only in landing mode */}
      {isLanding && (
        <footer className="border-t border-[#DDE9D6] px-4 py-8 text-sm text-slate-500 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1480px] flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>拍动视析 · 北京体育大学体育工程学院创新训练项目</span>
            <span className="text-xs text-slate-400">基于视觉捕捉与智能传感的运动表现分析平台</span>
          </div>
        </footer>
      )}
    </div>
  );
}
