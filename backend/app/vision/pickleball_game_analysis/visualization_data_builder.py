"""构建 StructuredVisualizationData，供前端 SVG 渲染使用。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.pickleball_game_analysis.visualization_schemas import (
    CourtGeometry,
    HeatmapCell,
    HeatmapPlayerGrid,
    PlayerTrajectory,
    ScatterPlayer,
    ScatterPlots,
    StructuredVisualizationData,
    VisualGrid,
    VisualHeatmaps,
    VisualizationPoint,
    ZoneStats,
    canonical_player_id,
    display_player_label,
    player_palette_color,
)
from app.vision.pickleball_game_analysis.zone_stats import compute_zone_stats

PLAYER_HEX_COLORS: list[str] = [
    "#22C55E",
    "#F97316",
    "#A855F7",
    "#3B82F6",
    "#EF4444",
    "#14B8A6",
]


class PositionVisualizationDataBuilder:
    """从检测/跟踪数据构建 StructuredVisualizationData。

    职责单一：只负责"构建数据"，不负责渲染。
    PositionVisualizer 和前端 SVG 组件都是该数据的消费者。
    """

    def __init__(
        self,
        court: PickleballCourtGeometry | None = None,
        reference_distance_m: float = 0.9,
    ) -> None:
        self.court = court or standard_court()
        # 平均站位距厨房线"参考基准"（米）——硬编码常数，反馈文案标注为参考基准。
        self.reference_distance_m = reference_distance_m

    def build(
        self,
        *,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
        effective_windows: list[tuple[float, float]] | None = None,
    ) -> StructuredVisualizationData:
        court_geom = CourtGeometry(
            court_width_ft=self.court.width_ft,
            court_length_ft=self.court.length_ft,
        )
        inside_court, outside_visible, dropped = self._split_points(player_points)
        heatmaps = self._build_heatmaps(inside_court)
        scatter = self._build_scatter_plots(inside_court + outside_visible, ball_points, bounce_points)
        trajectories = self._build_player_trajectories(inside_court + outside_visible)
        zone_stats = self._build_zone_stats(inside_court + outside_visible, effective_windows)

        return StructuredVisualizationData(
            court=court_geom,
            heatmaps=heatmaps,
            scatter_plots=scatter,
            player_trajectories=trajectories,
            outside_court_point_count=len(outside_visible),
            dropped_point_count=len(dropped),
            zone_stats=zone_stats,
        )

    def build_and_write(
        self,
        *,
        output_path: Path,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
        effective_windows: list[tuple[float, float]] | None = None,
    ) -> StructuredVisualizationData:
        data = self.build(
            player_points=player_points,
            ball_points=ball_points,
            bounce_points=bounce_points,
            effective_windows=effective_windows,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(_structured_to_dict(data), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return data

    def _split_points(
        self, player_points: list[VisualizationPoint]
    ) -> tuple[list[VisualizationPoint], list[VisualizationPoint], list[VisualizationPoint]]:
        """分离球场内、tracking buffer 内、tracking buffer 外三组点。"""
        inside_court: list[VisualizationPoint] = []
        outside_visible: list[VisualizationPoint] = []
        dropped: list[VisualizationPoint] = []
        for p in player_points:
            if self.court.is_in_tracking_bounds(p.x_ft, p.y_ft):
                if self.court.is_in_court_bounds(p.x_ft, p.y_ft):
                    inside_court.append(p)
                else:
                    outside_visible.append(p)
            else:
                dropped.append(p)
        return inside_court, outside_visible, dropped

    def _build_grid(self, player_points: list[VisualizationPoint]) -> VisualGrid | None:
        """把一组点聚合成 22×10 网格（合并视图或单球员视图共用）。"""
        valid = [p for p in player_points if self.court.is_in_court_bounds(p.x_ft, p.y_ft)]
        if not valid:
            return None

        rows = 22
        cols = 10
        counts: dict[tuple[int, int], int] = defaultdict(int)
        for point in valid:
            col = min(cols - 1, max(0, int(point.x_ft / self.court.width_ft * cols)))
            row = min(rows - 1, max(0, int(point.y_ft / self.court.length_ft * rows)))
            counts[(row, col)] += 1

        max_count = max(counts.values(), default=0)
        cells = [HeatmapCell(row=r, col=c, count=cnt) for (r, c), cnt in sorted(counts.items())]
        return VisualGrid(rows=rows, cols=cols, max_count=max_count, cells=cells)

    def _build_heatmaps(self, player_points: list[VisualizationPoint]) -> VisualHeatmaps | None:
        """构建热力图数据：合并视图 + 每球员独立网格（各自 max_count 归一化）。"""
        if not player_points:
            return None
        visual_grid = self._build_grid(player_points)
        players: list[HeatmapPlayerGrid] = []
        for index, (label, points) in enumerate(sorted(_group_points_by_label(player_points).items())):
            grid = self._build_grid(points)
            players.append(
                HeatmapPlayerGrid(
                    id=canonical_player_id(label),
                    label=display_player_label(label),
                    color=player_palette_color(PLAYER_HEX_COLORS, index, label),
                    grid=grid if grid is not None else VisualGrid(),
                )
            )
        return VisualHeatmaps(visual_grid=visual_grid, players=players)

    def _build_zone_stats(
        self,
        player_points: list[VisualizationPoint],
        effective_windows: list[tuple[float, float]] | None,
    ) -> ZoneStats | None:
        """构建区域空间热力图数据（每球员区域占用 + KCR + 反馈）。"""
        if not player_points:
            return None
        players = compute_zone_stats(
            player_points,
            effective_windows=effective_windows,
            reference_distance_m=self.reference_distance_m,
            court=self.court,
            colors=PLAYER_HEX_COLORS,
        )
        return ZoneStats(players=players)

    def _build_scatter_plots(
        self,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
    ) -> ScatterPlots:
        players: list[ScatterPlayer] = []
        grouped = _group_points_by_label(player_points)
        for index, (label, points) in enumerate(sorted(grouped.items())):
            coords = [(p.x_ft, p.y_ft) for p in points]
            players.append(
                ScatterPlayer(
                    id=canonical_player_id(label),
                    label=display_player_label(label),
                    color=player_palette_color(PLAYER_HEX_COLORS, index, label),
                    points=coords,
                )
            )

        ball_coords = [(p.x_ft, p.y_ft) for p in ball_points if self.court.is_in_court_bounds(p.x_ft, p.y_ft)]
        bounce_coords = [(p.x_ft, p.y_ft) for p in bounce_points if self.court.is_in_court_bounds(p.x_ft, p.y_ft)]

        return ScatterPlots(players=players, ball=ball_coords, bounces=bounce_coords)

    def _build_player_trajectories(self, player_points: list[VisualizationPoint]) -> list[PlayerTrajectory]:
        grouped = _group_points_by_label(player_points)
        trajectories: list[PlayerTrajectory] = []
        for _index, (label, points) in enumerate(sorted(grouped.items())):
            sorted_points = sorted(points, key=lambda p: p.frame_index or 0)
            path = [(p.x_ft, p.y_ft) for p in sorted_points]
            trajectories.append(
                PlayerTrajectory(
                    id=canonical_player_id(label),
                    label=display_player_label(label),
                    path=path,
                )
            )
        return trajectories


def _group_points_by_label(points: list[VisualizationPoint]) -> dict[str, list[VisualizationPoint]]:
    grouped: dict[str, list[VisualizationPoint]] = {}
    for point in points:
        label = point.label or "Player"
        grouped.setdefault(label, []).append(point)
    return grouped


def _structured_to_dict(data: StructuredVisualizationData) -> dict:
    """将 StructuredVisualizationData 转为 JSON 可序列化的 dict。"""

    def _point_list(points: list[tuple[float, float]]) -> list[list[float]]:
        return [[round(x, 2), round(y, 2)] for x, y in points]

    result: dict = {
        "court": {
            "court_width_ft": data.court.court_width_ft,
            "court_length_ft": data.court.court_length_ft,
        },
        "outside_court_point_count": data.outside_court_point_count,
        "dropped_point_count": data.dropped_point_count,
        "scatter_plots": {
            "players": [
                {
                    "id": p.id,
                    "label": p.label,
                    "color": p.color,
                    "points": _point_list(p.points),
                }
                for p in data.scatter_plots.players
            ],
            "ball": _point_list(data.scatter_plots.ball),
            "bounces": _point_list(data.scatter_plots.bounces),
        },
        "player_trajectories": [
            {
                "id": t.id,
                "label": t.label,
                "path": _point_list(t.path),
            }
            for t in data.player_trajectories
        ],
    }
    if data.heatmaps is not None:
        heatmaps_payload: dict = {}
        if data.heatmaps.visual_grid is not None:
            heatmaps_payload["visual_grid"] = _grid_to_dict(data.heatmaps.visual_grid)
        heatmaps_payload["players"] = [
            {
                "id": p.id,
                "label": p.label,
                "color": p.color,
                "grid": _grid_to_dict(p.grid),
            }
            for p in data.heatmaps.players
        ]
        result["heatmaps"] = heatmaps_payload
    if data.zone_stats is not None:
        result["zone_stats"] = {
            "players": [
                {
                    "id": player.id,
                    "label": player.label,
                    "color": player.color,
                    "denominator_seconds": player.denominator_seconds,
                    "tracked_seconds": player.tracked_seconds,
                    "data_sufficiency": player.data_sufficiency,
                    "nvz_occupancy_rate": player.nvz_occupancy_rate,
                    # deprecated alias（与 nvz_occupancy_rate 同值同分母，兼容迁移期保留）
                    "kitchen_control_rate": player.kitchen_control_rate,
                    "avg_distance_to_kitchen_line_m": player.avg_distance_to_kitchen_line_m,
                    "zones": [
                        {
                            "zone": zone.zone,
                            "label": zone.label,
                            "seconds": zone.seconds,
                            "occupancy": zone.occupancy,
                        }
                        for zone in player.zones
                    ],
                    "feedback": (
                        {"level": player.feedback.level, "summary": player.feedback.summary}
                        if player.feedback is not None
                        else None
                    ),
                }
                for player in data.zone_stats.players
            ]
        }
    return result


def _grid_to_dict(grid: VisualGrid) -> dict:
    """VisualGrid → JSON dict。"""
    return {
        "rows": grid.rows,
        "cols": grid.cols,
        "max_count": grid.max_count,
        "cells": [{"row": c.row, "col": c.col, "count": c.count} for c in grid.cells],
    }
