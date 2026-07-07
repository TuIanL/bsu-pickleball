"""热力图生成 —— 将球场坐标点映射为网格热力图单元。"""

from __future__ import annotations

# Heatmap：整张热力图（行数、列数、单元列表）。
# HeatmapCell：单个网格单元（行列坐标 + 出现次数）。
from app.schemas.metrics import Heatmap, HeatmapCell
# ProjectedTrackPoint：投影到标准球场坐标系（英尺）的轨迹点。
from app.schemas.tracking import ProjectedTrackPoint
# StandardPickleballCourt / standard_court：标准球场几何，提供尺寸与边界判定。
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court


def generate_heatmap(
    points: list[ProjectedTrackPoint],
    rows: int = 11,
    cols: int = 5,
    court: StandardPickleballCourt | None = None,
) -> Heatmap:
    """将球员轨迹点聚合成网格热力图。

    参数：
      points：投影到球场坐标系的轨迹点。
      rows / cols：热力图网格的行数（沿球场长度）与列数（沿球场宽度），默认 11×5。
      court：球场几何定义；缺省时使用标准球场。
    逻辑：把每个在界内的点按“x/宽度→列、y/长度→行”映射到网格，统计每格出现次数。
    """
    # 未显式传入球场时，使用标准球场定义。
    court = court or standard_court()
    # 用 (row, col) 元组作为键，累计每个网格单元的出现次数。
    counts: dict[tuple[int, int], int] = {}

    for point in points:
        # 界外点不计入热力图。
        if not court.is_in_bounds(point.court_point.x, point.court_point.y):
            continue
        # 由 x（宽度方向）归一化到 [0,1) 再乘以列数，得到列索引，并夹在 [0, cols-1]。
        col = min(cols - 1, max(0, int(point.court_point.x / court.width_ft * cols)))
        # 由 y（长度方向）归一化得到行索引，并夹在 [0, rows-1]。
        row = min(rows - 1, max(0, int(point.court_point.y / court.length_ft * rows)))
        # 对应网格计数 +1。
        counts[(row, col)] = counts.get((row, col), 0) + 1

    # 把计数表转换为已排序的 HeatmapCell 列表（按 (row, col) 升序）。
    cells = [HeatmapCell(row=row, col=col, count=count) for (row, col), count in sorted(counts.items())]
    return Heatmap(rows=rows, cols=cols, cells=cells)
