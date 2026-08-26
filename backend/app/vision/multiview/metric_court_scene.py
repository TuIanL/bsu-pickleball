"""Deterministic geometry helpers for the metric court scene contract."""

from __future__ import annotations

from math import isfinite

from app.schemas.metric_court_scene import (
    NetProfile,
    NetProfileControlPoint,
    ScenePoint3D,
)

COURT_WIDTH_FT = 20.0
COURT_LENGTH_FT = 44.0
NET_Y_FT = 22.0
NET_ENDPOINT_HEIGHT_FT = 36.0 / 12.0
NET_CENTER_HEIGHT_FT = 34.0 / 12.0


def standard_net_control_points(
    *,
    width_ft: float = COURT_WIDTH_FT,
    net_y_ft: float = NET_Y_FT,
) -> list[NetProfileControlPoint]:
    """Return the three minimum standard net-top controls in court feet."""
    center_x = width_ft / 2.0
    points = (
        ("left", 0.0, NET_ENDPOINT_HEIGHT_FT),
        ("center", center_x, NET_CENTER_HEIGHT_FT),
        ("right", width_ft, NET_ENDPOINT_HEIGHT_FT),
    )
    return [
        NetProfileControlPoint(
            id=point_id,
            world=ScenePoint3D(x=x, y=net_y_ft, z=z),
            provenance="manual",
            confirmed=False,
        )
        for point_id, x, z in points
    ]


def sample_net_top_profile(
    control_points: list[NetProfileControlPoint],
    *,
    sample_count: int = 21,
) -> list[ScenePoint3D]:
    """Sample the endpoint/center net sag as a quadratic profile.

    Extra measured controls are linearly interpolated in x.  With exactly
    three controls, a quadratic polynomial is fit through the left, center,
    and right heights so the known center height remains exact.
    """
    if sample_count < 2:
        raise ValueError("sample_count must be at least 2")
    controls = sorted(control_points, key=lambda point: point.world.x)
    if len(controls) < 2:
        raise ValueError("at least two net controls are required")
    if any(not isfinite(point.world.x) or not isfinite(point.world.z) for point in controls):
        raise ValueError("net control coordinates must be finite")

    left = controls[0].world.x
    right = controls[-1].world.x
    if right <= left:
        raise ValueError("net control x coordinates must increase")

    use_quadratic = len(controls) == 3

    def height_at(x: float) -> float:
        if use_quadratic:
            result = 0.0
            for index, control in enumerate(controls):
                basis = 1.0
                for other_index, other in enumerate(controls):
                    if index == other_index:
                        continue
                    basis *= (x - other.world.x) / (control.world.x - other.world.x)
                result += control.world.z * basis
            return result
        for first, second in zip(controls, controls[1:]):
            x1, x2 = first.world.x, second.world.x
            if x1 <= x <= x2:
                ratio = (x - x1) / max(x2 - x1, 1e-9)
                return first.world.z + ratio * (second.world.z - first.world.z)
        return controls[0].world.z if x < left else controls[-1].world.z

    y = controls[0].world.y
    return [
        ScenePoint3D(
            x=left + (right - left) * index / (sample_count - 1),
            y=y,
            z=height_at(left + (right - left) * index / (sample_count - 1)),
        )
        for index in range(sample_count)
    ]


def build_standard_net_profile(*, width_ft: float = COURT_WIDTH_FT, net_y_ft: float = NET_Y_FT) -> NetProfile:
    controls = standard_net_control_points(width_ft=width_ft, net_y_ft=net_y_ft)
    return NetProfile(
        profile_type="standard",
        height_source="standard",
        coordinate_units="feet",
        control_points=controls,
        sampled_top_profile=sample_net_top_profile(controls),
        post_world_points=[
            ScenePoint3D(x=-1.0, y=net_y_ft, z=NET_ENDPOINT_HEIGHT_FT),
            ScenePoint3D(x=width_ft + 1.0, y=net_y_ft, z=NET_ENDPOINT_HEIGHT_FT),
        ],
    )
