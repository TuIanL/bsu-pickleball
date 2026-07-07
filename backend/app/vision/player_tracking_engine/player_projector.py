"""球员投影器 —— 将跟踪球员的脚点从图像像素坐标投影到球场英尺坐标。"""

from __future__ import annotations

# Mapping/Sequence：用于类型标注（已投影点映射、可迭代轨迹）。
from collections.abc import Mapping, Sequence

# 投影相关数据结构：
# FootpointEstimate 脚点估计；ImageTrackPoint 图像坐标轨迹点；
# PlayerFramePosition 单帧球员位置（含球场坐标与有效性）；ProjectedCourtPoint2D 投影后二维点；
# ProjectedTrackPoint 投影后轨迹点；Track 跟踪框。
from app.schemas.tracking import (
    FootpointEstimate,
    ImageTrackPoint,
    PlayerFramePosition,
    ProjectedCourtPoint2D,
    ProjectedTrackPoint,
    Track,
)
# 单应性变换工具：image_to_court（脚点→球场坐标）、project_point（单点投影）。
from app.vision.courtvision_calibration_engine.homography import image_to_court, project_point
# 脚点估计器（默认用检测框底边中点）。
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator


class PlayerProjector:
    """Project tracked player footpoints from image pixels into court feet."""

    def __init__(
        self,
        x_bounds: tuple[float, float] = (-2.0, 22.0),
        y_bounds: tuple[float, float] = (-2.0, 46.0),
        include_invalid: bool = False,
        footpoint_estimator: FootpointEstimator | None = None,
    ) -> None:
        # x_bounds/y_bounds：球场坐标的合法范围（默认允许略超出边界，便于容纳边缘球员）；
        # include_invalid：是否保留投影后越界的点；footpoint_estimator：可注入自定义脚点估计器。
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.include_invalid = include_invalid
        self.footpoint_estimator = footpoint_estimator or FootpointEstimator()

    def project(
        self,
        tracks: Sequence[Track],
        homography: Sequence[Sequence[float]],
        frame_index: int,
        timestamp: float,
        footpoints: Mapping[int, FootpointEstimate] | None = None,
    ) -> list[PlayerFramePosition]:
        # 把一帧内的多条轨迹投影成 PlayerFramePosition（含图像脚点、球场坐标、有效性）。
        positions: list[PlayerFramePosition] = []

        for track in tracks:
            # 优先使用外部传入的脚点估计；否则用默认估计器从 track 推算脚点。
            footpoint = footpoints.get(track.track_id) if footpoints is not None else None
            footpoint = footpoint or self.footpoint_estimator.estimate(track)
            # 用单应矩阵把图像脚点映射到球场坐标（英尺）。
            court_x, court_y = image_to_court(footpoint.image_footpoint, homography)
            court_position = [float(court_x), float(court_y)]
            valid = self._in_bounds(court_position)
            # 越界且不允许保留则跳过。
            if not valid and not self.include_invalid:
                continue
            positions.append(
                PlayerFramePosition(
                    frame_index=frame_index,
                    timestamp=timestamp,
                    track_id=track.track_id,
                    bbox=track.bbox,
                    image_footpoint=footpoint.image_footpoint,
                    court_position=court_position,
                    confidence=track.confidence,
                    valid=valid,
                    validity="valid" if valid else "invalid",
                    footpoint_method=footpoint.method,
                )
            )

        return positions

    def _in_bounds(self, court_position: list[float]) -> bool:
        # 判断球场坐标是否落在允许范围内。
        x, y = court_position
        return self.x_bounds[0] <= x <= self.x_bounds[1] and self.y_bounds[0] <= y <= self.y_bounds[1]


def project_track_points(
    track_points: list[ImageTrackPoint],
    homography: list[list[float]],
) -> list[ProjectedTrackPoint]:
    # 批量把图像坐标轨迹点投影成场地球场坐标轨迹点（保留原有点位元数据）。
    projected: list[ProjectedTrackPoint] = []

    for point in track_points:
        x, y = project_point(homography, (point.image_point.x, point.image_point.y))
        projected.append(
            ProjectedTrackPoint(
                **point.model_dump(),
                court_point=ProjectedCourtPoint2D(x=x, y=y),
            )
        )

    return projected
