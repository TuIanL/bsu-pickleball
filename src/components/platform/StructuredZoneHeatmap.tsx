import { useState } from "react";
import { courtSvgDefs } from "../../utils/courtGeometry";
import type { PlayerZoneStats, StructuredVisualizationData, ZoneStat } from "../../types/report";

const ZONE_ORDER = ["kitchen", "transition", "backcourt"] as const;

interface StructuredZoneHeatmapProps {
  data: StructuredVisualizationData | null;
}

export default function StructuredZoneHeatmap({ data }: StructuredZoneHeatmapProps) {
  const players = data?.zone_stats?.players ?? [];
  if (players.length === 0) {
    return <p className="mt-3 text-sm leading-6 text-slate-500">暂无区域统计</p>;
  }
  return <ZoneHeatmapBody players={players} />;
}

function ZoneHeatmapBody({ players }: { players: PlayerZoneStats[] }) {
  const [selectedId, setSelectedId] = useState(players[0]?.id);
  const selected = players.find((player) => player.id === selectedId) ?? players[0];
  const defs = courtSvgDefs();
  const courtH = defs.courtOutline.height;

  function yToSvg(yFt: number) {
    return defs.courtOutline.y + (yFt / 44) * courtH;
  }

  // 三段横带（y 英尺）：backcourt [0,7)+[37,44] / transition [7,15)+[29,37] / kitchen [15,29]
  const bandSpans: Record<string, Array<[number, number]>> = {
    kitchen: [[15, 29]],
    transition: [
      [7, 15],
      [29, 37],
    ],
    backcourt: [
      [0, 7],
      [37, 44],
    ],
  };

  function zoneLabel(zone: ZoneStat) {
    return zone.label;
  }

  return (
    <div>
      {/* 球员单选 chip */}
      <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 px-1">
        {players.map((player) => (
          <button
            key={`zone-player-${player.id}`}
            onClick={() => setSelectedId(player.id)}
            className="flex items-center gap-1.5 text-xs font-medium"
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: player.color, opacity: player.id === selected.id ? 1 : 0.3 }}
            />
            <span className={player.id === selected.id ? "text-[#14241B]" : "text-slate-400"}>{player.label}</span>
          </button>
        ))}
      </div>

      <svg viewBox={defs.viewBox} className="w-full bg-white" style={{ aspectRatio: "200/440" }}>
        {/* 三段区域着色（按占用率强度） */}
        {ZONE_ORDER.map((zoneKey) =>
          bandSpans[zoneKey].map(([y0, y1]) => {
            const zone = selected.zones.find((z) => z.zone === zoneKey);
            const occupancy = zone?.occupancy ?? 0;
            return (
              <rect
                key={`${zoneKey}-${y0}-${y1}`}
                x={defs.courtOutline.x}
                y={yToSvg(y0)}
                width={defs.courtOutline.width}
                height={yToSvg(y1) - yToSvg(y0)}
                fill={selected.color}
                opacity={0.1 + 0.6 * occupancy}
              />
            );
          })
        )}
        {/* 球场底框 */}
        <rect
          x={defs.courtOutline.x}
          y={defs.courtOutline.y}
          width={defs.courtOutline.width}
          height={courtH}
          fill="none"
          stroke="#14241B"
          strokeWidth={1}
          rx={2}
        />
        <line x1={defs.net.x1} y1={defs.net.y1} x2={defs.net.x2} y2={defs.net.y2} stroke="#14241B" strokeWidth={1.5} strokeDasharray="4,3" />
        <line x1={defs.kitchenTop.x1} y1={defs.kitchenTop.y1} x2={defs.kitchenTop.x2} y2={defs.kitchenTop.y2} stroke="#22C55E" strokeWidth={1} strokeDasharray="3,2" />
        <line x1={defs.kitchenBottom.x1} y1={defs.kitchenBottom.y1} x2={defs.kitchenBottom.x2} y2={defs.kitchenBottom.y2} stroke="#22C55E" strokeWidth={1} strokeDasharray="3,2" />
        {/* 区域标签 */}
        {(["kitchen", "transition", "backcourt"] as const).map((zoneKey) => {
          const zone = selected.zones.find((z) => z.zone === zoneKey);
          const midY = bandSpans[zoneKey].reduce((acc, [y0, y1]) => acc + (y0 + y1) / 2, 0) / bandSpans[zoneKey].length;
          return (
            <text
              key={`zone-label-${zoneKey}`}
              x={defs.courtOutline.x + defs.courtOutline.width / 2}
              y={yToSvg(midY) + 3}
              textAnchor="middle"
              fontSize="9"
              fill="#14241B"
              opacity={0.75}
            >
              {zoneLabel(zone!)}
            </text>
          );
        })}
      </svg>

      {/* 区域占用条 + KCR + 反馈 */}
      <div className="mt-3 px-1">
        <div className="mb-3 flex items-end gap-6">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Kitchen Control</p>
            <p className="text-2xl font-black text-[#14241B]">{(selected.kitchen_control_rate * 100).toFixed(0)}%</p>
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">平均站位距厨房线</p>
            <p className="text-2xl font-black text-[#14241B]">{selected.avg_distance_to_kitchen_line_m.toFixed(1)}m</p>
          </div>
        </div>

        <div className="grid gap-2">
          {selected.zones.map((zone) => (
            <div key={zone.zone} className="flex items-center gap-2">
              <span className="w-16 text-xs font-medium text-[#14241B]">{zone.label}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.min(100, Math.round(zone.occupancy * 100))}%`, backgroundColor: selected.color }}
                />
              </div>
              <span className="w-12 text-right text-xs tabular-nums text-slate-600">{(zone.occupancy * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>

        {selected.data_sufficiency === "insufficient" && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">有效帧不足，以下占用百分比为参考，勿作确定结论。</p>
        )}
        {selected.feedback?.summary && (
          <p className="mt-3 rounded-lg bg-[#F5FAF1] px-3 py-2 text-xs leading-5 text-[#14241B]">{selected.feedback.summary}</p>
        )}
      </div>
    </div>
  );
}
