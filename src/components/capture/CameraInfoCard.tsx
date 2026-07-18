import { Camera } from "lucide-react";

interface Props {
  cameraId: string;
  label?: string;
  resolution?: string;
  fps?: number;
}

export function CameraInfoCard({ cameraId, label, resolution, fps }: Props) {
  return (
    <div className="rounded-lg p-3 text-xs" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)" }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Camera size={14} style={{ color: "var(--capture-text-muted)" }} />
          <span className="font-medium" style={{ color: "var(--capture-text-primary)" }}>{label || cameraId}</span>
        </div>
      </div>
      {(resolution || fps) && (
        <p className="mt-1" style={{ color: "var(--capture-text-muted)" }}>
          {resolution}{resolution && fps ? " · " : ""}{fps ? `${fps}fps` : ""}
        </p>
      )}
    </div>
  );
}
