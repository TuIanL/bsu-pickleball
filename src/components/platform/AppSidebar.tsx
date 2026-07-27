import {
  Activity,
  AlertTriangle,
  FileText,
  LayoutDashboard,
  Loader2,
  Monitor,
  PlaySquare,
  Settings,
  Square,
  Video,
} from "lucide-react";
import { useActiveCaptureTake, type ActiveCaptureTakeSummary } from "../../hooks/useActiveCaptureTake";
import { computeCaptureElapsedMs } from "../capture/captureClock";
import type { NavigationSection, AppPath } from "../../app/navigationTypes";

interface NavItem {
  section: NavigationSection;
  label: string;
  icon: typeof Activity;
  path: AppPath;
}

const navItems: NavItem[] = [
  { section: "capture", label: "工作台", icon: LayoutDashboard, path: "/workspace" as AppPath },
  { section: "videos", label: "视频管理", icon: Video, path: "/analysis/tasks" },
  { section: "analysis", label: "分析任务", icon: PlaySquare, path: "/capture" },
  { section: "reports", label: "报告中心", icon: FileText, path: "/reports/movement" },
  { section: "devices", label: "设备管理", icon: Monitor, path: "/camera" },
  { section: "settings", label: "设置", icon: Settings, path: "/training" },
];

interface AppSidebarProps {
  navigationSection: NavigationSection | null;
  onNavigate: (path: AppPath | `/upload` | `/upload?${string}`) => void;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function formatVideoSpec(videoSpec: ActiveCaptureTakeSummary["videoSpec"]): string {
  if (!videoSpec) return "";
  const parts: string[] = [];
  if (videoSpec.width && videoSpec.height) parts.push(`${videoSpec.width}x${videoSpec.height}`);
  if (videoSpec.fps) parts.push(`${videoSpec.fps}fps`);
  return parts.join(" · ");
}

function ActiveRecordingBlock({
  activeTake,
  onNavigate,
  isOrphan,
  forceCancel,
  forceCancelling,
}: {
  activeTake: ActiveCaptureTakeSummary;
  onNavigate: AppSidebarProps["onNavigate"];
  isOrphan: boolean;
  forceCancel: () => void;
  forceCancelling: boolean;
}) {
  const elapsedMs = computeCaptureElapsedMs(activeTake.startedAt);
  const isInsane = elapsedMs > 3600_000 * 24;

  const handleForceCancel = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("确定要强制终止此录制吗？终止后录制将标记为失败。")) return;
    forceCancel();
  };

  return (
    <div className="border-t border-[#E4E7EC]">
      <button
        className="px-3 py-3 w-full text-left hover:bg-[#F9FAFB] transition"
        onClick={() => {
          const route = `/capture/${activeTake.fieldSessionId}` as AppPath;
          onNavigate(route);
        }}
        type="button"
      >
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#E5484D] opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[#E5484D]" />
            </span>
            <span className="text-xs font-bold text-[#182230]">
              {isInsane ? "--:--:--" : formatElapsed(elapsedMs)}
            </span>
          </div>
          {activeTake.title && (
            <p className="text-xs text-[#475467] truncate">{activeTake.title}</p>
          )}
          {activeTake.courtName && (
            <p className="text-xs text-[#98A2B3] truncate">{activeTake.courtName}</p>
          )}
          <p className="text-xs text-[#98A2B3]">
            {activeTake.captureMode === "dual" ? "双路同步" : "单路录制"}
            {activeTake.videoSpec ? ` · ${formatVideoSpec(activeTake.videoSpec)}` : ""}
          </p>
        </div>
      </button>
      {isOrphan && (
        <div className="px-3 pb-3">
          <div className="flex items-center gap-1.5 text-[#F59E0B] text-[10px] mb-2">
            <AlertTriangle size={12} />
            <span>录制已中断</span>
          </div>
          <button
            className="w-full flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold text-white bg-[#E5484D] hover:bg-[#D43F44] transition disabled:opacity-50"
            onClick={handleForceCancel}
            disabled={forceCancelling}
            type="button"
          >
            {forceCancelling ? (
              <><Loader2 size={12} className="animate-spin" />终止中…</>
            ) : (
              <><Square size={10} />强制终止</>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

export function AppSidebar({ navigationSection, onNavigate }: AppSidebarProps) {
  const { activeTake, isOrphan, forceCancel, forceCancelling } = useActiveCaptureTake();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-16 sm:w-[216px] bg-white border-r border-[#E4E7EC] flex flex-col z-40">
      <button className="flex items-center justify-center gap-2 px-2 sm:justify-start sm:px-4 h-16 shrink-0 w-full text-left hover:bg-[#F9FAFB] transition" onClick={() => onNavigate("/")} type="button">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-[#22C55E]/30 bg-[#19B84C]/14 text-[#168A34]">
          <Activity size={20} aria-hidden="true" />
        </span>
        <span className="hidden min-w-0 sm:block">
          <span className="block text-sm font-black tracking-[0.02em] text-[#182230]">
            拍动视析
          </span>
          <span className="block text-[10px] text-[#98A2B3]">匹克球运动分析</span>
        </span>
      </button>

      <nav className="flex-1 px-2 py-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = navigationSection === item.section;
          return (
            <button
              key={item.section}
              className={`w-full flex items-center justify-center gap-2.5 px-2 py-2.5 sm:justify-start sm:px-3 rounded-lg text-sm font-medium transition ${
                isActive
                  ? "bg-[#EAF7EE] text-[#3BAA62]"
                  : "text-[#475467] hover:bg-[#F2F4F7]"
              }`}
              onClick={() => onNavigate(item.path)}
              type="button"
            >
              <item.icon size={18} aria-hidden="true" />
              <span className="hidden sm:inline">{item.label}</span>
            </button>
          );
        })}
      </nav>

      {activeTake && (
        <div className="hidden sm:block">
          <ActiveRecordingBlock
            activeTake={activeTake}
            onNavigate={onNavigate}
            isOrphan={isOrphan}
            forceCancel={forceCancel}
            forceCancelling={forceCancelling}
          />
        </div>
      )}
    </aside>
  );
}
