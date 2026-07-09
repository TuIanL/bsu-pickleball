"""构建 StructuredVisualizationData，供前端 SVG 渲染使用。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.pickleball_game_analysis.visualization_schemas import (
    CourtGeometry,
    HeatmapCell,
    PlayerTrajectory,
    ScatterPlayer,
    ScatterPlots,
    StructuredVisualizationData,
    VisualGrid,
    VisualizationPoint,
)

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

    def __init__(self, court: PickleballCourtGeometry | None = None) -> None:
        self.court = court or standard_court()

    def build(
        self,
        *,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
    ) -> StructuredVisualizationData:
        court_geom = CourtGeometry(
            court_width_ft=self.court.width_ft,
            court_length_ft=self.court.length_ft,
        )
        inside_court, outside_visible, dropped = self._split_points(player_points)
        visual_grid = self._build_visual_grid(inside_court)
        scatter = self._build_scatter_plots(inside_court + outside_visible, ball_points, bounce_points)
        trajectories = self._build_player_trajectories(inside_court + outside_visible)

        return StructuredVisualizationData(
            court=court_geom,
            heatmaps=visual_grid,
            scatter_plots=scatter,
            player_trajectories=trajectories,
            outside_court_point_count=len(outside_visible),
            dropped_point_count=len(dropped),
        )

    def build_and_write(
        self,
        *,
        output_path: Path,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
    ) -> StructuredVisualizationData:
        data = self.build(
            player_points=player_points,
            ball_points=ball_points,
            bounce_points=bounce_points,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(_structured_to_dict(data), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return data

    def _split_points(self, player_points: list[VisualizationPoint]) -> tuple[list[VisualizationPoint], list[VisualizationPoint], list[VisualizationPoint]]:
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

    def _build_visual_grid(self, player_points: list[VisualizationPoint]) -> VisualGrid | None:
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
        cells = [
            HeatmapCell(row=r, col=c, count=cnt)
            for (r, c), cnt in sorted(counts.items())
        ]
        return VisualGrid(rows=rows, cols=cols, max_count=max_count, cells=cells)

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
            players.append(ScatterPlayer(
                id=str(index),
                label=label,
                color=PLAYER_HEX_COLORS[index % len(PLAYER_HEX_COLORS)],
                points=coords,
            ))

        ball_coords = [(p.x_ft, p.y_ft) for p in ball_points if self.court.is_in_court_bounds(p.x_ft, p.y_ft)]
        bounce_coords = [(p.x_ft, p.y_ft) for p in bounce_points if self.court.is_in_court_bounds(p.x_ft, p.y_ft)]

        return ScatterPlots(players=players, ball=ball_coords, bounces=bounce_coords)

    def _build_player_trajectories(self, player_points: list[VisualizationPoint]) -> list[PlayerTrajectory]:
        grouped = _group_points_by_label(player_points)
        trajectories: list[PlayerTrajectory] = []
        for index, (label, points) in enumerate(sorted(grouped.items())):
            sorted_points = sorted(points, key=lambda p: p.frame_index or 0)
            path = [(p.x_ft, p.y_ft) for p in sorted_points]
            trajectories.append(PlayerTrajectory(
                id=str(index),
                label=label,
                path=path,
            ))
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
        result["heatmaps"] = {
            "visual_grid": {
                "rows": data.heatmaps.rows,
                "cols": data.heatmaps.cols,
                "max_count": data.heatmaps.max_count,
                "cells": [
                    {"row": c.row, "col": c.col, "count": c.count}
                    for c in data.heatmaps.cells
                ],
            }
        }
    return result
