import type { ShotLanding } from "../../../types/shotLandings";
import { zone12Stats } from "../../../services/landingVisualization";

const ROWS = ["VD", "D", "T", "K"];
const COLS = ["L", "C", "R"];

export function LandingZoneGrid({ landings }: { landings: ShotLanding[] }) {
  const stats = zone12Stats(landings);
  const max = Math.max(1, ...Object.values(stats.counts));
  return <div className="grid grid-cols-3 gap-1">{ROWS.flatMap((row) => COLS.map((col) => {
    const zone = `${row}-${col}`;
    const count = stats.counts[zone] ?? 0;
    return <div key={zone} className="rounded-lg border border-emerald-900/10 p-3 text-center" style={{ backgroundColor: `rgba(35,152,91,${.08 + .72 * count / max})` }}>
      <div className="text-xs font-black">{zone}</div><div className="mt-1 text-lg font-black">{count}</div>
      <div className="text-[11px]">{stats.denominator ? `${(stats.ratio(zone) * 100).toFixed(1)}%` : "—"}</div>
    </div>;
  }))}</div>;
}
