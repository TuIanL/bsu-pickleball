import { useMemo, useState } from "react";
import { scaleQuantize } from "d3-scale";
import { courtSvgDefs } from "../../utils/courtGeometry";
import type { StructuredVisualizationData } from "../../types/report";

const HEATMAP_COLORS = ["#0000FF", "#00FF00", "#FFFF00", "#FF0000"];

interface StructuredHeatmapProps {
  data: StructuredVisualizationData | null;
  fallbackPngUrl?: string;
}

export default function StructuredHeatmap({ data, fallbackPngUrl }: StructuredHeatmapProps) {
  const grid = data?.heatmaps?.visual_grid;

  if (!grid || grid.cells.length === 0) {
    if (fallbackPngUrl) {
      return (
        <img
          alt="位置热力图"
          className="aspect-[11/16] w-full bg-white object-contain"
          src={fallbackPngUrl}
        />
      );
    }
    return null;
  }

  return <HeatmapSVG grid={grid} />;
}

function HeatmapSVG({ grid }: { grid: NonNullable<StructuredVisualizationData["heatmaps"]>["visual_grid"] }) {
  const [hovered, setHovered] = useState<{ row: number; col: number; count: number } | null>(null);
  const defs = courtSvgDefs();

  const colorScale = useMemo(() => {
    const max = grid.max_count || 1;
    return scaleQuantize<string>().domain([0, max]).range(HEATMAP_COLORS);
  }, [grid.max_count]);

  const cellWidth = defs.courtOutline.width / grid.cols;
  const cellHeight = defs.courtOutline.height / grid.rows;

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
        {grid.cells.map((cell) => {
          if (cell.count === 0) return null;
          const x = defs.courtOutline.x + cell.col * cellWidth;
          const y = defs.courtOutline.y + cell.row * cellHeight;
          const fill = colorScale(cell.count);
          const isHovered = hovered?.row === cell.row && hovered?.col === cell.col;
          return (
            <rect
              key={`${cell.row}-${cell.col}`}
              x={x}
              y={y}
              width={cellWidth}
              height={cellHeight}
              fill={fill}
              opacity={isHovered ? 0.85 : 0.55}
              stroke={isHovered ? "#14241B" : "none"}
              strokeWidth={isHovered ? 1 : 0}
              className="cursor-pointer transition-opacity"
              onMouseEnter={() => setHovered(cell)}
              onMouseLeave={() => setHovered(null)}
            />
          );
        })}
        {hovered && (
          <rect
            x={defs.courtOutline.x + hovered.col * cellWidth}
            y={defs.courtOutline.y + hovered.row * cellHeight}
            width={cellWidth}
            height={cellHeight}
            fill="none"
            stroke="#14241B"
            strokeWidth={2}
            rx={1}
          />
        )}
      </svg>
      {hovered && (
        <div className="absolute left-1/2 top-2 -translate-x-1/2 rounded-lg bg-[#14241B] px-3 py-1.5 text-xs font-semibold text-white shadow-lg">
          第{hovered.row + 1}行第{hovered.col + 1}列: {hovered.count} 次
        </div>
      )}
      <ColorLegend maxCount={grid.max_count} colors={HEATMAP_COLORS} />
    </div>
  );
}

function ColorLegend({ maxCount, colors }: { maxCount: number; colors: string[] }) {
  const steps = colors.length;
  const segments = steps - 1;
  const segWidth = 20;

  return (
    <div className="mt-2 flex items-center gap-3 px-2">
      <div className="flex rounded-md overflow-hidden border border-[#DDE9D6]">
        {Array.from({ length: segments }, (_, i) => (
          <div
            key={i}
            className="h-3"
            style={{
              width: segWidth,
              background: `linear-gradient(to right, ${colors[i]}, ${colors[i + 1]})`,
            }}
          />
        ))}
      </div>
      <span className="text-[10px] font-medium text-slate-500">0</span>
      <div className="flex-1" />
      <span className="text-[10px] font-medium text-slate-500">{maxCount}</span>
    </div>
  );
}
