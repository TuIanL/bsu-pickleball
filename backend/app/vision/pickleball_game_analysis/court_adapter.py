"""Court coordinate adapter for ball image points."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.courtvision_calibration_engine.homography import HomographyError, image_to_court
from app.vision.pickleball_game_analysis.schemas import Point2D, clean_point, coordinate_system_metadata


@dataclass(frozen=True)
class CourtProjection:
    """
    一次"图像坐标 → 球场坐标"投影的结果。

      - court_xy：投影得到的球场坐标（英尺）；失败则为 None；
      - in_bounds：该坐标是否在球场界内（投影失败时 None）；
      - detail：状态说明（projected / missing_homography / invalid_homography / ...）。
    """

    court_xy: Point2D | None
    in_bounds: bool | None
    detail: str


class BallCourtAdapter:
    """把球的图像坐标投影到本项目的"英尺制球场坐标"。"""

    def __init__(self, court: PickleballCourtGeometry | None = None) -> None:
        # 若无传入球场几何，则使用标准匹克球场
        self.court = court or standard_court()

    @property
    def coordinate_system(self) -> dict[str, object]:
        """返回坐标系统说明（图像=像素，球场=英尺，含宽长）。"""
        return coordinate_system_metadata(self.court.width_ft, self.court.length_ft)

    def project(
        self,
        image_xy: Sequence[float] | None,
        homography: Sequence[Sequence[float]] | None,
    ) -> CourtProjection:
        """
        把一个图像坐标点投影到球场坐标。

        参数:
            image_xy:  图像坐标 (x, y)，可空；
            homography: 图像→球场的单应变换矩阵（3x3），可空。

        返回 CourtProjection。任何缺失/非法输入都会安全返回 court_xy=None，并给出原因：
            - missing_image_point：没有图像点；
            - missing_homography：没有单应矩阵；
            - invalid_homography：投影计算抛错（矩阵坏）；
            - invalid_court_point：投影结果无效（出现 nan/inf）；
            - projected：成功投影。
        """
        point = clean_point(image_xy)
        if point is None:
            return CourtProjection(court_xy=None, in_bounds=None, detail="missing_image_point")
        if homography is None:
            return CourtProjection(court_xy=None, in_bounds=None, detail="missing_homography")

        try:
            court_x, court_y = image_to_court(point, homography)
            court_xy = clean_point((court_x, court_y))
        except (HomographyError, ValueError, TypeError):
            return CourtProjection(court_xy=None, in_bounds=None, detail="invalid_homography")

        if court_xy is None:
            return CourtProjection(court_xy=None, in_bounds=None, detail="invalid_court_point")
        in_bounds = self.court.is_in_bounds(court_xy[0], court_xy[1])
        return CourtProjection(court_xy=court_xy, in_bounds=in_bounds, detail="projected")
