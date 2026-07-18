import type { ReactNode } from "react";
import { Play, Square, Pause, Flag } from "lucide-react";
import type { RecordingControlViewModel } from "./captureTypes";

interface Props {
  vm: RecordingControlViewModel;
  canStart?: boolean;
  onStart?: () => void;
  onStop?: () => void;
  onPause?: () => void;
  onMark?: () => void;
  onCancel?: () => void;
  error?: string;
  extraButtons?: ReactNode;
  belowControls?: ReactNode;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function RecordingControlPanel({ vm, canStart, onStart, onStop, onPause, onMark, onCancel, error, extraButtons, belowControls }: Props) {
  const isRecording = vm.phase === "recording";
  const isIdle = vm.phase === "idle";
  const isStopping = vm.phase === "stopping" || vm.phase === "recovering";
  const isFailed = vm.phase === "failed";

  return (
    <div>
      <div className="flex items-center justify-between rounded-xl px-5 py-3" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)", boxShadow: "var(--capture-shadow-card)" }}>
        <div className="flex items-center gap-6 min-w-0">
          <div>
            <p className="text-2xl font-bold tabular-nums" style={{ color: "var(--capture-text-primary)" }}>{formatElapsed(vm.elapsedMs)}</p>
            <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>录制时长</p>
          </div>
          {isRecording && (
            <div>
              <p className="text-sm font-semibold" style={{ color: "var(--capture-text-primary)" }}>
                {vm.fileSize.state === "ready" ? vm.fileSize.label : "-"}
              </p>
              <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>文件大小</p>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {isIdle && onStart && (
            <button
              className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-white font-bold transition disabled:opacity-50"
              style={{ background: "var(--capture-brand-primary)" }}
              onClick={onStart}
              disabled={!canStart}
              type="button"
            >
              <Play size={16} fill="currentColor" />开始录制
            </button>
          )}
          {isRecording && (
            <>
              {onPause && (
                <button className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition" type="button" style={{ borderColor: "var(--capture-border-default)", color: "var(--capture-text-secondary)" }} onClick={onPause}>
                  <Pause size={16} />暂停
                </button>
              )}
              {onStop && (
                <button
                  className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-white font-bold transition"
                  style={{ background: "var(--capture-status-recording)" }}
                  onClick={onStop}
                  type="button"
                >
                  <Square size={16} fill="currentColor" />停止
                </button>
              )}
              {onMark && (
                <button className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition" type="button" style={{ borderColor: "var(--capture-border-default)", color: "var(--capture-text-secondary)" }} onClick={onMark}>
                  <Flag size={16} />标记
                </button>
              )}
            </>
          )}
          {isStopping && onCancel && (
            <button className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm" type="button" style={{ borderColor: "var(--capture-border-default)", color: "var(--capture-text-secondary)" }} onClick={onCancel}>取消录制</button>
          )}
          {extraButtons}
        </div>

        <div className="flex items-center gap-5 shrink-0">
          {isRecording && (
            <>
              <div className="text-right">
                <p className="text-sm font-semibold tabular-nums" style={{ color: "var(--capture-text-primary)" }}>
                  {vm.fps.state === "ready" ? `${vm.fps.value} fps` : "-"}
                </p>
                <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>帧率</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold tabular-nums" style={{ color: "var(--capture-text-primary)" }}>
                  {vm.bitrate.state === "ready" ? `${vm.bitrate.value} Mbps` : "-"}
                </p>
                <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>码率</p>
              </div>
            </>
          )}
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              {isRecording && <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ background: "var(--capture-status-recording)" }} />}
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full" style={{ background: isRecording ? "var(--capture-status-recording)" : isIdle ? "var(--capture-text-muted)" : isFailed ? "var(--capture-status-recording)" : "var(--capture-status-warning)" }} />
            </span>
            <span className="text-xs font-medium" style={{ color: "var(--capture-text-secondary)" }}>
              {isRecording ? "录制中" : isIdle ? "就绪" : isFailed ? "失败" : vm.phase}
            </span>
          </div>
        </div>
      </div>
      {isFailed && error && (
        <div className="mt-2 rounded-lg px-4 py-2 text-sm" style={{ background: "var(--capture-brand-soft)", border: "1px solid var(--capture-status-recording)", color: "var(--capture-status-recording)" }}>
          {error}
        </div>
      )}
      {belowControls}
    </div>
  );
}
