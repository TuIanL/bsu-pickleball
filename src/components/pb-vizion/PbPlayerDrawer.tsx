// =============================================================
// PB Vision 报告页 - 左侧球员抽屉栏
// =============================================================
import { usePbReport, usePbAllSubjects } from "../../contexts/PbReportContext";

/** 球员圆形头像占位（无真实头像时用渐变背景 + 首字母） */
function PlayerAvatar({ name, size = 36 }: { name: string; size?: number }) {
  const initials = name?.trim().slice(0, 1).toUpperCase() || "P";
  const hue =
    name.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % 360;
  const bg = `linear-gradient(135deg, hsl(${hue} 85% 65%), hsl(${(hue + 40) % 360} 80% 55%))`;
  return (
    <div
      className="flex items-center justify-center rounded-full text-white font-semibold shrink-0"
      style={{
        background: bg,
        width: size,
        height: size,
        fontSize: size * 0.4,
      }}
    >
      {initials}
    </div>
  );
}

/** 导航项（视觉占位，暂不做跳转） */
function NavItem({
  icon,
  label,
  active = false,
}: {
  icon: string;
  label: string;
  active?: boolean;
}) {
  return (
    <div
      className={
        "flex items-center gap-3 px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors " +
        (active
          ? "bg-[var(--pb-primary-soft,#e6ffe9)] text-[var(--pb-primary-dark,#00cc33)] font-semibold"
          : "text-[var(--pb-text-secondary,#6b7280)] hover:bg-black/5 hover:text-[var(--pb-text-primary,#111827)]")
      }
    >
      <span className="text-lg w-6 text-center">{icon}</span>
      <span>{label}</span>
    </div>
  );
}

export default function PbPlayerDrawer() {
  const {
    selectedPlayerId,
    setSelectedPlayerId,
    drawerOpen,
    toggleDrawer,
  } = usePbReport();
  const subjects = usePbAllSubjects();

  if (!drawerOpen) return null;

  return (
    <>
      {/* 抽屉主体 */}
      <aside
        className="fixed left-0 top-0 h-screen w-[260px] z-40 flex flex-col border-r border-[var(--pb-card-border,#e5e7eb)] bg-[var(--pb-card-bg,#ffffff)]"
        style={{ boxShadow: "1px 0 8px rgba(0,0,0,0.04)" }}
      >
        {/* 顶部折叠按钮 + Logo */}
        <div className="flex items-center justify-between px-4 h-14 border-b border-[var(--pb-card-border,#e5e7eb)] shrink-0">
          <div className="font-bold text-[var(--pb-text-primary,#111827)] tracking-wide">
            匹克球分析报告
          </div>
          <button
            type="button"
            aria-label="收起抽屉"
            onClick={toggleDrawer}
            className="w-8 h-8 rounded-md flex items-center justify-center text-[var(--pb-text-secondary,#6b7280)] hover:bg-black/5 transition"
          >
            ✕
          </button>
        </div>

        {/* 导航区（5 项占位，第一个高亮） */}
        <nav className="flex flex-col gap-1 px-2 py-3 border-b border-[var(--pb-card-border,#e5e7eb)] shrink-0">
          <NavItem icon="🎬" label="首页" active />
          <NavItem icon="📹" label="击球探索" />
          <NavItem icon="📊" label="比赛数据" />
          <NavItem icon="🏆" label="排行榜" />
          <NavItem icon="👥" label="团队数据" />
        </nav>

        {/* 球员列表 */}
        <div className="px-2 pt-3 pb-1 flex flex-col gap-1">
          <div className="px-2 pb-2 text-xs font-semibold text-[var(--pb-text-muted,#9ca3af)] uppercase tracking-wider">
            球员统计
          </div>
          <div className="flex flex-col gap-1 overflow-y-auto scrollbar-none pr-1">
            {subjects.map((s) => {
              const active = s.id === selectedPlayerId;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSelectedPlayerId(s.id)}
                  className={
                    "w-full flex items-center gap-3 px-2 py-2 rounded-lg text-left transition-all " +
                    (active
                      ? "bg-[#4b5563] text-white shadow-sm"
                      : "hover:bg-black/5 text-[var(--pb-text-primary,#111827)]")
                  }
                >
                  <PlayerAvatar name={s.name} size={34} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{s.name}</div>
                    {s.role && (
                      <div className={"text-xs truncate " + (active ? "text-white/70" : "text-[var(--pb-text-muted,#9ca3af)]")}>
                        {s.role}
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* 底部：空白撑开 + Share 按钮 + 切换旧版（可选 7.6） */}
        <div className="mt-auto px-3 py-4 flex flex-col gap-2 border-t border-[var(--pb-card-border,#e5e7eb)] shrink-0">
          <button
            type="button"
            className="pb-btn-primary w-full flex items-center justify-center gap-2"
            onClick={() => {
              // Share 占位
              if (typeof window !== "undefined") {
                try {
                  // 优先走原生 share，如果不支持则 fallback toast（后续改 console）
                  if (typeof (navigator as Navigator & { share?: unknown }).share === "function") {
                    // 暂时跳过，打印日志
                  }
                } catch {
                  /* ignore */
                }
                console.warn("分享按钮占位，待接入分享逻辑");
                alert("分享功能占位");
              }
            }}
          >
            <span>🔗</span>
            <span>分享比赛</span>
          </button>

          {/* 任务 7.6：切换旧版按钮（默认已实现，方便 AB 对比） */}
          <button
            type="button"
            className="w-full text-xs rounded-lg px-3 py-2 text-[var(--pb-text-secondary,#6b7280)] border border-[var(--pb-card-border,#e5e7eb)] hover:bg-black/5 transition"
            onClick={() => {
              if (typeof window !== "undefined") {
                window.localStorage.setItem("reportLegacy", "1");
                const next = new URL(window.location.href);
                next.searchParams.set("legacy", "1");
                window.location.href = next.toString();
              }
            }}
          >
            切换旧版
          </button>
        </div>
      </aside>
    </>
  );
}

/** 侧边展开条（抽屉关闭时显示在左侧，点击重新展开） */
export function PbDrawerExpander() {
  const { drawerOpen, toggleDrawer } = usePbReport();
  if (drawerOpen) return null;
  return (
    <button
      type="button"
      aria-label="展开抽屉"
      onClick={toggleDrawer}
      className="fixed left-0 top-1/2 -translate-y-1/2 z-40 w-6 h-20 rounded-r-lg border border-l-0 border-[var(--pb-card-border,#e5e7eb)] bg-white/90 backdrop-blur text-[var(--pb-text-secondary,#6b7280)] hover:text-[var(--pb-primary-dark,#00cc33)] hover:border-[var(--pb-primary,#00FF41)] transition-all shadow-sm flex items-center justify-center text-sm font-bold"
    >
      ›
    </button>
  );
}
