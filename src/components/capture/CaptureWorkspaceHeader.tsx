import { FolderOpen, Settings } from "lucide-react";
import type { CaptureHeaderViewModel } from "./captureTypes";

interface Props {
  vm: CaptureHeaderViewModel;
  onStoragePick?: () => void;
}

export function CaptureWorkspaceHeader({ vm, onStoragePick }: Props) {
  return (
    <div className="flex items-center justify-between" style={{ paddingBottom: 4 }}>
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-black" style={{ color: "var(--capture-text-primary)" }}>{vm.title || "现场采集"}</h1>
          {vm.isRecording && (
            <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-bold" style={{ background: "var(--capture-brand-soft)", color: "var(--capture-brand-primary)" }}>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ background: "var(--capture-status-recording)" }} />
                <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: "var(--capture-status-recording)" }} />
              </span>
              录制中
            </span>
          )}
        </div>
        <p className="text-sm" style={{ color: "var(--capture-text-secondary)" }}>{vm.statusLabel}</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs" style={{ color: "var(--capture-text-muted)" }}>{vm.storageSpace}</span>
        {onStoragePick && (
          <button className="p-2 rounded-lg hover:bg-gray-100 transition" onClick={onStoragePick} type="button" aria-label="选择存储位置">
            <FolderOpen size={16} />
          </button>
        )}
        <button className="p-2 rounded-lg hover:bg-gray-100 transition" type="button" aria-label="设置">
          <Settings size={16} />
        </button>
      </div>
    </div>
  );
}
