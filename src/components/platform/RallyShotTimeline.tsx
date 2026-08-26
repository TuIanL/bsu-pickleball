import { useMemo, useState } from "react";
import type { ShotRallyEventsArtifact } from "../../types/shotRallyEvents";
import {
  buildRallyShotTimelineModel,
  RALLY_SHOT_QUALITY_LABELS,
  RALLY_SHOT_STAGE_LABELS,
  type RallyShotTimelineEvent,
  type RallyShotTimelineRow,
  type RallyShotStageKey,
} from "../../services/rallyShotTimeline";

type TimelineLoadState = "idle" | "loading" | "available" | "unavailable" | "failed";

interface RallyShotTimelineProps {
  artifact: ShotRallyEventsArtifact | null;
  loadState: TimelineLoadState;
  status?: string;
  detail?: string;
  onSeekToMs?: (timestampMs: number) => void;
}

const STAGE_COLORS: Record<RallyShotStageKey, string> = {
  serve: "#2F80ED",
  return: "#14B8A6",
  third: "#8B5CF6",
  rally_shot: "#F97316",
  unknown: "#94A3B8",
};

const QUALITY_OPACITY = {
  high: 1,
  medium: 0.82,
  low: 0.58,
  none: 0.42,
};

function formatMs(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "时间未知";
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function formatAverage(value: number | null): string {
  return value == null ? "—" : value.toFixed(1);
}

function eventPosition(event: RallyShotTimelineEvent, index: number, row: RallyShotTimelineRow): number {
  const timedEvents = row.events.map((candidate) => candidate.timestampMs).filter((value): value is number => value != null);
  if (event.timestampMs == null || timedEvents.length < 2) {
    return row.events.length < 2 ? 50 : (index / Math.max(row.events.length - 1, 1)) * 100;
  }
  const min = Math.min(...timedEvents);
  const max = Math.max(...timedEvents);
  if (max <= min) return 50;
  return ((event.timestampMs - min) / (max - min)) * 100;
}

function EventMarker({
  event,
  position,
  onSelect,
}: {
  event: RallyShotTimelineEvent;
  position: number;
  onSelect: (event: RallyShotTimelineEvent) => void;
}) {
  const color = STAGE_COLORS[event.stage];
  const playerRing = event.ownershipStatus === "confirmed" ? event.playerColor : "#94A3B8";
  const label = `${event.shotId} · ${event.stageLabel} · ${event.ownershipLabel}`;
  return (
    <button
      aria-label={label}
      className="group absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full p-1 text-left transition hover:z-10 focus:z-10 focus:outline-none focus:ring-2 focus:ring-[#168A34]/40"
      onClick={() => onSelect(event)}
      style={{ left: `${Math.max(2, Math.min(98, position))}%` }}
      type="button"
    >
      <span
        className="block h-5 w-5 rounded-full border-[3px] bg-white shadow-sm transition group-hover:scale-125"
        style={{ borderColor: playerRing, opacity: QUALITY_OPACITY[event.qualityBand] }}
      >
        <span className="block h-full w-full rounded-full" style={{ backgroundColor: color }} />
      </span>
      <span className="pointer-events-none absolute left-1/2 top-8 hidden -translate-x-1/2 whitespace-nowrap rounded-lg bg-[#14241B] px-2 py-1 text-[10px] font-bold text-white shadow-lg group-hover:block group-focus:block">
        {event.stageLabel} · {event.playerLabel}
      </span>
    </button>
  );
}

function TimelineRow({
  row,
  selectedShotId,
  onSelect,
}: {
  row: RallyShotTimelineRow;
  selectedShotId: string | null;
  onSelect: (event: RallyShotTimelineEvent) => void;
}) {
  const timedEvents = row.events.map((event) => event.timestampMs).filter((value): value is number => value != null);
  const firstTime = timedEvents.length ? Math.min(...timedEvents) : row.startMs;
  const lastTime = timedEvents.length ? Math.max(...timedEvents) : row.endMs;
  return (
    <div className="rounded-2xl border border-[#E6EFE0] bg-white/75 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <strong className="block truncate text-sm text-[#14241B]">{row.label}</strong>
          <span className="text-xs text-slate-500">
            {row.events.length} 个击球 · {firstTime != null ? formatMs(firstTime) : "时间未知"}–{lastTime != null ? formatMs(lastTime) : "时间未知"}
          </span>
        </div>
        {row.isUnassigned && <span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">边界外事件</span>}
      </div>
      <div className="relative mt-4 h-16 overflow-x-auto rounded-xl bg-[#F5FAF1] px-3">
        <div className="relative h-full min-w-[420px]">
          <div className="absolute left-0 right-0 top-1/2 h-px bg-[#CFE0C7]" />
          {row.events.map((event, index) => (
            <EventMarker
              event={event}
              key={event.shotId}
              onSelect={onSelect}
              position={eventPosition(event, index, row)}
            />
          ))}
        </div>
      </div>
      {selectedShotId && row.events.some((event) => event.shotId === selectedShotId) && (
        <p className="mt-2 text-xs text-slate-500">已选中 {selectedShotId}，下方查看事件详情。</p>
      )}
    </div>
  );
}

function EventDetails({ event, onSeekToMs }: { event: RallyShotTimelineEvent; onSeekToMs?: (timestampMs: number) => void }) {
  return (
    <div className="rounded-2xl border border-[#CFE0C7] bg-[#F5FAF1] p-4" data-testid="rally-shot-details">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#168A34]">事件详情</p>
          <h3 className="mt-1 text-base font-black text-[#14241B]">{event.shotId} · {event.stageLabel}</h3>
        </div>
        <span className="rounded-full px-2.5 py-1 text-xs font-bold" style={{ backgroundColor: `${STAGE_COLORS[event.stage]}18`, color: STAGE_COLORS[event.stage] }}>
          {event.qualityLabel}
        </span>
      </div>
      <dl className="mt-3 grid gap-x-4 gap-y-2 text-xs text-slate-600 sm:grid-cols-2">
        <div><dt className="inline text-slate-400">击球者：</dt> <dd className="inline font-bold text-[#14241B]">{event.ownershipLabel}</dd></div>
        <div><dt className="inline text-slate-400">时间：</dt> <dd className="inline font-bold text-[#14241B]">{formatMs(event.timestampMs)}</dd></div>
        <div><dt className="inline text-slate-400">证据窗口：</dt> <dd className="inline font-bold text-[#14241B]">{event.canSeek ? `${formatMs(event.evidenceStartMs)}–${formatMs(event.evidenceEndMs)}` : "暂无可跳转证据"}</dd></div>
        <div><dt className="inline text-slate-400">轨迹长度：</dt> <dd className="inline font-bold text-[#14241B]">{event.pathDistanceFt == null ? "—" : `${event.pathDistanceFt.toFixed(1)} ft`}</dd></div>
      </dl>
      {event.canSeek && event.evidenceStartMs != null ? (
        <button className="green-button mt-4 px-3 py-2 text-xs" onClick={() => onSeekToMs?.(event.evidenceStartMs!)} type="button">
          定位到视频证据
        </button>
      ) : (
        <p className="mt-3 text-xs text-slate-500">暂无可跳转证据，仅展示该事件的统计信息。</p>
      )}
    </div>
  );
}

export function RallyShotTimeline({ artifact, loadState, status, detail, onSeekToMs }: RallyShotTimelineProps) {
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const model = useMemo(() => (artifact ? buildRallyShotTimelineModel(artifact) : null), [artifact]);
  const selectedEvent = model?.events.find((event) => event.shotId === selectedShotId) ?? null;
  const isUnavailable = loadState === "unavailable" || loadState === "failed" || artifact?.status !== "available";

  return (
    <article className="rounded-2xl border border-[#DDE9D6] bg-white/75 p-4 md:col-span-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">回合事件分析</p>
          <h3 className="mt-2 text-xl font-black text-[#14241B]">回合—击球阶段时序图</h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">沿视频时间轴查看每个回合的击球阶段、球员归属和可回放证据。</p>
        </div>
        <span className="rounded-full bg-[#E9F5E4] px-2.5 py-1 text-xs font-black text-[#168A34]">SHOT / RALLY</span>
      </div>

      {loadState === "loading" ? (
        <div className="mt-5 rounded-2xl border border-dashed border-[#CFE0C7] bg-[#F8FCF6] p-5 text-sm text-slate-500" role="status">正在读取回合事件…</div>
      ) : isUnavailable ? (
        <div className="mt-5 rounded-2xl border border-dashed border-[#DDE9D6] bg-[#F8FCF6] p-5">
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-600">{loadState === "failed" || status === "failed" ? "读取失败" : "不可用"}</span>
          <p className="mt-3 text-sm leading-6 text-slate-500">{detail || artifact?.detail || "当前任务没有可用的回合—击球事件数据。"}</p>
        </div>
      ) : model?.mode === "empty" ? (
        <div className="mt-5 rounded-2xl border border-dashed border-[#DDE9D6] bg-[#F8FCF6] p-5 text-sm text-slate-500">暂无可展示击球事件。</div>
      ) : model ? (
        <>
          <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["击球事件", model.summary.shotCount],
              ["可用回合", model.summary.rallyCount || "—"],
              ["平均每回合", formatAverage(model.summary.averageShotsPerRally)],
              ["归属不明", model.summary.unassignedCount],
            ].map(([label, value]) => (
              <div className="rounded-xl bg-[#F5FAF1] px-3 py-2" key={label}>
                <span className="block text-[11px] font-bold text-slate-400">{label}</span>
                <strong className="mt-1 block text-lg font-black tabular-nums text-[#14241B]">{value}</strong>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-600">
            {(Object.keys(RALLY_SHOT_STAGE_LABELS) as RallyShotStageKey[]).map((stage) => (
              <span className="inline-flex items-center gap-1.5" key={stage}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: STAGE_COLORS[stage] }} />
                {RALLY_SHOT_STAGE_LABELS[stage]}
              </span>
            ))}
            <span className="text-slate-400">圆环透明度表示{RALLY_SHOT_QUALITY_LABELS.high} / {RALLY_SHOT_QUALITY_LABELS.low}</span>
          </div>

          {model.mode === "chronological" && (
            <p className="mt-4 rounded-xl bg-[#FFF7E8] px-3 py-2 text-xs leading-5 text-[#8A5A00]">
              未提供可靠回合边界，当前按击球事件时间排序；未推断回合编号或阶段顺序。
            </p>
          )}

          {model.summary.shotCount > 0 && model.summary.shotCount < 3 && (
            <p className="mt-3 rounded-xl bg-[#F8F4FF] px-3 py-2 text-xs leading-5 text-[#6B4AA1]">
              当前击球事件样本较少，时序图仅作为证据索引，不代表完整回合统计。
            </p>
          )}

          <div className="mt-4 grid gap-3">
            {model.rows.map((row) => (
              <TimelineRow key={row.id} onSelect={(event) => setSelectedShotId(event.shotId)} row={row} selectedShotId={selectedShotId} />
            ))}
          </div>

          {selectedEvent && <div className="mt-4"><EventDetails event={selectedEvent} onSeekToMs={onSeekToMs} /></div>}
        </>
      ) : null}
    </article>
  );
}

export default RallyShotTimeline;
