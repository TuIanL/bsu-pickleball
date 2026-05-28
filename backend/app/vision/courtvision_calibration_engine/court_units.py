"""匹克球场单位转换工具 —— 英尺 ↔ 米换算及标准球场尺寸常量。"""

from __future__ import annotations

from dataclasses import dataclass


FEET_TO_METERS = 0.3048
METERS_TO_FEET = 1.0 / FEET_TO_METERS

PICKLEBALL_COURT_WIDTH_FT = 20.0
PICKLEBALL_COURT_LENGTH_FT = 44.0
PICKLEBALL_COURT_WIDTH_M = PICKLEBALL_COURT_WIDTH_FT * FEET_TO_METERS
PICKLEBALL_COURT_LENGTH_M = PICKLEBALL_COURT_LENGTH_FT * FEET_TO_METERS
PICKLEBALL_KITCHEN_DEPTH_FT = 7.0
PICKLEBALL_KITCHEN_DEPTH_M = PICKLEBALL_KITCHEN_DEPTH_FT * FEET_TO_METERS


@dataclass(frozen=True)
class CourtUnitMetadata:
    court_unit: str = "m"
    width_m: float = PICKLEBALL_COURT_WIDTH_M
    length_m: float = PICKLEBALL_COURT_LENGTH_M
    width_ft: float = PICKLEBALL_COURT_WIDTH_FT
    length_ft: float = PICKLEBALL_COURT_LENGTH_FT
    feet_to_meters: float = FEET_TO_METERS

    def as_dict(self) -> dict[str, float | str]:
        return {
            "court_unit": self.court_unit,
            "width_m": round(self.width_m, 4),
            "length_m": round(self.length_m, 4),
            "width_ft": self.width_ft,
            "length_ft": self.length_ft,
            "feet_to_meters": self.feet_to_meters,
        }


def feet_to_meters(value: float) -> float:
    return float(value) * FEET_TO_METERS


def meters_to_feet(value: float) -> float:
    return float(value) * METERS_TO_FEET


def point_feet_to_meters(point: list[float] | tuple[float, float]) -> list[float]:
    return [feet_to_meters(point[0]), feet_to_meters(point[1])]


def point_meters_to_feet(point: list[float] | tuple[float, float]) -> list[float]:
    return [meters_to_feet(point[0]), meters_to_feet(point[1])]


def standard_metric_court_metadata() -> CourtUnitMetadata:
    return CourtUnitMetadata()


def normalize_court_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    normalized = unit.strip().lower()
    if normalized in {"m", "meter", "meters", "metre", "metres"}:
        return "m"
    if normalized in {"ft", "foot", "feet"}:
        return "ft"
    return None


def court_dimensions_for_unit(unit: str | None) -> tuple[float, float] | None:
    normalized = normalize_court_unit(unit)
    if normalized == "m":
        return PICKLEBALL_COURT_WIDTH_M, PICKLEBALL_COURT_LENGTH_M
    if normalized == "ft":
        return PICKLEBALL_COURT_WIDTH_FT, PICKLEBALL_COURT_LENGTH_FT
    return None


def feet_value_for_unit(value_ft: float, unit: str | None) -> float | None:
    normalized = normalize_court_unit(unit)
    if normalized == "m":
        return feet_to_meters(value_ft)
    if normalized == "ft":
        return float(value_ft)
    return None
