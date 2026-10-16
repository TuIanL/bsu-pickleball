import { useState } from "react";
import { scaleQuantize } from "d3-scale";
import { courtSvgDefs } from "../../utils/courtGeometry";
import type { HeatmapPlayerGrid, StructuredVisualizationData, VisualGrid } from "../../types/report";

const HEATMAP_COLORS = ["#0000FF", "#00FF00", "#FFFF00", "#FF0000"];

interface StructuredHeatmapProps {
  data: StructuredVisualizationData | null;
  fallbackPngUrl?: string;
}

export default function StructuredHeatmap({ data, fallbackPngUrl }: StructuredHeatmapProps) {
  const heatmaps = data?.heatmaps;
  const players = heatmaps?.players ?? [];
  const aggregateGrid = heatmaps?.visual_grid;

  if (!heatmaps || (!aggregateGrid && players.length === 0)) {
    if (fallbackPngUrl) {
      return (
        <img
          alt="位置热力图"
          className="aspect-[11/16] w-full bg-[var(--ui-surface)] object-contain"
          src={fallbackPngUrl}
        />
      );
    }
    return null;
  }

  // 旧 JSON 无 per-player 网格时，回退渲染合并网格。
  if (players.length === 0 && aggregateGrid) {
    return (
      <div>
        <AggregateHeatmapSVG grid={aggregateGrid} />
        <IdentitySlotStatus slots={heatmaps.identity_slots} />
        {heatmaps.aggregate_source === "anonymous_unbound_observations" ? (
          <p className="mt-2 text-xs text-[var(--ui-text-muted)]">合并区域统计含未确认球员观测，不代表个人 P1–P4。</p>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      {players.length ? <PlayerLayersHeatmapSVG players={players} /> : <AggregateHeatmapSVG grid={aggregateGrid!} />}
      <IdentitySlotStatus slots={heatmaps.identity_slots} />
    </div>
  );
}

function IdentitySlotStatus({ slots }: { slots?: NonNullable<StructuredVisualizationData["heatmaps"]>["identity_slots"] }) {
  if (!slots?.length) return null;
  return (
    <div className="mt-3 rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-3" aria-label="冻结名册身份状态">
      <p className="text-xs font-bold text-[var(--ui-ink)]">冻结名册身份状态</p>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {slots.map((slot) => (
          <div key={slot.id} className="rounded-lg bg-[var(--ui-surface)] px-2.5 py-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <strong className="text-[var(--ui-ink)]">
                {slot.label}{slot.canonical_end ? ` · ${slot.canonical_end === "end_a" ? "A端" : "B端"}` : ""}
              </strong>
              <span className={slot.status === "confirmed" ? "font-semibold text-green-700" : "font-semibold text-amber-700"}>
                {slot.status === "confirmed" ? "已确认" : slot.status === "unavailable" ? "不可用" : "未确认"}
              </span>
            </div>
            {slot.reason ? <p className="mt-1 text-[var(--ui-text-muted)]">{identityReasonLabel(slot.reason)}</p> : null}
            {typeof slot.observed_samples === "number" ? (
              <p className="mt-1 text-[var(--ui-text-muted)]">已确认有效点 {slot.observed_samples}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function identityReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    bootstrap_binding_no_simultaneous_observation: "锚点时刻没有可匹配观测",
    bootstrap_binding_waiting_global_association: "锚点已匹配到检测轨迹，等待全局身份关联",
    bootstrap_binding_tracklet_competes_for_slots: "同一检测轨迹竞争多个名册槽",
    bootstrap_binding_ambiguous_match: "锚点匹配存在歧义",
    bootstrap_binding_conflicting_slots: "多个名册槽竞争同一观测",
    bootstrap_binding_insufficient_evidence: "观测证据不足，未绑定身份",
    frozen_identity_end_mismatch: "观测端位与名册不一致",
    frozen_identity_already_owned: "该观测已绑定其他名册槽",
    roster_snapshot_hash_mismatch: "冻结名册校验失败",
    roster_snapshot_missing: "冻结名册不可用",
  };
  return labels[reason] ?? reason.replaceAll("_", " ");
}

function HeatmapCourtBase({ children }: { children: React.ReactNode }) {
  const defs = courtSvgDefs();
  return (
    <svg viewBox={defs.viewBox} className="w-full bg-[var(--ui-surface)]" style={{ aspectRatio: "200/440" }}>
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
      {children}
    </svg>
  );
}

/** 合并网格回退视图（蓝→红渐变）。 */
function AggregateHeatmapSVG({ grid }: { grid: VisualGrid }) {
  const defs = courtSvgDefs();
  const max = grid.max_count || 1;
  const colorScale = scaleQuantize<string>().domain([0, max]).range(HEATMAP_COLORS);
  const cellWidth = defs.courtOutline.width / grid.cols;
  const cellHeight = defs.courtOutline.height / grid.rows;

  return (
    <HeatmapCourtBase>
      {grid.cells.map((cell) => {
        if (cell.count === 0) return null;
        const x = defs.courtOutline.x + cell.col * cellWidth;
        const y = defs.courtOutline.y + cell.row * cellHeight;
        return (
          <rect
            key={`${cell.row}-${cell.col}`}
            x={x}
            y={y}
            width={cellWidth}
            height={cellHeight}
            fill={colorScale(cell.count)}
            opacity={0.55}
          />
        );
      })}
    </HeatmapCourtBase>
  );
}

/** 每球员图层 + 图例切换（默认全开，各自 max_count 归一化）。 */
function PlayerLayersHeatmapSVG({ players }: { players: HeatmapPlayerGrid[] }) {
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(() => new Set(players.map((p) => p.id)));
  const defs = courtSvgDefs();

  function toggleLayer(id: string) {
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="relative">
      <HeatmapCourtBase>
        {players.map((player) => {
          if (!visibleLayers.has(player.id)) return null;
          const grid = player.grid;
          const max = grid.max_count || 1;
          const cellWidth = defs.courtOutline.width / grid.cols;
          const cellHeight = defs.courtOutline.height / grid.rows;
          return grid.cells.map((cell) => {
            if (cell.count === 0) return null;
            const x = defs.courtOutline.x + cell.col * cellWidth;
            const y = defs.courtOutline.y + cell.row * cellHeight;
            return (
              <rect
                key={`${player.id}-${cell.row}-${cell.col}`}
                x={x}
                y={y}
                width={cellWidth}
                height={cellHeight}
                fill={player.color}
                opacity={0.28 + 0.62 * (cell.count / max)}
              />
            );
          });
        })}
      </HeatmapCourtBase>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 px-2">
        {players.map((player) => (
          <button
            key={`legend-heatmap-${player.id}`}
            onClick={() => toggleLayer(player.id)}
            className="flex items-center gap-1.5 text-xs font-medium"
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: player.color, opacity: visibleLayers.has(player.id) ? 1 : 0.3 }}
            />
            <span className={visibleLayers.has(player.id) ? "text-[var(--ui-ink)]" : "text-slate-400 line-through"}>
              {player.label}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
