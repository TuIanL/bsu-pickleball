import {
  Activity,
  Camera,
  ChevronRight,
  Upload,
  UserRound,
} from "lucide-react";
import type { ReactNode } from "react";
import type { AppPath, NavigationItem } from "../../types/report";

interface AppShellProps {
  activePath: string;
  children: ReactNode;
  navigation: NavigationItem[];
  onNavigate: (path: AppPath | "/reports/landing") => void;
}

export function AppShell({ activePath, children, navigation, onNavigate }: AppShellProps) {
  const isActive = (path: string) => {
    if (path === "/") {
      return activePath === "/";
    }

    if (path === "/reports/landing") {
      return activePath.startsWith("/reports");
    }

    return activePath === path;
  };

  return (
    <div className="min-h-screen overflow-x-hidden text-slate-50">
      <header className="sticky top-0 z-50 border-b border-white/10 bg-[#070A0D]/88 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-[1480px] items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <button
            className="group flex min-w-0 items-center gap-3 text-left"
            onClick={() => onNavigate("/")}
            type="button"
          >
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl border border-[#54FE49]/30 bg-[#13D208]/14 text-[#54FE49] shadow-[0_0_28px_rgba(84,254,73,0.22)] transition group-hover:scale-105">
              <Activity size={22} aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-base font-black tracking-[0.02em]">
                PickleMotion AI
              </span>
              <span className="block truncate text-xs text-slate-400">拍动视析 · AI 比赛分析</span>
            </span>
          </button>

          <nav className="hidden flex-1 justify-center lg:flex" aria-label="Primary navigation">
            <div className="flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.045] p-1">
              {navigation.map((item) => (
                <button
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    isActive(item.path)
                      ? "bg-white text-[#071008]"
                      : "text-slate-300 hover:bg-white/10 hover:text-white"
                  }`}
                  key={item.id}
                  onClick={() => onNavigate(item.path)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </nav>

          <div className="ml-auto hidden items-center gap-2 md:flex">
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/vision")} type="button">
              <Camera size={16} aria-hidden="true" />
              View Demo
            </button>
            <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/vision")} type="button">
              <Upload size={16} aria-hidden="true" />
              Upload Match
            </button>
          </div>

          <button
            className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] py-1.5 pl-1.5 pr-3 text-sm font-semibold text-slate-200 transition hover:bg-white/10 sm:flex"
            onClick={() => onNavigate("/training")}
            type="button"
          >
            <span className="grid size-8 place-items-center rounded-full bg-[#D9FF3F] text-[#071008]">
              <UserRound size={15} aria-hidden="true" />
            </span>
            Team Lime
          </button>
        </div>

        <div className="mx-auto flex max-w-[1480px] gap-2 overflow-x-auto px-4 pb-3 sm:px-6 lg:hidden">
          {navigation.map((item) => (
            <button
              className={`shrink-0 rounded-full border px-3 py-2 text-xs font-bold transition ${
                isActive(item.path)
                  ? "border-[#54FE49] bg-[#54FE49] text-[#071008]"
                  : "border-white/10 bg-white/[0.055] text-slate-300"
              }`}
              key={item.id}
              onClick={() => onNavigate(item.path)}
              type="button"
            >
              {item.shortLabel}
            </button>
          ))}
        </div>
      </header>

      <main>{children}</main>

      <footer className="border-t border-white/10 px-4 py-8 text-sm text-slate-500 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[1480px] flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>PickleMotion AI · 北京体育大学体育工程学院创新训练项目展示原型</span>
          <button
            className="inline-flex w-fit items-center gap-1 font-semibold text-slate-300 transition hover:text-[#54FE49]"
            onClick={() => onNavigate("/vision")}
            type="button"
          >
            Open visual workspace
            <ChevronRight size={15} aria-hidden="true" />
          </button>
        </div>
      </footer>
    </div>
  );
}
