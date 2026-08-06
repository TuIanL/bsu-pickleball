"""Generate heatmap and scatter plot image artifacts from court positions."""

from __future__ import annotations

# defaultdict：热力图网格计数；Path：文件路径；Iterable：可接受任意可迭代点集合。
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import cv2  # type: ignore
import numpy as np

# 球场几何与标准球场；小地图渲染器（复用其渲染能力生成静态图）。
from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.pickleball_game_analysis.minimap_visualizer import MinimapVisualizer, player_color
# 清单条目、配置、坐标点、结果对象、标签函数、清单写出函数。
from app.vision.pickleball_game_analysis.visualization_schemas import (
    ManifestItem,
    StructuredVisualizationData,
    VisualGrid,
    VisualizationConfig,
    VisualizationPoint,
    VisualizationResult,
    labels_for,
    write_manifest,
)


class PositionVisualizer:
    def __init__(self, config: VisualizationConfig | None = None, court: PickleballCourtGeometry | None = None) -> None:
        # 配置与球场均允许缺省（回退默认值）；minimap 复用配置与球场；labels 按语言取文案。
        self.config = config or VisualizationConfig()
        self.court = court or standard_court()
        self.minimap = MinimapVisualizer(config=self.config, court=self.court)
        self.labels = labels_for(self.config.language)

    def generate(
        self,
        *,
        job_id: str,
        structured_data: StructuredVisualizationData | None = None,
        heatmaps_dir: Path,
        scatter_plots_dir: Path,
        heatmaps_manifest_path: Path,
        scatter_manifest_path: Path,
        image_url_prefix: str,
        heatmaps_artifact_url: str,
        scatter_artifact_url: str,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
    ) -> tuple[VisualizationResult, VisualizationResult]:
        # 主入口：分别生成"球员热力图"与"散点图（球员/球/弹跳）"两组静态图，并写出各自清单。
        # 如果传入 structured_data，则使用其预计算的 22×10 网格，避免重复计算。
        heat_items = self._generate_heatmaps(
            job_id=job_id,
            output_dir=heatmaps_dir,
            image_url_prefix=f"{image_url_prefix}/heatmaps",
            artifact_url=heatmaps_artifact_url,
            player_points=player_points,
            visual_grid=structured_data.heatmaps.visual_grid if structured_data and structured_data.heatmaps else None,
        )
        scatter_items = self._generate_scatters(
            job_id=job_id,
            output_dir=scatter_plots_dir,
            image_url_prefix=f"{image_url_prefix}/scatter_plots",
            artifact_url=scatter_artifact_url,
            player_points=player_points,
            ball_points=ball_points,
            bounce_points=bounce_points,
        )

        # 有产物则为 available，否则为 no_data；并拼出中文详情文案。
        heat_status = "available" if heat_items else "no_data"
        scatter_status = "available" if scatter_items else "no_data"
        heat_detail = f"已生成 {len(heat_items)} 个热力图" if heat_items else self.labels["no_data"]
        scatter_detail = f"已生成 {len(scatter_items)} 个散点图" if scatter_items else self.labels["no_data"]
        # 写出热力图清单（schema 版本 position_heatmaps.v1）。
        write_manifest(
            heatmaps_manifest_path,
            schema_version="position_heatmaps.v1",
            job_id=job_id,
            status=heat_status,
            detail=heat_detail,
            items=heat_items,
        )
        # 写出散点图清单（schema 版本 position_scatter_plots.v1）。
        write_manifest(
            scatter_manifest_path,
            schema_version="position_scatter_plots.v1",
            job_id=job_id,
            status=scatter_status,
            detail=scatter_detail,
            items=scatter_items,
        )
        return (
            VisualizationResult(heat_status, heat_detail, str(heatmaps_manifest_path), heatmaps_artifact_url, len(heat_items)),
            VisualizationResult(scatter_status, scatter_detail, str(scatter_manifest_path), scatter_artifact_url, len(scatter_items)),
        )

    def _generate_heatmaps(
        self,
        *,
        job_id: str,
        output_dir: Path,
        image_url_prefix: str,
        artifact_url: str,
        player_points: list[VisualizationPoint],
        visual_grid: VisualGrid | None = None,
    ) -> list[ManifestItem]:
        # 热力图只使用正式球场（court_bounds）内的点，界外点不统计。
        valid = [point for point in player_points if self.court.is_in_court_bounds(point.x_ft, point.y_ft)]
        if not valid:
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        items: list[ManifestItem] = []

        file_name = "player_positions_heatmap.png"
        image = self._heatmap_image(valid, grid=visual_grid)
        cv2.imwrite(str(output_dir / file_name), image)
        items.append(
            ManifestItem(
                id="player-positions-heatmap",
                kind="heatmap",
                label=self.labels["player_heatmap"],
                title=self.labels["player_heatmap"],
                description="基于球员轨迹 artifact 的估计球场位置密度。",
                file_name=file_name,
                file_path=str(output_dir / file_name),
                url=f"{image_url_prefix}/{file_name}",
                artifact_url=artifact_url,
                width=image.shape[1],
                height=image.shape[0],
                source_artifacts=["players_trajectory.json"],
            )
        )

        for index, (label, points) in enumerate(_points_by_label(valid).items()):
            safe_label = _safe_file_label(label)
            player_file_name = f"player_positions_heatmap_{safe_label}.png"
            player_image = self._heatmap_image(points, heat_color=player_color(index))
            cv2.imwrite(str(output_dir / player_file_name), player_image)
            items.append(
                ManifestItem(
                    id=f"player-positions-heatmap-{safe_label}",
                    kind="heatmap",
                    label=f"{self.labels['player_heatmap']} · {label}",
                    title=f"{label} {self.labels['player_heatmap']}",
                    description=f"基于球员轨迹 artifact 的 {label} 估计球场位置密度。",
                    file_name=player_file_name,
                    file_path=str(output_dir / player_file_name),
                    url=f"{image_url_prefix}/{player_file_name}",
                    artifact_url=artifact_url,
                    width=player_image.shape[1],
                    height=player_image.shape[0],
                    source_artifacts=["players_trajectory.json"],
                )
            )
        return items

    def _generate_scatters(
        self,
        *,
        job_id: str,
        output_dir: Path,
        image_url_prefix: str,
        artifact_url: str,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
    ) -> list[ManifestItem]:
        # 按需生成三类散点图：球员位置、球轨迹、弹跳候选。哪类有点就生成哪类。
        output_dir.mkdir(parents=True, exist_ok=True)
        items: list[ManifestItem] = []
        if player_points:
            items.append(
                self._write_scatter(
                    output_dir / "player_positions_scatter.png",
                    player_points=player_points,
                    ball_points=[],
                    bounce_points=[],
                    item_id="player-positions-scatter",
                    title=self.labels["player_scatter"],
                    description="基于球员轨迹 artifact 的估计球员位置散点。",
                    file_url=f"{image_url_prefix}/player_positions_scatter.png",
                    artifact_url=artifact_url,
                    source_artifacts=["players_trajectory.json"],
                )
            )
        if ball_points:
            items.append(
                self._write_scatter(
                    output_dir / "ball_trajectory_scatter.png",
                    player_points=[],
                    ball_points=ball_points,
                    bounce_points=[],
                    item_id="ball-trajectory-scatter",
                    title=self.labels["ball_scatter"],
                    description="基于清洗球轨迹 artifact 的球路散点，仅表示候选事实。",
                    file_url=f"{image_url_prefix}/ball_trajectory_scatter.png",
                    artifact_url=artifact_url,
                    source_artifacts=["cleaned_ball_trajectory.json", "ball_trajectory.json"],
                )
            )
        if bounce_points:
            items.append(
                self._write_scatter(
                    output_dir / "bounce_points_scatter.png",
                    player_points=[],
                    ball_points=[],
                    bounce_points=bounce_points,
                    item_id="bounce-points-scatter",
                    title=self.labels["bounce_scatter"],
                    description="基于弹跳候选 artifact 的散点图，不代表比分、犯规或正式落点结论。",
                    file_url=f"{image_url_prefix}/bounce_points_scatter.png",
                    artifact_url=artifact_url,
                    source_artifacts=["bounce_events.json"],
                )
            )
        return items

    def _heatmap_image(
        self,
        points: Iterable[VisualizationPoint],
        *,
        heat_color: tuple[int, int, int] = (0, 208, 255),
        grid: VisualGrid | None = None,
    ) -> np.ndarray:
        # 基于小地图底图，叠加"网格密度着色"得到热力图。
        base = self.minimap.render()                      # 干净的球场底图
        overlay = np.zeros_like(base, dtype=np.uint8)     # 同尺寸空叠加层
        rows = self.config.heatmap_rows
        cols = self.config.heatmap_cols
        if grid is not None:
            # 使用预计算的网格，避免重复计数。
            counts: dict[tuple[int, int], int] = defaultdict(int)
            for cell in grid.cells:
                counts[(cell.row, cell.col)] = cell.count
            max_count = grid.max_count or 1
        else:
            counts = defaultdict(int)
            # 统计每个网格单元里落入的球员点数。
            for point in points:
                if not self.court.is_in_court_bounds(point.x_ft, point.y_ft):
                    continue
                col = min(cols - 1, max(0, int(point.x_ft / self.court.width_ft * cols)))
                row = min(rows - 1, max(0, int(point.y_ft / self.court.length_ft * rows)))
                counts[(row, col)] += 1
            max_count = max(counts.values(), default=1)
        for (row, col), count in counts.items():
            x1 = int(self.config.minimap_padding + col / cols * (self.config.minimap_width - self.config.minimap_padding * 2))
            x2 = int(self.config.minimap_padding + (col + 1) / cols * (self.config.minimap_width - self.config.minimap_padding * 2))
            y1 = int(self.config.minimap_padding + row / rows * (self.config.minimap_height - self.config.minimap_padding * 2))
            y2 = int(self.config.minimap_padding + (row + 1) / rows * (self.config.minimap_height - self.config.minimap_padding * 2))
            intensity = int(255 * count / max_count)
            color = tuple(int(channel * (0.35 + 0.65 * count / max_count)) for channel in heat_color)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        # 把底图与密度叠加层加权混合（底图 0.68 + 叠加 0.32）。
        return cv2.addWeighted(base, 0.68, overlay, 0.32, 0)

    def _write_scatter(
        self,
        path: Path,
        *,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
        item_id: str,
        title: str,
        description: str,
        file_url: str,
        artifact_url: str,
        source_artifacts: list[str],
    ) -> ManifestItem:
        # 用 minimap 渲染把给定点画成散点图并保存，返回对应清单条目。
        image = self.minimap.render(
            player_points=player_points,
            ball_points=ball_points,
            bounce_points=bounce_points,
            limit_player_trails=False,
        )
        cv2.imwrite(str(path), image)
        return ManifestItem(
            id=item_id,
            kind="scatter",
            label=title,
            title=title,
            description=description,
            file_name=path.name,
            file_path=str(path),
            url=file_url,
            artifact_url=artifact_url,
            width=image.shape[1],
            height=image.shape[0],
            source_artifacts=source_artifacts,
        )


def _points_by_label(points: list[VisualizationPoint]) -> dict[str, list[VisualizationPoint]]:
    grouped: dict[str, list[VisualizationPoint]] = {}
    for point in points:
        label = point.label or "Player"
        grouped.setdefault(label, []).append(point)
    return grouped


def _safe_file_label(label: str) -> str:
    safe = "".join(char.lower() if char.isalnum() else "-" for char in label).strip("-")
    return safe or "player"
