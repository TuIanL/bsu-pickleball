from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CourtPoint:
    x: float
    y: float


@dataclass(frozen=True)
class CourtLine:
    name: str
    start: CourtPoint
    end: CourtPoint


@dataclass(frozen=True)
class CourtZone:
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def contains(self, point: CourtPoint) -> bool:
        return self.x_min <= point.x <= self.x_max and self.y_min <= point.y <= self.y_max


@dataclass(frozen=True)
class StandardPickleballCourt:
    """Standard pickleball court geometry in feet.

    Coordinate convention:
    - x runs left-to-right from 0 to 20 ft
    - y runs near baseline-to-far baseline from 0 to 44 ft
    - net is y = 22 ft
    """

    width_ft: float = 20.0
    length_ft: float = 44.0
    net_y_ft: float = 22.0
    kitchen_depth_ft: float = 7.0

    @property
    def near_kitchen_y_ft(self) -> float:
        return self.net_y_ft - self.kitchen_depth_ft

    @property
    def far_kitchen_y_ft(self) -> float:
        return self.net_y_ft + self.kitchen_depth_ft

    @property
    def bounds(self) -> CourtZone:
        return CourtZone("court_bounds", 0.0, self.width_ft, 0.0, self.length_ft)

    @property
    def net_line(self) -> CourtLine:
        return CourtLine("net", CourtPoint(0.0, self.net_y_ft), CourtPoint(self.width_ft, self.net_y_ft))

    @property
    def near_kitchen_line(self) -> CourtLine:
        y = self.near_kitchen_y_ft
        return CourtLine("near_kitchen_line", CourtPoint(0.0, y), CourtPoint(self.width_ft, y))

    @property
    def far_kitchen_line(self) -> CourtLine:
        y = self.far_kitchen_y_ft
        return CourtLine("far_kitchen_line", CourtPoint(0.0, y), CourtPoint(self.width_ft, y))

    @property
    def center_line_near(self) -> CourtLine:
        return CourtLine(
            "near_center_line",
            CourtPoint(self.width_ft / 2.0, 0.0),
            CourtPoint(self.width_ft / 2.0, self.near_kitchen_y_ft),
        )

    @property
    def center_line_far(self) -> CourtLine:
        return CourtLine(
            "far_center_line",
            CourtPoint(self.width_ft / 2.0, self.far_kitchen_y_ft),
            CourtPoint(self.width_ft / 2.0, self.length_ft),
        )

    @property
    def kitchen_zones(self) -> list[CourtZone]:
        return [
            CourtZone("near_kitchen", 0.0, self.width_ft, self.near_kitchen_y_ft, self.net_y_ft),
            CourtZone("far_kitchen", 0.0, self.width_ft, self.net_y_ft, self.far_kitchen_y_ft),
        ]

    @property
    def service_zones(self) -> list[CourtZone]:
        mid_x = self.width_ft / 2.0
        return [
            CourtZone("near_left_service", 0.0, mid_x, 0.0, self.near_kitchen_y_ft),
            CourtZone("near_right_service", mid_x, self.width_ft, 0.0, self.near_kitchen_y_ft),
            CourtZone("far_left_service", 0.0, mid_x, self.far_kitchen_y_ft, self.length_ft),
            CourtZone("far_right_service", mid_x, self.width_ft, self.far_kitchen_y_ft, self.length_ft),
        ]

    @property
    def lines(self) -> list[CourtLine]:
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

    def is_in_bounds(self, x: float, y: float) -> bool:
        return self.bounds.contains(CourtPoint(x, y))

    def is_in_kitchen(self, x: float, y: float) -> bool:
        point = CourtPoint(x, y)
        return any(zone.contains(point) for zone in self.kitchen_zones)

    def service_zone_for(self, x: float, y: float) -> str | None:
        point = CourtPoint(x, y)
        for zone in self.service_zones:
            if zone.contains(point):
                return zone.name
        return None

    def zone_names_for(self, x: float, y: float) -> list[str]:
        point = CourtPoint(x, y)
        zones = []
        if self.bounds.contains(point):
            zones.append(self.bounds.name)
        zones.extend(zone.name for zone in self.kitchen_zones if zone.contains(point))
        zones.extend(zone.name for zone in self.service_zones if zone.contains(point))
        return zones


def standard_court() -> StandardPickleballCourt:
    return StandardPickleballCourt()
