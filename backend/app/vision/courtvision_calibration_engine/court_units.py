"""
匹克球场单位转换工具（court_units）—— 英尺 ↔ 米换算及标准球场尺寸常量。

匹克球球场的标准尺寸通常用英尺表示（宽 20 英尺、长 44 英尺），
但有些场景想要米。这个文件集中管理"换算系数"和"标准尺寸常量"，
并提供点坐标、单值、整场尺寸的单位转换函数。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# dataclass：数据类（详见 schemas.py 注释）。
from dataclasses import dataclass


# 英尺↔米 的换算系数（1 英尺 = 0.3048 米）。
FEET_TO_METERS = 0.3048
METERS_TO_FEET = 1.0 / FEET_TO_METERS

# 标准匹克球场尺寸（英尺）。
PICKLEBALL_COURT_WIDTH_FT = 20.0
PICKLEBALL_COURT_LENGTH_FT = 44.0
# 换算成米。
PICKLEBALL_COURT_WIDTH_M = PICKLEBALL_COURT_WIDTH_FT * FEET_TO_METERS
PICKLEBALL_COURT_LENGTH_M = PICKLEBALL_COURT_LENGTH_FT * FEET_TO_METERS
# 厨房区（非截击区）深度：标准 7 英尺。
PICKLEBALL_KITCHEN_DEPTH_FT = 7.0
PICKLEBALL_KITCHEN_DEPTH_M = PICKLEBALL_KITCHEN_DEPTH_FT * FEET_TO_METERS


@dataclass(frozen=True)
class CourtUnitMetadata:
    """
    球场单位元信息：把"当前用的是什么单位、宽长各多少（米/英尺）"打包成一个对象。

    `as_dict()` 方便把它写进 JSON / 报告里。
    """
    court_unit: str = "m"                      # 当前使用的单位："m" 或 "ft"
    width_m: float = PICKLEBALL_COURT_WIDTH_M  # 宽（米）
    length_m: float = PICKLEBALL_COURT_LENGTH_M  # 长（米）
    width_ft: float = PICKLEBALL_COURT_WIDTH_FT  # 宽（英尺）
    length_ft: float = PICKLEBALL_COURT_LENGTH_FT  # 长（英尺）
    feet_to_meters: float = FEET_TO_METERS     # 换算系数

    def as_dict(self) -> dict[str, float | str]:
        """转成普通 dict（米保留 4 位小数，方便序列化）。"""
        return {
            "court_unit": self.court_unit,
            "width_m": round(self.width_m, 4),
            "length_m": round(self.length_m, 4),
            "width_ft": self.width_ft,
            "length_ft": self.length_ft,
            "feet_to_meters": self.feet_to_meters,
        }


def feet_to_meters(value: float) -> float:
    """英尺 → 米。"""
    return float(value) * FEET_TO_METERS


def meters_to_feet(value: float) -> float:
    """米 → 英尺。"""
    return float(value) * METERS_TO_FEET


def point_feet_to_meters(point: list[float] | tuple[float, float]) -> list[float]:
    """把一个 (x, y) 点从英尺坐标转成米坐标。"""
    return [feet_to_meters(point[0]), feet_to_meters(point[1])]


def point_meters_to_feet(point: list[float] | tuple[float, float]) -> list[float]:
    """把一个 (x, y) 点从米坐标转成英尺坐标。"""
    return [meters_to_feet(point[0]), meters_to_feet(point[1])]


def standard_metric_court_metadata() -> CourtUnitMetadata:
    """返回一份"以米为单位"的标准球场元信息。"""
    return CourtUnitMetadata()


def normalize_court_unit(unit: str | None) -> str | None:
    """
    把各种写法统一成规范单位字符串。

    例如 "Meter" / "metres" → "m"；"FT" / "Feet" → "ft"；
    不认识的单位 → None（表示无效）。
    """
    if unit is None:
        return None
    normalized = unit.strip().lower()
    if normalized in {"m", "meter", "meters", "metre", "metres"}:
        return "m"
    if normalized in {"ft", "foot", "feet"}:
        return "ft"
    return None


def court_dimensions_for_unit(unit: str | None) -> tuple[float, float] | None:
    """根据单位返回 (宽, 长)。"m" 返回米，"ft" 返回英尺，其它返回 None。"""
    normalized = normalize_court_unit(unit)
    if normalized == "m":
        return PICKLEBALL_COURT_WIDTH_M, PICKLEBALL_COURT_LENGTH_M
    if normalized == "ft":
        return PICKLEBALL_COURT_WIDTH_FT, PICKLEBALL_COURT_LENGTH_FT
    return None


def feet_value_for_unit(value_ft: float, unit: str | None) -> float | None:
    """
    把一个"以英尺给出的数值"转换成目标单位下的值。

    - 目标 "m" → 转成米；
    - 目标 "ft" → 原样返回；
    - 无效单位 → None。
    """
    normalized = normalize_court_unit(unit)
    if normalized == "m":
        return feet_to_meters(value_ft)
    if normalized == "ft":
        return float(value_ft)
    return None
