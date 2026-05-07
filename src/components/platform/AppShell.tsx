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
  onNavigate: (path: AppPath | "/reports/landing" | "/upload") => void;
}

export function AppShell({ activePath, children, navigation, onNavigate }: AppShellProps) {
  const isActive = (path: string) => {
    if (path === "/") {
      return activePath === "/";
    }

    if (path === "/analysis/new") {
      return activePath === "/analysis/new";
    }

    if (path === "/reports/landing") {
      return activePath.startsWith("/reports");
    }

    return activePath === path;
  };

  return (
    <div className="min-h-screen overflow-x-hidden text-[#17231D]">
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
              <span className="block truncate text-xs text-slate-400">智能比赛分析 · 训练展示原型</span>
            </span>
          </button>

          <nav className="hidden flex-1 justify-center lg:flex" aria-label="主导航">
            <div className="flex items-center gap-1 rounded-full border border-[#DDE9D6] bg-[#F1F7EC] p-1">
              {navigation.map((item) => (
                <button
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    isActive(item.path)
                      ? "bg-[#17231D] text-white shadow-sm"
                      : "text-slate-600 hover:bg-white hover:text-[#17231D]"
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
              查看演示
            </button>
            <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
              <Upload size={16} aria-hidden="true" />
              上传比赛
            </button>
          </div>

          <button
            className="hidden items-center gap-2 rounded-full border border-[#DDE9D6] bg-white/85 py-1.5 pl-1.5 pr-3 text-sm font-semibold text-slate-700 transition hover:border-[#22C55E]/35 hover:bg-[#F5FFF2] sm:flex"
            onClick={() => onNavigate("/training")}
            type="button"
          >
            <span className="grid size-8 place-items-center rounded-full bg-[#D9FF3F] text-[#071008]">
              <UserRound size={15} aria-hidden="true" />
            </span>
            荧光队
          </button>
        </div>

        <div className="mx-auto flex max-w-[1480px] gap-2 overflow-x-auto px-4 pb-3 sm:px-6 lg:hidden">
          {navigation.map((item) => (
            <button
              className={`shrink-0 rounded-full border px-3 py-2 text-xs font-bold transition ${
                isActive(item.path)
                  ? "border-[#22C55E] bg-[#22C55E] text-[#071008]"
                  : "border-[#DDE9D6] bg-white/85 text-slate-700"
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

      <footer className="border-t border-[#DDE9D6] px-4 py-8 text-sm text-slate-500 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[1480px] flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>拍动视析 · 北京体育大学体育工程学院创新训练项目展示原型</span>
          <button
            className="inline-flex w-fit items-center gap-1 font-semibold text-slate-700 transition hover:text-[#168A34]"
            onClick={() => onNavigate("/analysis/new")}
            type="button"
          >
            上传比赛视频
            <ChevronRight size={15} aria-hidden="true" />
          </button>
        </div>
      </footer>
    </div>
  );
}
