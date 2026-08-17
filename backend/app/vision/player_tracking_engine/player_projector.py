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
        drop_outside_tracking: bool = True,
    ) -> None:
        # x_bounds/y_bounds：向后兼容保留（已弃用，由 court.tracking_bounds 替代）。
        # drop_outside_tracking：是否丢弃超出 tracking_bounds 的点（取代 include_invalid）。
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.drop_outside_tracking = drop_outside_tracking
        self.footpoint_estimator = footpoint_estimator or FootpointEstimator()

    def project(
        self,
        tracks: Sequence[Track],
        homography: Sequence[Sequence[float]],
        frame_index: int,
        timestamp: float,
        footpoints: Mapping[int, FootpointEstimate] | None = None,
        frame_shape: tuple[int, int] | None = None,
    ) -> list[PlayerFramePosition]:
        # 把一帧内的多条轨迹投影成 PlayerFramePosition（含图像脚点、球场坐标、有效性）。
        positions: list[PlayerFramePosition] = []

        for track in tracks:
            # 优先使用外部传入的脚点估计；否则用默认估计器从 track 推算脚点。
            footpoint = footpoints.get(track.track_id) if footpoints is not None else None
            footpoint = footpoint or self.footpoint_estimator.estimate(track, frame_shape=frame_shape)
            # 用单应矩阵把图像脚点映射到球场坐标（英尺）。
            court_x, court_y = image_to_court(footpoint.image_footpoint, homography)
            court_position = [float(court_x), float(court_y)]

            # 使用状态分类取代简单的 in_bounds 检查
            status = self._classify_projection(court_position)
            is_inside_court = status == "inside_court"
            is_inside_tracking = status != "outside_tracking_area"

            # 只有超出 tracking_bounds 且 drop_outside_tracking=True 时才丢弃
            if status == "outside_tracking_area" and self.drop_outside_tracking:
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
                    valid=is_inside_court,
                    validity="valid" if is_inside_court else "invalid",
                    footpoint_method=footpoint.method,
                    is_inside_court=is_inside_court,
                    is_inside_tracking_area=is_inside_tracking,
                    projection_status=status,
                    projection_confidence=footpoint.confidence,
                    footpoint_metadata=footpoint.metadata,
                )
            )

        return positions

    def _classify_projection(self, court_position: list[float]) -> str:
        """分类投影点的空间状态。"""
        return classify_projection_status(court_position)


def classify_projection_status(court_position: Sequence[float]) -> str:
    """共享纯函数：court position → 空间状态分类（inside_court / outside_court_visible / outside_tracking_area）。

    pre-association 与正式 `PlayerProjector` 共用本函数，MUST NOT 各写一套，
    防"pre-association 说投影有效、正式 projector 说 outside_tracking_area → drop"的前后不一致。
    """
    from app.vision.courtvision_calibration_engine.court_geometry import standard_court

    court = standard_court()
    x, y = float(court_position[0]), float(court_position[1])
    if court.is_in_court_bounds(x, y):
        return "inside_court"
    if court.is_in_tracking_bounds(x, y):
        return "outside_court_visible"
    return "outside_tracking_area"


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
