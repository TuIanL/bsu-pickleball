import type { CameraPreviewViewModel } from "./captureTypes";

interface Props {
  vm: CameraPreviewViewModel;
  previewKey?: number;
  fillContainer?: boolean;
}

export function CameraPreviewCard({ vm, previewKey, fillContainer = false }: Props) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border${fillContainer ? " h-full" : ""}`}
      style={{ aspectRatio: fillContainer ? undefined : "16/9", background: "var(--capture-surface-video)", borderColor: "var(--capture-border-default)" }}
    >
      <span className="absolute top-2 left-2 z-10 rounded px-2 py-0.5 text-xs text-white" style={{ background: "rgba(0,0,0,0.6)" }}>
        {vm.label}
      </span>
      {vm.resolution && (
        <span className="absolute top-2 right-2 z-10 rounded px-2 py-0.5 text-xs text-white" style={{ background: "rgba(0,0,0,0.6)" }}>
          {vm.resolution}{vm.fps ? ` · ${vm.fps}fps` : ""}
        </span>
      )}
      {vm.status === "ready" ? (
        <img
          key={previewKey}
          src={vm.previewUrl}
          className="w-full h-full object-contain"
          alt={vm.slot}
          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
        />
      ) : vm.status === "connecting" ? (
        <div className="flex items-center justify-center h-full text-xs" style={{ color: "var(--capture-text-muted)" }}>
          摄像头连接中...
        </div>
      ) : vm.status === "failed" ? (
        <div className="flex flex-col items-center justify-center h-full gap-2 text-xs" style={{ color: "var(--capture-text-muted)" }}>
          <span>视频流中断</span>
          <button className="px-3 py-1 rounded border text-xs" type="button" style={{ borderColor: "var(--capture-border-default)" }}>重试预览</button>
        </div>
      ) : (
        <div className="flex items-center justify-center h-full text-xs" style={{ color: "var(--capture-text-muted)" }}>
          选择摄像头后显示预览
        </div>
      )}
    </div>
  );
}

export function CameraPreviewGrid({ cameras, previewKey }: { cameras: CameraPreviewViewModel[]; previewKey?: number }) {
  if (cameras.length === 0) {
    return <CameraPreviewCard vm={{ slot: "empty", cameraId: "", label: "预览", previewUrl: "", status: "idle" }} />;
  }
  return (
    <div className={`grid ${cameras.length === 1 ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2"} gap-3`}>
      {cameras.map(track => (
        <CameraPreviewCard key={track.slot} vm={track} previewKey={previewKey} />
      ))}
    </div>
  );
}
