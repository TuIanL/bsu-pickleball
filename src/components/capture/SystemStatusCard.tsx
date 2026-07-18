/**
 * SystemStatusCard —— 系统状态卡，展示后端可验证的存储/轨道/同步状态。
 *
 * 设计依据：openspec/changes/redesign-live-recording-workspace-runtime-status
 * - 只展示后端能够确认的存储、录制轨道、双路同步和事件同步状态
 * - 不展示音频编码、网络质量等没有后端证据的虚假状态
 * - 每个指标独立表达 loading/collecting/unavailable/error，单项失败不掩盖整体
 */
import { CheckCircle2, AlertCircle, Loader2, MinusCircle } from "lucide-react";
import type {
  CaptureTakeRuntimeStatus,
  RuntimeMetricAvailability,
  RuntimeMetricValue,
  StorageCapacity,
  SyncRuntimeStatus,
  TrackRuntimeStatus,
} from "../../types/captureRuntimeStatus";

interface Props {
  snapshot: CaptureTakeRuntimeStatus | null;
  isLoading: boolean;
  error: string | null;
  lastSuccessAt: string | null;
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function MetricIcon({ state }: { state: RuntimeMetricAvailability }) {
  if (state === "ready") return <CheckCircle2 size={14} style={{ color: "var(--capture-brand-primary)" }} />;
  if (state === "collecting") return <Loader2 size={14} className="animate-spin" style={{ color: "var(--capture-status-warning)" }} />;
  if (state === "error") return <AlertCircle size={14} style={{ color: "var(--capture-status-recording)" }} />;
  return <MinusCircle size={14} style={{ color: "var(--capture-text-muted)" }} />;
}

function metricLabel(state: RuntimeMetricAvailability): string {
  switch (state) {
    case "ready": return "正常";
    case "collecting": return "采集中";
    case "unavailable": return "不可用";
    case "error": return "异常";
  }
}

function StorageRow({ storage }: { storage: StorageCapacity }) {
  const detail =
    storage.state === "ready"
      ? `${formatBytes(storage.usedBytes)} / ${formatBytes(storage.totalBytes)}（剩余 ${formatBytes(storage.freeBytes)}）`
      : storage.message ?? metricLabel(storage.state);
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="flex items-center gap-1.5" style={{ color: "var(--capture-text-secondary)" }}>
        <MetricIcon state={storage.state} /> 存储容量
      </span>
      <span className="truncate text-right" style={{ color: "var(--capture-text-primary)" }} title={detail}>
        {detail}
      </span>
    </div>
  );
}

function TrackRow({ track }: { track: TrackRuntimeStatus }) {
  const state: RuntimeMetricAvailability = track.error
    ? "error"
    : track.phase === "recording" || track.phase === "starting"
      ? track.fileSizeBytes.state
      : track.fileSizeBytes.state === "ready"
        ? "ready"
        : "unavailable";
  const detail = track.error
    ? track.error
    : track.fileSizeBytes.state === "ready"
      ? `${track.slot} · ${formatBytes(track.fileSizeBytes.value)}`
      : `${track.slot} · ${metricLabel(track.fileSizeBytes.state)}`;
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="flex items-center gap-1.5" style={{ color: "var(--capture-text-secondary)" }}>
        <MetricIcon state={state} /> 轨道 {track.slot}
      </span>
      <span className="truncate text-right" style={{ color: "var(--capture-text-primary)" }} title={detail}>
        {detail}
      </span>
    </div>
  );
}

function SyncRow({ sync }: { sync: SyncRuntimeStatus | null }) {
  if (!sync) {
    return (
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="flex items-center gap-1.5" style={{ color: "var(--capture-text-secondary)" }}>
          <MinusCircle size={14} style={{ color: "var(--capture-text-muted)" }} /> 双路同步
        </span>
        <span style={{ color: "var(--capture-text-muted)" }}>单摄模式</span>
      </div>
    );
  }
  const detail =
    sync.dualSync === "ready"
      ? `已同步${sync.dualSyncQuality ? ` · ${sync.dualSyncQuality}` : ""}`
      : sync.message ?? metricLabel(sync.dualSync);
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="flex items-center gap-1.5" style={{ color: "var(--capture-text-secondary)" }}>
        <MetricIcon state={sync.dualSync} /> 双路同步
      </span>
      <span className="truncate text-right" style={{ color: "var(--capture-text-primary)" }} title={detail}>
        {detail}
      </span>
    </div>
  );
}

function EventSyncRow({ sync }: { sync: SyncRuntimeStatus | null }) {
  const state: RuntimeMetricAvailability = sync?.eventSync ?? "ready";
  const detail = state === "ready" ? "已同步" : metricLabel(state);
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="flex items-center gap-1.5" style={{ color: "var(--capture-text-secondary)" }}>
        <MetricIcon state={state} /> 事件同步
      </span>
      <span style={{ color: "var(--capture-text-primary)" }}>{detail}</span>
    </div>
  );
}

export function SystemStatusCard({ snapshot, isLoading, error, lastSuccessAt }: Props) {
  return (
    <div
      className="rounded-xl p-4 space-y-3"
      style={{
        background: "var(--capture-surface-card)",
        border: "1px solid var(--capture-border-default)",
        boxShadow: "var(--capture-shadow-card)",
      }}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold" style={{ color: "var(--capture-text-primary)" }}>
          系统状态
        </h3>
        {error ? (
          <span className="text-[10px]" style={{ color: "var(--capture-status-recording)" }} title={error}>
            状态更新失败
          </span>
        ) : isLoading ? (
          <span className="text-[10px]" style={{ color: "var(--capture-text-muted)" }}>
            加载中…
          </span>
        ) : lastSuccessAt ? (
          <span className="text-[10px]" style={{ color: "var(--capture-text-muted)" }}>
            更新于 {new Date(lastSuccessAt).toLocaleTimeString()}
          </span>
        ) : null}
      </div>

      {!snapshot && !isLoading && (
        <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>
          {error ?? "暂无运行状态"}
        </p>
      )}

      {isLoading && !snapshot && (
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--capture-text-muted)" }}>
          <Loader2 size={14} className="animate-spin" /> 正在获取运行状态…
        </div>
      )}

      {snapshot && (
        <div className="space-y-2">
          <StorageRow storage={snapshot.storage} />
          {snapshot.tracks.map((t) => (
            <TrackRow key={t.trackId} track={t} />
          ))}
          <SyncRow sync={snapshot.sync ?? null} />
          <EventSyncRow sync={snapshot.sync ?? null} />
        </div>
      )}

      {error && snapshot && (
        <p className="text-[10px]" style={{ color: "var(--capture-status-recording)" }}>
          {error}
        </p>
      )}
    </div>
  );
}

/** 工具：把 RuntimeMetricValue 映射为前端展示用的 MetricValue（captureTypes） */
export function adaptRuntimeMetric<T>(
  rv: RuntimeMetricValue<T> | null | undefined,
  toLabel: (value: T) => string,
): { state: "ready"; value: T; label: string } | { state: "loading" } | { state: "unsupported" } | { state: "error"; message?: string } {
  if (!rv || typeof rv !== "object" || typeof rv.state !== "string") {
    return { state: "loading" };
  }
  switch (rv.state) {
    case "ready":
      return { state: "ready", value: rv.value as T, label: toLabel(rv.value as T) };
    case "collecting":
      return { state: "loading" };
    case "unavailable":
      return { state: "unsupported" };
    case "error":
      return { state: "error", message: rv.message ?? undefined };
  }
}
