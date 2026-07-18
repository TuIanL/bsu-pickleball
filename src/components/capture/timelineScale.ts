export interface TimelineTick {
  label: string;
  positionPct: number;
}

const NICE_STEP_MS = [
  1_000, 2_000, 5_000,
  10_000, 15_000, 30_000,
  60_000, 120_000, 300_000,
  600_000, 900_000, 1_800_000,
  3_600_000, 7_200_000, 10_800_000,
  21_600_000, 43_200_000,
];

function formatDuration(ms: number): string {
  if (ms < 0) ms = 0;
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  if (m > 0) return `${m}:${String(s).padStart(2, "0")}`;
  return `0:${String(s).padStart(2, "0")}`;
}

export function computeTicks(
  windowStartMs: number,
  windowEndMs: number,
  containerWidthPx: number,
  minLabelSpacingPx = 72,
): TimelineTick[] {
  const duration = windowEndMs - windowStartMs;
  if (duration < 1000 || containerWidthPx <= 0 || windowEndMs <= windowStartMs) {
    return [];
  }
  const viewDuration = windowEndMs - windowStartMs;
  const targetCount = Math.max(2, Math.floor(containerWidthPx / minLabelSpacingPx));
  const stepMs = NICE_STEP_MS.find(s => viewDuration / s <= targetCount) ?? NICE_STEP_MS.at(-1)!;
  const firstTick = Math.ceil(windowStartMs / stepMs) * stepMs;
  const ticks: TimelineTick[] = [];
  for (let t = firstTick; t <= windowEndMs; t += stepMs) {
    const posPct = ((t - windowStartMs) / viewDuration) * 100;
    ticks.push({ label: formatDuration(t), positionPct: Math.max(0, Math.min(100, posPct)) });
  }
  if (ticks.length > 0) {
    const firstDistPx = (ticks[0].positionPct / 100) * containerWidthPx;
    if (firstDistPx < minLabelSpacingPx / 2 && windowStartMs > 0) {
      ticks[0] = { label: formatDuration(windowStartMs), positionPct: 0 };
    }
  }
  return ticks;
}

export function toTimelineMarkers(
  events: { event_type: string; id: string; timestamp_ms: number; note?: string; label?: string; payload_json?: { highlight?: boolean; intermission_kind?: string } }[],
): { id: string; timestampMs: number; track: "highlight" | "side_change" | "timeout"; label?: string; pending?: boolean; failed?: boolean }[] {
  return events
    .filter(e => e.event_type === "side_change"
      || (e.event_type === "add_note" && e.payload_json?.highlight === true)
      || (e.event_type === "session_note" && e.payload_json?.highlight === true)
      || (e.event_type === "non_play_start" && e.payload_json?.intermission_kind === "timeout"))
    .map(e => {
      let track: "highlight" | "side_change" | "timeout";
      if (e.event_type === "side_change") track = "side_change";
      else if (e.event_type === "non_play_start") track = "timeout";
      else track = "highlight";
      return { id: e.id, timestampMs: e.timestamp_ms, track, label: e.note ?? e.label };
    });
}
