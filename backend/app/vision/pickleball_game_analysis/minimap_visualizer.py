"""Render a 2D pickleball minimap from standard court coordinates."""

from __future__ import annotations

# dataclass：用装饰器快速定义数据结构；Iterable：可接受任意可迭代的点集合。
from dataclasses import dataclass
from typing import Iterable

# OpenCV（绘图与图像操作）；numpy（图像数组与几何计算）。# type: ignore 表示忽略类型检查器的导入报错。
import cv2  # type: ignore
import numpy as np

# 球场几何：CourtLine（线）、PickleballCourtGeometry（球场几何对象）、standard_court（标准球场工厂）。
from app.vision.courtvision_calibration_engine.court_geometry import CourtLine, PickleballCourtGeometry, standard_court
# 可视化数据结构：VisualizationConfig（配置）、VisualizationPoint（单个坐标点）。
from app.vision.pickleball_game_analysis.visualization_schemas import VisualizationConfig, VisualizationPoint


@dataclass(frozen=True)
class MinimapStyle:
    # 小地图各元素的 BGR 颜色（注意 OpenCV 用 BGR 而非 RGB 顺序）。frozen=True 表示不可变配色方案。
    background: tuple[int, int, int] = (246, 249, 244)       # 背景底色（浅灰绿）
    court_fill: tuple[int, int, int] = (226, 242, 224)       # 球场填充色（浅绿）
    line: tuple[int, int, int] = (34, 76, 45)                # 球场线颜色（深绿）
    kitchen_fill: tuple[int, int, int] = (216, 235, 245)     # 厨房区填充色（浅蓝）
    player: tuple[int, int, int] = (33, 138, 52)             # 球员轨迹/点颜色（绿）
    ball: tuple[int, int, int] = (28, 114, 235)              # 球轨迹/点颜色（蓝）
    bounce: tuple[int, int, int] = (30, 90, 255)             # 弹跳点标记颜色（亮蓝）


PLAYER_COLORS: tuple[tuple[int, int, int], ...] = (
    (33, 138, 52),    # green
    (224, 95, 36),    # orange
    (190, 72, 178),   # magenta
    (42, 128, 214),   # blue
    (80, 92, 220),    # red-blue
    (40, 160, 160),   # teal
)


class MinimapVisualizer:
    def __init__(
        self,
        config: VisualizationConfig | None = None,
        court: PickleballCourtGeometry | None = None,
        style: MinimapStyle | None = None,
    ) -> None:
        # 三个参数都允许缺省：缺省时分别回退到默认配置、标准球场、默认配色。
        self.config = config or VisualizationConfig()
        self.court = court or standard_court()
        self.style = style or MinimapStyle()

    def court_to_pixel(self, x_ft: float, y_ft: float, *, clamp: bool = False) -> tuple[int, int] | None:
        # 把“英尺球场坐标 (x_ft, y_ft)”映射到小地图图像像素坐标。
        # clamp=False 且点界外时返回 None；clamp=True 时把坐标夹到 [0, 边界] 再映射（保证不越界）。
        if not clamp and not self.court.is_in_bounds(x_ft, y_ft):
            return None
        # 若开启 clamp，则把坐标限制在合法范围内，否则直接使用原始坐标。
        x = min(self.court.width_ft, max(0.0, float(x_ft))) if clamp else float(x_ft)
        y = min(self.court.length_ft, max(0.0, float(y_ft))) if clamp else float(y_ft)
        pad = self.config.minimap_padding  # 小地图四周留白像素
        draw_width = self.config.minimap_width - pad * 2     # 实际可绘制宽度
        draw_height = self.config.minimap_height - pad * 2  # 实际可绘制高度
        # 按“坐标 / 球场尺寸”的比例映射到像素空间，再加上留白偏移。
        px = pad + (x / self.court.width_ft) * draw_width
        py = pad + (y / self.court.length_ft) * draw_height
        return (int(round(px)), int(round(py)))

    def render(
        self,
        *,
        player_points: Iterable[VisualizationPoint] = (),
        ball_points: Iterable[VisualizationPoint] = (),
        bounce_points: Iterable[VisualizationPoint] = (),
        limit_player_trails: bool = True,
    ) -> np.ndarray:
        # 生成一张小地图图像：先铺背景，再画球场、球员轨迹、球轨迹，最后画弹跳点标记。
        # 用 np.full 创建一张纯色背景图（高度、宽度、3 通道），dtype=uint8。
        image = np.full(
            (self.config.minimap_height, self.config.minimap_width, 3),
            self.style.background,
            dtype=np.uint8,
        )
        self._draw_court(image)  # 画球场底色、厨房区、各条线
        for index, (_label, points) in enumerate(_points_by_label(list(player_points)).items()):
            draw_points = points[-self.config.trail_length :] if limit_player_trails else points
            self._draw_trails(image, draw_points, player_color(index), radius=4)
        # 画球轨迹，但只保留最后 trail_length 个点（形成拖尾效果）。
        self._draw_trails(image, list(ball_points)[-self.config.trail_length :], self.style.ball, radius=3)
        for point in bounce_points:
            # 每个弹跳点画一个倾斜十字标记。
            pixel = self.court_to_pixel(point.x_ft, point.y_ft)
            if pixel is not None:
                cv2.drawMarker(image, pixel, self.style.bounce, markerType=cv2.MARKER_TILTED_CROSS, markerSize=12, thickness=2)
        return image

    def _draw_court(self, image: np.ndarray) -> None:
        # 先构造球场外边界四个角的像素坐标（强制 clamp 避免越界），填充球场底色多边形。
        boundary = [
            self.court_to_pixel(0, 0, clamp=True),
            self.court_to_pixel(self.court.width_ft, 0, clamp=True),
            self.court_to_pixel(self.court.width_ft, self.court.length_ft, clamp=True),
            self.court_to_pixel(0, self.court.length_ft, clamp=True),
        ]
        # 过滤掉 None 后转成 numpy 数组，填充多边形。
        pts = np.array([point for point in boundary if point is not None], dtype=np.int32)
        cv2.fillPoly(image, [pts], self.style.court_fill)
        # 逐个厨房区（非截击区）填充浅蓝色多边形。
        for zone in self.court.kitchen_zones:
            zone_pts = [self.court_to_pixel(p.x, p.y, clamp=True) for p in zone.polygon.points]
            cv2.fillPoly(image, [np.array([p for p in zone_pts if p is not None], dtype=np.int32)], self.style.kitchen_fill)
        # 逐条球场线绘制。
        for line in self.court.lines:
            self._draw_line(image, line)

    def _draw_line(self, image: np.ndarray, line: CourtLine) -> None:
        # 把一条球场线的起止点映射到像素并画线（抗锯齿）。
        start = self.court_to_pixel(line.start.x, line.start.y, clamp=True)
        end = self.court_to_pixel(line.end.x, line.end.y, clamp=True)
        if start is not None and end is not None:
            cv2.line(image, start, end, self.style.line, 2, lineType=cv2.LINE_AA)

    def _draw_trails(self, image: np.ndarray, points: list[VisualizationPoint], color: tuple[int, int, int], radius: int) -> None:
        # 把轨迹点映射成像素坐标（过滤无效点）。
        pixels = [self.court_to_pixel(point.x_ft, point.y_ft) for point in points]
        pixels = [pixel for pixel in pixels if pixel is not None]
        # 至少 2 个点才画折线（拖尾轨迹），否则只画散点。
        if len(pixels) >= 2:
            cv2.polylines(image, [np.array(pixels, dtype=np.int32)], isClosed=False, color=color, thickness=2, lineType=cv2.LINE_AA)
        # 每个点画一个实心圆（半径 radius）。
        for pixel in pixels:
            cv2.circle(image, pixel, radius, color, -1, lineType=cv2.LINE_AA)


def player_color(index: int) -> tuple[int, int, int]:
    return PLAYER_COLORS[index % len(PLAYER_COLORS)]


def _points_by_label(points: list[VisualizationPoint]) -> dict[str, list[VisualizationPoint]]:
    grouped: dict[str, list[VisualizationPoint]] = {}
    for point in points:
        label = point.label or "Player"
        grouped.setdefault(label, []).append(point)
    return grouped
