import { useState } from "react";
import { courtSvgDefs } from "../../utils/courtGeometry";
import type { PlayerZoneStats, StructuredVisualizationData, ZoneStat } from "../../types/report";

const ZONE_ORDER = ["kitchen", "transition", "backcourt"] as const;

export type PbHeatmapColorScheme = "platform" | "pb-vision";

interface StructuredZoneHeatmapProps {
  data: StructuredVisualizationData | null;
  /**
   * 配色方案：
   * - "platform"（默认）：深墨绿 + 绿/金渐变，用于原报告页等平台深绿风格页面
   * - "pb-vision"：PB Vision 亮色风格，荧光亮绿 → 深紫渐变，用于 PB Vision 新报告页
   */
  colorScheme?: PbHeatmapColorScheme;
}

export default function StructuredZoneHeatmap({ data, colorScheme = "platform" }: StructuredZoneHeatmapProps) {
  const players = data?.zone_stats?.players ?? [];
  if (players.length === 0) {
    return <p className="mt-3 text-sm leading-6 text-slate-500">暂无区域统计</p>;
  }
  return <ZoneHeatmapBody players={players} colorScheme={colorScheme} />;
}

function ZoneHeatmapBody({
  players,
  colorScheme,
}: {
  players: PlayerZoneStats[];
  colorScheme: PbHeatmapColorScheme;
}) {
  const [selectedId, setSelectedId] = useState(players[0]?.id);
  const selected = players.find((player) => player.id === selectedId) ?? players[0];
  const defs = courtSvgDefs();
  const courtH = defs.courtOutline.height;

  // 配色根据 colorScheme 切换
  const palette =
    colorScheme === "pb-vision"
      ? {
          courtBg: "transparent",
          courtStroke: "#334155", // slate-700
          netStroke: "#00FF41", // PB 荧光亮绿
          kitchenStroke: "#A855F7", // PB 紫色（kitchen 色）
          labelColor: "#0F172A", // slate-900
          // heatmap 渐变（亮绿 → 深紫）
          heatStops: ["#00FF41", "#34D399", "#22D3EE", "#6366F1", "#A855F7", "#7E22CE"],
          textHeaderColor: "#0F172A",
          textSupportColor: "#475569",
          progressBg: "#E2E8F0",
        }
      : {
          courtBg: "#FFFFFF",
          courtStroke: "#14241B",
          netStroke: "#14241B",
          kitchenStroke: "#22C55E",
          labelColor: "#14241B",
          heatStops: [], // 空表示使用 player.color 单色
          textHeaderColor: "#14241B",
          textSupportColor: "#64748B",
          progressBg: "#F1F5F9",
        };

  /** 把 [0,1] 的强度映射到 PB 渐变色组 */
  function pbHeatColor(intensity: number): string {
    if (colorScheme !== "pb-vision" || palette.heatStops.length === 0) {
      return selected.color;
    }
    const stops = palette.heatStops;
    const clamped = Math.max(0, Math.min(1, intensity));
    const scaled = clamped * (stops.length - 1);
    const lo = Math.floor(scaled);
    const hi = Math.min(lo + 1, stops.length - 1);
    const t = scaled - lo;
    const c0 = stops[lo];
    const c1 = stops[hi];
    // hex #RRGGBB 简单线性插值
    const hexToRgb = (hex: string): [number, number, number] => {
      const h = hex.replace("#", "");
      return [
        parseInt(h.substring(0, 2), 16),
        parseInt(h.substring(2, 4), 16),
        parseInt(h.substring(4, 6), 16),
      ];
    };
    const rgbToHex = (r: number, g: number, b: number) =>
      "#" +
      [r, g, b]
        .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0"))
        .join("");
    const [r0, g0, b0] = hexToRgb(c0);
    const [r1, g1, b1] = hexToRgb(c1);
    return rgbToHex(r0 + (r1 - r0) * t, g0 + (g1 - g0) * t, b0 + (b1 - b0) * t);
  }

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
              style={{
                backgroundColor:
                  colorScheme === "pb-vision" ? pbHeatColor(0.8) : player.color,
                opacity: player.id === selected.id ? 1 : 0.3,
              }}
            />
            <span
              className={
                player.id === selected.id
                  ? "text-[var(--pb-text-primary)] font-semibold"
                  : "text-slate-400"
              }
              style={{ color: player.id === selected.id ? palette.textHeaderColor : undefined }}
            >
              {player.label}
            </span>
          </button>
        ))}
      </div>

      <svg
        viewBox={defs.viewBox}
        className="w-full"
        style={{ aspectRatio: "200/440", background: palette.courtBg }}
      >
        {/* 三段区域着色（按占用率强度） */}
        {ZONE_ORDER.map((zoneKey) =>
          bandSpans[zoneKey].map(([y0, y1]) => {
            const zone = selected.zones.find((z) => z.zone === zoneKey);
            const occupancy = zone?.occupancy ?? 0;
            const fillColor = pbHeatColor(occupancy);
            return (
              <rect
                key={`${zoneKey}-${y0}-${y1}`}
                x={defs.courtOutline.x}
                y={yToSvg(y0)}
                width={defs.courtOutline.width}
                height={yToSvg(y1) - yToSvg(y0)}
                fill={fillColor}
                opacity={colorScheme === "pb-vision" ? 0.45 + 0.35 * occupancy : 0.1 + 0.6 * occupancy}
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
          stroke={palette.courtStroke}
          strokeWidth={1}
          rx={2}
        />
        <line
          x1={defs.net.x1}
          y1={defs.net.y1}
          x2={defs.net.x2}
          y2={defs.net.y2}
          stroke={palette.netStroke}
          strokeWidth={1.5}
          strokeDasharray="4,3"
        />
        <line
          x1={defs.kitchenTop.x1}
          y1={defs.kitchenTop.y1}
          x2={defs.kitchenTop.x2}
          y2={defs.kitchenTop.y2}
          stroke={palette.kitchenStroke}
          strokeWidth={1}
          strokeDasharray="3,2"
        />
        <line
          x1={defs.kitchenBottom.x1}
          y1={defs.kitchenBottom.y1}
          x2={defs.kitchenBottom.x2}
          y2={defs.kitchenBottom.y2}
          stroke={palette.kitchenStroke}
          strokeWidth={1}
          strokeDasharray="3,2"
        />
        {/* 区域标签 */}
        {(["kitchen", "transition", "backcourt"] as const).map((zoneKey) => {
          const zone = selected.zones.find((z) => z.zone === zoneKey);
          const midY =
            bandSpans[zoneKey].reduce((acc, [y0, y1]) => acc + (y0 + y1) / 2, 0) /
            bandSpans[zoneKey].length;
          return (
            <text
              key={`zone-label-${zoneKey}`}
              x={defs.courtOutline.x + defs.courtOutline.width / 2}
              y={yToSvg(midY) + 3}
              textAnchor="middle"
              fontSize="9"
              fill={palette.labelColor}
              opacity={0.8}
              fontWeight={600}
            >
              {zoneLabel(zone!)}
            </text>
          );
        })}
      </svg>

      {/* 区域占用条 + NVZ 占用率（canonical，描述性）+ 反馈 */}
      <div className="mt-3 px-1">
        <div className="mb-3 flex items-end gap-6">
          <div>
            <p
              className="text-[10px] font-bold uppercase tracking-wider"
              style={{ color: palette.textSupportColor }}
            >
              非截击区占用率
            </p>
            <p className="text-2xl font-black" style={{ color: palette.textHeaderColor }}>
              {((selected.nvz_occupancy_rate ?? selected.kitchen_control_rate) * 100).toFixed(0)}%
            </p>
          </div>
          <div>
            <p
              className="text-[10px] font-bold uppercase tracking-wider"
              style={{ color: palette.textSupportColor }}
            >
              平均站位距厨房线
            </p>
            <p className="text-2xl font-black" style={{ color: palette.textHeaderColor }}>
              {selected.avg_distance_to_kitchen_line_m.toFixed(1)}m
            </p>
          </div>
        </div>

        <div className="grid gap-2">
          {selected.zones.map((zone) => (
            <div key={zone.zone} className="flex items-center gap-2">
              <span
                className="w-16 text-xs font-medium"
                style={{ color: palette.textHeaderColor }}
              >
                {zone.label}
              </span>
              <div
                className="h-2 flex-1 overflow-hidden rounded-full"
                style={{ backgroundColor: palette.progressBg }}
              >
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, Math.round(zone.occupancy * 100))}%`,
                    backgroundColor:
                      colorScheme === "pb-vision"
                        ? pbHeatColor(zone.occupancy)
                        : selected.color,
                  }}
                />
              </div>
              <span
                className="w-12 text-right text-xs tabular-nums"
                style={{ color: palette.textSupportColor }}
              >
                {(zone.occupancy * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>

        {selected.data_sufficiency === "insufficient" && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
            有效帧不足，以下占用百分比为参考，勿作确定结论。
          </p>
        )}
        {selected.feedback?.summary && (
          <p
            className="mt-3 rounded-lg px-3 py-2 text-xs leading-5"
            style={{
              backgroundColor:
                colorScheme === "pb-vision" ? "#F0FDF4" : "#F5FAF1",
              color: palette.textHeaderColor,
            }}
          >
            {selected.feedback.summary}
          </p>
        )}
      </div>
    </div>
  );
}
