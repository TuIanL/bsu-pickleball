import { useState } from "react";
import { courtToSvg, courtSvgDefs } from "../../utils/courtGeometry";
import type { StructuredVisualizationData } from "../../types/report";

const BALL_COLOR = "#3B82F6";
const BOUNCE_COLOR = "#EF4444";
const BOUNCE_CROSS_SIZE = 4;

interface StructuredScatterPlotProps {
  data: StructuredVisualizationData | null;
  fallbackPngUrl?: string;
}

export default function StructuredScatterPlot({ data, fallbackPngUrl }: StructuredScatterPlotProps) {
  const hasPlayers = (data?.scatter_plots.players?.length ?? 0) > 0;
  const hasBall = (data?.scatter_plots.ball?.length ?? 0) > 0;
  const hasBounces = (data?.scatter_plots.bounces?.length ?? 0) > 0;

  if (!hasPlayers && !hasBall && !hasBounces) {
    if (fallbackPngUrl) {
      return (
        <img
          alt="位置散点图"
          className="aspect-[11/16] w-full bg-white object-contain"
          src={fallbackPngUrl}
        />
      );
    }
    return null;
  }

  return <ScatterSVG data={data!} />;
}

function ScatterSVG({ data }: { data: StructuredVisualizationData }) {
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(() => {
    const all = new Set<string>();
    data.scatter_plots.players.forEach((p) => all.add(`player-${p.id}`));
    if (data.scatter_plots.ball.length > 0) all.add("ball");
    if (data.scatter_plots.bounces.length > 0) all.add("bounces");
    return all;
  });

  const defs = courtSvgDefs();

  function toggleLayer(key: string) {
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="relative">
      <svg viewBox={defs.viewBox} className="w-full bg-white" style={{ aspectRatio: "200/440" }}>
        <rect
          x={defs.courtOutline.x}
          y={defs.courtOutline.y}
          width={defs.courtOutline.width}
          height={defs.courtOutline.height}
          fill="#F5FAF1"
          stroke="#14241B"
          strokeWidth={1}
          rx={2}
        />
        <line x1={defs.net.x1} y1={defs.net.y1} x2={defs.net.x2} y2={defs.net.y2} stroke="#14241B" strokeWidth={1.5} strokeDasharray="4,3" />
        <line x1={defs.kitchenTop.x1} y1={defs.kitchenTop.y1} x2={defs.kitchenTop.x2} y2={defs.kitchenTop.y2} stroke="#22C55E" strokeWidth={1} strokeDasharray="3,2" />
        <line x1={defs.kitchenBottom.x1} y1={defs.kitchenBottom.y1} x2={defs.kitchenBottom.x2} y2={defs.kitchenBottom.y2} stroke="#22C55E" strokeWidth={1} strokeDasharray="3,2" />
        {data.scatter_plots.players.map((player) => {
          if (!visibleLayers.has(`player-${player.id}`)) return null;
          return player.points.map((pt, i) => {
            const svg = courtToSvg(pt[0], pt[1]);
            return (
              <circle
                key={`p-${player.id}-${i}`}
                cx={svg.x}
                cy={svg.y}
                r={2.5}
                fill={player.color}
                opacity={0.6}
              />
            );
          });
        })}
        {visibleLayers.has("ball") &&
          data.scatter_plots.ball.map((pt, i) => {
            const svg = courtToSvg(pt[0], pt[1]);
            return (
              <circle
                key={`b-${i}`}
                cx={svg.x}
                cy={svg.y}
                r={1.5}
                fill={BALL_COLOR}
                opacity={0.5}
              />
            );
          })}
        {visibleLayers.has("bounces") &&
          data.scatter_plots.bounces.map((pt, i) => {
            const svg = courtToSvg(pt[0], pt[1]);
            return (
              <g key={`bo-${i}`}>
                <line
                  x1={svg.x - BOUNCE_CROSS_SIZE}
                  y1={svg.y - BOUNCE_CROSS_SIZE}
                  x2={svg.x + BOUNCE_CROSS_SIZE}
                  y2={svg.y + BOUNCE_CROSS_SIZE}
                  stroke={BOUNCE_COLOR}
                  strokeWidth={1.5}
                />
                <line
                  x1={svg.x - BOUNCE_CROSS_SIZE}
                  y1={svg.y + BOUNCE_CROSS_SIZE}
                  x2={svg.x + BOUNCE_CROSS_SIZE}
                  y2={svg.y - BOUNCE_CROSS_SIZE}
                  stroke={BOUNCE_COLOR}
                  strokeWidth={1.5}
                />
              </g>
            );
          })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 px-2">
        {data.scatter_plots.players.map((player) => (
          <button
            key={`legend-player-${player.id}`}
            onClick={() => toggleLayer(`player-${player.id}`)}
            className="flex items-center gap-1.5 text-xs font-medium"
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: player.color, opacity: visibleLayers.has(`player-${player.id}`) ? 1 : 0.3 }}
            />
            <span className={visibleLayers.has(`player-${player.id}`) ? "text-[#14241B]" : "text-slate-400 line-through"}>
              {player.label}
            </span>
          </button>
        ))}
        {data.scatter_plots.ball.length > 0 && (
          <button
            onClick={() => toggleLayer("ball")}
            className="flex items-center gap-1.5 text-xs font-medium"
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: BALL_COLOR, opacity: visibleLayers.has("ball") ? 1 : 0.3 }}
            />
            <span className={visibleLayers.has("ball") ? "text-[#14241B]" : "text-slate-400 line-through"}>
              球轨迹
            </span>
          </button>
        )}
        {data.scatter_plots.bounces.length > 0 && (
          <button
            onClick={() => toggleLayer("bounces")}
            className="flex items-center gap-1.5 text-xs font-medium"
          >
            <span className="inline-flex items-center justify-center h-2.5 w-2.5">
              <span className="text-[9px] font-bold leading-none" style={{ color: visibleLayers.has("bounces") ? BOUNCE_COLOR : "#94A3B8" }}>
                ✕
              </span>
            </span>
            <span className={visibleLayers.has("bounces") ? "text-[#14241B]" : "text-slate-400 line-through"}>
              弹跳候选
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
