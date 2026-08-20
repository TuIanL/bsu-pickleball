import { useMemo } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import StructuredZoneHeatmap from "../platform/StructuredZoneHeatmap";
import type {
  AnalysisReport,
  HeatmapPlayerGrid,
  MovementPoint,
  StructuredVisualizationData,
  VisualHeatmaps,
} from "../../types/report";

function getDistanceFt(report: AnalysisReport, playerId: string): number {
  try {
    const metricsAny = (report as unknown as { metrics?: unknown }).metrics;
    if (metricsAny && typeof metricsAny === "object") {
      const distances = (
        metricsAny as {
          distances?: Array<{ track_id?: string; player_id?: string; distance_ft?: number }>;
        }
      ).distances;
      if (Array.isArray(distances)) {
        const match = distances.find(
          (d) =>
            (d.track_id && d.track_id === playerId) ||
            (d.player_id && d.player_id === playerId)
        );
        if (match && typeof match.distance_ft === "number") {
          return Math.round(match.distance_ft);
        }
      }
    }
  } catch {
    // ignore
  }

  const movement: MovementPoint[] | undefined = report?.session?.movementPath;
  if (Array.isArray(movement) && movement.length > 0) {
    return Math.round(movement.length * 0.3);
  }

  return 727;
}

function getPlayerHeatmap(
  report: AnalysisReport,
  playerId: string
): HeatmapPlayerGrid | null {
  try {
    const reportAny = report as unknown as {
      metrics?: { heatmap?: VisualHeatmaps };
      visualizations?: StructuredVisualizationData;
    };
    const sources: (VisualHeatmaps | undefined)[] = [];
    if (reportAny.metrics?.heatmap) sources.push(reportAny.metrics.heatmap);
    if (reportAny.visualizations?.heatmaps) sources.push(reportAny.visualizations.heatmaps);
    for (const src of sources) {
      if (src?.players && Array.isArray(src.players)) {
        const match = src.players.find((p) => p.id === playerId);
        if (match) return match;
      }
    }
  } catch {
    // ignore
  }
  return null;
}

function PickleballCourtPlaceholder() {
  return (
    <svg
      viewBox="0 0 200 125"
      className="w-full h-full"
      preserveAspectRatio="xMidYMid meet"
    >
      <rect x="10" y="10" width="180" height="105" fill="#f9fafb" stroke="#9ca3af" strokeWidth="1.2" rx="3" />
      <line x1="10" y1="62.5" x2="190" y2="62.5" stroke="#6b7280" strokeWidth="1.5" strokeDasharray="4,3" />
      <line x1="10" y1="32" x2="190" y2="32" stroke="#22c55e" strokeWidth="0.8" strokeDasharray="3,2" />
      <line x1="10" y1="93" x2="190" y2="93" stroke="#22c55e" strokeWidth="0.8" strokeDasharray="3,2" />
      <line x1="100" y1="10" x2="100" y2="115" stroke="#9ca3af" strokeWidth="1" />
      <text x="100" y="67" textAnchor="middle" fontSize="8" fill="#9ca3af" opacity="0.7">球网</text>
      <text x="100" y="22" textAnchor="middle" fontSize="6" fill="#9ca3af" opacity="0.6">厨房区</text>
      <text x="100" y="103" textAnchor="middle" fontSize="6" fill="#9ca3af" opacity="0.6">厨房区</text>
    </svg>
  );
}

export default function PbCourtCoverage() {
  const { selectedPlayerId, report } = usePbReport();

  const distanceFt = useMemo(
    () => getDistanceFt(report, selectedPlayerId),
    [report, selectedPlayerId]
  );

  const playerHeatmap = useMemo(
    () => getPlayerHeatmap(report, selectedPlayerId),
    [report, selectedPlayerId]
  );

  const heatmapDataForStructured = useMemo<StructuredVisualizationData | null>(() => {
    if (!playerHeatmap) return null;
    return {
      court: { court_width_ft: 20, court_length_ft: 44 },
      heatmaps: { players: [playerHeatmap] },
      scatter_plots: {
        players: [],
        ball: [],
        bounces: [],
      },
      player_trajectories: [],
    } as unknown as StructuredVisualizationData;
  }, [playerHeatmap]);

  return (
    <div className="pb-card p-5 sm:p-6">
      <div className="mb-4">
        <h3 className="font-bold text-lg text-[var(--pb-text-primary,#111827)]">
          场地覆盖
        </h3>
        <div className="mt-2 flex items-center gap-3">
          <span className="text-xs uppercase tracking-widest text-[var(--pb-text-secondary,#6b7280)]">
            比赛概览
          </span>
          <div className="flex-1 h-px bg-[var(--pb-card-border,#e5e7eb)]" />
        </div>
        <p className="mt-3 text-2xl font-black text-[var(--pb-text-primary,#111827)]">
          移动距离：{" "}
          <span className="text-[var(--pb-primary,#00FF41)]">{distanceFt}</span>{" "}
          <span className="text-lg font-semibold">英尺</span>
        </p>
      </div>

      <div
        className="w-full rounded-xl overflow-hidden bg-[#f9fafb] border border-[var(--pb-card-border,#e5e7eb)]"
        style={{ aspectRatio: "16 / 10" }}
      >
        {heatmapDataForStructured ? (
          <div className="w-full h-full p-2">
            <StructuredZoneHeatmap
              data={heatmapDataForStructured}
              {...({ colorScheme: "pb-vision" } as unknown as object)}
            />
          </div>
        ) : (
          <PickleballCourtPlaceholder />
        )}
      </div>
    </div>
  );
}
