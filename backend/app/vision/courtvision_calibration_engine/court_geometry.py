"""
匹克球场几何模型（court_geometry）—— 标准 20×44 英尺球场，含各区域定义。

这个文件把"一张标准匹克球场"用数学结构描述出来：
- 球场坐标用英尺，x 从左到右 0→20，y 从近端底线到远端底线 0→44，球网在 y=22；
- 定义了点(CourtPoint)、线(CourtLine)、多边形(CourtPolygon)、区域(CourtZone)；
- PickleballCourtGeometry 预存了所有线、区域，以及"判断某点在不在界内/厨房区/哪个发球区"的方法。

它是后面"投影画线、判定球员位置"的基础数据。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# dataclass：数据类（详见 schemas.py 注释）。
from dataclasses import dataclass


@dataclass(frozen=True)
class CourtPoint:
    """球场上的一个点（x, y），坐标单位是英尺。"""
    x: float
    y: float


@dataclass(frozen=True)
class CourtLine:
    """球场上的一条线（有名字 + 起点 + 终点）。例如球网、边线、厨房线。"""
    name: str
    start: CourtPoint
    end: CourtPoint


@dataclass(frozen=True)
class CourtPolygon:
    """一个多边形区域（有名字 + 一串顶点），用于区域填充/判断。"""
    name: str
    points: tuple[CourtPoint, ...]


@dataclass(frozen=True)
class CourtZone:
    """
    一个轴对齐的矩形区域（用 x/y 的最小最大值界定）。

    提供：
    - contains：判断某点是否落在这个矩形区域内；
    - polygon 属性：把它转成 CourtPolygon（供画线/填充用）。
    """
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def contains(self, point: CourtPoint) -> bool:
        """判断点是否在这个矩形区域内（含边界）。"""
        return self.x_min <= point.x <= self.x_max and self.y_min <= point.y <= self.y_max

    @property
    def polygon(self) -> CourtPolygon:
        """把这个矩形区域转成 4 个顶点的多边形（顺序：左下→右下→右上→左上）。"""
        return CourtPolygon(
            self.name,
            (
                CourtPoint(self.x_min, self.y_min),
                CourtPoint(self.x_max, self.y_min),
                CourtPoint(self.x_max, self.y_max),
                CourtPoint(self.x_min, self.y_max),
            ),
        )


@dataclass(frozen=True)
class PickleballCourtGeometry:
    """
    标准匹克球场几何（单位：英尺）。

    坐标约定（重要）：
    - x：从左到右，0 → 20 英尺（球场宽）；
    - y：从近端底线(near) → 远端底线(far)，0 → 44 英尺（球场长）；
    - 球网在 y = 22 英尺处（球场正中）。

    下面大量 @property 是"按需即时计算"的便捷属性：
    比如 net_line 会返回一个 CourtLine 对象，无需预先存。
    """

    unit: str = "feet"
    width_ft: float = 20.0          # 球场宽（英尺）
    length_ft: float = 44.0         # 球场长（英尺）
    net_y_ft: float = 22.0          # 球网所在的 y 坐标（球场正中）
    kitchen_depth_ft: float = 7.0   # 厨房区（非截击区）深度（英尺）

    @property
    def near_kitchen_y_ft(self) -> float:
        """近端厨房线 y 坐标 = 球网 - 厨房深度 = 22 - 7 = 15。"""
        return self.net_y_ft - self.kitchen_depth_ft

    @property
    def far_kitchen_y_ft(self) -> float:
        """远端厨房线 y 坐标 = 球网 + 厨房深度 = 22 + 7 = 29。"""
        return self.net_y_ft + self.kitchen_depth_ft

    @property
    def coordinate_system(self) -> dict[str, float | str]:
        """简要描述坐标系（单位、宽、长），便于写进报告。"""
        return {"unit": self.unit, "width": self.width_ft, "length": self.length_ft}

    @property
    def standard_keypoints(self) -> dict[str, CourtPoint]:
        """四个角点（用于标定时对应画面四角）。"""
        return {
            "top_left": CourtPoint(0.0, 0.0),
            "top_right": CourtPoint(self.width_ft, 0.0),
            "bottom_right": CourtPoint(self.width_ft, self.length_ft),
            "bottom_left": CourtPoint(0.0, self.length_ft),
        }

    @property
    def outer_boundary_polygon(self) -> CourtPolygon:
        """最外层边界多边形（整个球场外框）。"""
        points = self.standard_keypoints
        return CourtPolygon(
            "outer_boundary",
            (
                points["top_left"],
                points["top_right"],
                points["bottom_right"],
                points["bottom_left"],
            ),
        )

    @property
    def bounds(self) -> CourtZone:
        """整个球场的矩形边界区域。"""
        return CourtZone("court_bounds", 0.0, self.width_ft, 0.0, self.length_ft)

    @property
    def net_line(self) -> CourtLine:
        """球网线（横跨整个宽度，位于 y=22）。"""
        return CourtLine("net", CourtPoint(0.0, self.net_y_ft), CourtPoint(self.width_ft, self.net_y_ft))

    @property
    def near_kitchen_line(self) -> CourtLine:
        """近端厨房线（横贯，位于 y=15）。"""
        y = self.near_kitchen_y_ft
        return CourtLine("near_kitchen_line", CourtPoint(0.0, y), CourtPoint(self.width_ft, y))

    @property
    def far_kitchen_line(self) -> CourtLine:
        """远端厨房线（横贯，位于 y=29）。"""
        y = self.far_kitchen_y_ft
        return CourtLine("far_kitchen_line", CourtPoint(0.0, y), CourtPoint(self.width_ft, y))

    @property
    def center_line_near(self) -> CourtLine:
        """近端中线：从球场中宽(x=10) 的近端底线，连接到近端厨房线。"""
        return CourtLine(
            "near_center_line",
            CourtPoint(self.width_ft / 2.0, 0.0),
            CourtPoint(self.width_ft / 2.0, self.near_kitchen_y_ft),
        )

    @property
    def center_line_far(self) -> CourtLine:
        """远端中线：从远端厨房线，连接到球场中宽(x=10) 的远端底线。"""
        return CourtLine(
            "far_center_line",
            CourtPoint(self.width_ft / 2.0, self.far_kitchen_y_ft),
            CourtPoint(self.width_ft / 2.0, self.length_ft),
        )

    @property
    def kitchen_zones(self) -> list[CourtZone]:
        """两个厨房区：近端(15~22)、远端(22~29)，各跨整个宽度。"""
        return [
            CourtZone("near_kitchen", 0.0, self.width_ft, self.near_kitchen_y_ft, self.net_y_ft),
            CourtZone("far_kitchen", 0.0, self.width_ft, self.net_y_ft, self.far_kitchen_y_ft),
        ]

    @property
    def service_zones(self) -> list[CourtZone]:
        """
        四个发球区（左右 × 远近）：
        - 近端左/右：y 从 0 到近端厨房线(15)；
        - 远端左/右：y 从远端厨房线(29) 到 44；
        中线 x=10 把左右分开。
        """
        mid_x = self.width_ft / 2.0
        return [
            CourtZone("near_left_service", 0.0, mid_x, 0.0, self.near_kitchen_y_ft),
            CourtZone("near_right_service", mid_x, self.width_ft, 0.0, self.near_kitchen_y_ft),
            CourtZone("far_left_service", 0.0, mid_x, self.far_kitchen_y_ft, self.length_ft),
            CourtZone("far_right_service", mid_x, self.width_ft, self.far_kitchen_y_ft, self.length_ft),
        ]

    @property
    def lines(self) -> list[CourtLine]:
        """标准球场的全部 9 条线（供投影/绘制/诊断使用）。"""
        return [
            CourtLine("near_baseline", CourtPoint(0.0, 0.0), CourtPoint(self.width_ft, 0.0)),
            CourtLine("far_baseline", CourtPoint(0.0, self.length_ft), CourtPoint(self.width_ft, self.length_ft)),
            CourtLine("left_sideline", CourtPoint(0.0, 0.0), CourtPoint(0.0, self.length_ft)),
            CourtLine("right_sideline", CourtPoint(self.width_ft, 0.0), CourtPoint(self.width_ft, self.length_ft)),
            self.net_line,
            self.near_kitchen_line,
            self.far_kitchen_line,
            self.center_line_near,
            self.center_line_far,
        ]

    @property
    def polygons(self) -> list[CourtPolygon]:
        """所有多边形：外框 + 两个厨房区 + 四个发球区。"""
        return [
            self.outer_boundary_polygon,
            *[zone.polygon for zone in self.kitchen_zones],
            *[zone.polygon for zone in self.service_zones],
        ]

    @property
    def overlay_fill_polygons(self) -> list[CourtPolygon]:
        """叠加绘制时要填充半透明的多边形（厨房区 + 发球区，不含外框）。"""
        return [zone.polygon for zone in self.kitchen_zones + self.service_zones]

    def is_in_bounds(self, x: float, y: float) -> bool:
        """判断 (x, y) 是否落在整个球场边界内。"""
        return self.bounds.contains(CourtPoint(x, y))

    def is_in_kitchen(self, x: float, y: float) -> bool:
        """判断 (x, y) 是否在某个厨房区（非截击区）内。"""
        point = CourtPoint(x, y)
        return any(zone.contains(point) for zone in self.kitchen_zones)

    def service_zone_for(self, x: float, y: float) -> str | None:
        """返回 (x, y) 所在的发球区名字（如 "near_left_service"）；不在任何发球区则返回 None。"""
        point = CourtPoint(x, y)
        for zone in self.service_zones:
            if zone.contains(point):
                return zone.name
        return None

    def zone_names_for(self, x: float, y: float) -> list[str]:
        """返回 (x, y) 命中的全部区域名（可能同时命中 边界 + 厨房区 + 发球区）。"""
        point = CourtPoint(x, y)
        zones = []
        if self.bounds.contains(point):
            zones.append(self.bounds.name)
        zones.extend(zone.name for zone in self.kitchen_zones if zone.contains(point))
        zones.extend(zone.name for zone in self.service_zones if zone.contains(point))
        return zones


# 兼容别名：StandardPickleballCourt 就是 PickleballCourtGeometry 的另一种写法。
StandardPickleballCourt = PickleballCourtGeometry


def standard_court() -> PickleballCourtGeometry:
    """返回一个默认的标准球场几何对象（工厂函数）。"""
    return PickleballCourtGeometry()
