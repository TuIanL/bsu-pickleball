"""标定质量诊断 —— 对 homography 和标定控制点做多维度质量评估。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.vision.courtvision_calibration_engine.court_geometry import standard_court
from app.vision.courtvision_calibration_engine.homography import (
    HomographyError,
    court_to_image,
    _transform_points,
)


@dataclass
class CalibrationDiagnosticResult:
    calibration_quality: str = "good"  # good | suspect | bad
    corner_reprojection_errors_px: list[float] = field(default_factory=list)
    corner_mean_error_px: float = 0.0
    corner_max_error_px: float = 0.0
    derived_points_within_frame: bool = True
    aspect_ratio_error: float = 0.0
    baseline_direction_valid: bool = True
    homography_condition_number: float = 0.0
    warnings: list[str] = field(default_factory=list)


class CalibrationDiagnostics:
    """对 homography + 标定控制点做多维度质量诊断。"""

    def __init__(
        self,
        homography: list[list[float]],
        image_points: list[tuple[float, float]],
        court_points: list[tuple[float, float]],
        frame_shape: tuple[int, int],
    ) -> None:
        self._H = np.asarray(homography, dtype=float)
        if self._H.shape != (3, 3):
            raise ValueError("homography must be 3x3")
        self._image_points = image_points
        self._court_points = court_points
        self._frame_width, self._frame_height = frame_shape
        self._court = standard_court()

    def diagnose(self) -> CalibrationDiagnosticResult:
        result = CalibrationDiagnosticResult()

        result.corner_reprojection_errors_px = self.compute_corner_reprojection_errors()
        if result.corner_reprojection_errors_px:
            result.corner_mean_error_px = float(np.mean(result.corner_reprojection_errors_px))
            result.corner_max_error_px = float(np.max(result.corner_reprojection_errors_px))

        result.derived_points_within_frame = self.check_derived_points()
        result.aspect_ratio_error = self.compute_aspect_ratio_error()
        result.baseline_direction_valid = self.check_baseline_direction()
        result.homography_condition_number = self.compute_homography_condition_number()

        result.calibration_quality, result.warnings = self.assess_quality(result)
        return result

    def compute_corner_reprojection_errors(self) -> list[float]:
        errors: list[float] = []
        try:
            inv_H = np.linalg.inv(self._H)
        except np.linalg.LinAlgError:
            return errors

        for img_pt, court_pt in zip(self._image_points, self._court_points, strict=False):
            try:
                projected = court_to_image(court_pt, inv_H)
                dx = float(img_pt[0]) - projected[0]
                dy = float(img_pt[1]) - projected[1]
                errors.append(float(np.sqrt(dx * dx + dy * dy)))
            except HomographyError:
                errors.append(float("nan"))
        return errors

    def check_derived_points(self) -> bool:
        derived: list[tuple[float, float]] = [
            (0.0, 22.0),
            (20.0, 22.0),
            (0.0, 15.0),
            (20.0, 15.0),
            (0.0, 29.0),
            (20.0, 29.0),
            (10.0, 15.0),
            (10.0, 29.0),
        ]
        try:
            inv_H = np.linalg.inv(self._H)
            projected = court_to_image(derived, inv_H)
        except (np.linalg.LinAlgError, HomographyError):
            return False

        in_frame = all(
            0 <= px <= self._frame_width and 0 <= py <= self._frame_height
            for px, py in projected if isinstance(projected, list)
        )
        if not in_frame:
            return False

        if isinstance(projected, list) and len(projected) >= 6:
            net_left_y = projected[0][1]
            net_right_y = projected[1][1]
            near_kitchen_left_y = projected[2][1]
            far_kitchen_left_y = projected[4][1]
            if not (near_kitchen_left_y != far_kitchen_left_y):
                return False

            net_between = (near_kitchen_left_y < net_left_y < far_kitchen_left_y) or (
                far_kitchen_left_y < net_left_y < near_kitchen_left_y
            )
            if not net_between:
                return False

        return True

    def compute_aspect_ratio_error(self) -> float:
        """用消影点法验证四角点是否可能是 20×44ft 矩形的透视投影。

        给定矩形四角图像坐标，计算两组对边的消影点。
        若矩形为直角，消影点方向应接近正交。
        返回正交偏差角度（度），0 表示完美正交。
        平行边（消影点在无穷远）按 0 处理（正投影视图）。
        """
        if len(self._image_points) < 4:
            return float("inf")

        pts = [(float(p[0]), float(p[1])) for p in self._image_points[:4]]
        tl, tr, br, bl = pts

        def _line_intersection(p1, p2, p3, p4):
            x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-10:
                return None
            px = ((x1*y2 - y1*x2) * (x3 - x4) - (x1 - x2) * (x3*y4 - y3*x4)) / denom
            py = ((x1*y2 - y1*x2) * (y3 - y4) - (y1 - y2) * (x3*y4 - y3*x4)) / denom
            return (px, py)

        vp1 = _line_intersection(tl, tr, bl, br)
        vp2 = _line_intersection(tl, bl, tr, br)

        if vp1 is None or vp2 is None:
            return 0.0

        dx1 = vp1[0] - (tl[0] + tr[0]) / 2
        dy1 = vp1[1] - (tl[1] + tr[1]) / 2
        dx2 = vp2[0] - (tl[0] + bl[0]) / 2
        dy2 = vp2[1] - (tl[1] + bl[1]) / 2

        mag1 = np.sqrt(dx1*dx1 + dy1*dy1)
        mag2 = np.sqrt(dx2*dx2 + dy2*dy2)
        if mag1 < 1e-6 or mag2 < 1e-6:
            return 0.0

        cos_angle = abs(dx1*dx2 + dy1*dy2) / (mag1 * mag2)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        ortho_deviation_deg = abs(90.0 - np.degrees(np.arccos(cos_angle)))
        return float(ortho_deviation_deg)

    def check_baseline_direction(self) -> bool:
        try:
            inv_H = np.linalg.inv(self._H)
            near_baseline = court_to_image([(10.0, 0.0)], inv_H)
            far_baseline = court_to_image([(10.0, 44.0)], inv_H)
        except (np.linalg.LinAlgError, HomographyError):
            return False

        if not isinstance(near_baseline, list) or not isinstance(far_baseline, list):
            return False

        near_y = near_baseline[0][1]
        far_y = far_baseline[0][1]
        return near_y > far_y

    def compute_homography_condition_number(self) -> float:
        try:
            return float(np.linalg.cond(self._H))
        except np.linalg.LinAlgError:
            return float("inf")

    def assess_quality(self, result: CalibrationDiagnosticResult) -> tuple[str, list[str]]:
        warnings: list[str] = []
        quality = "good"

        if result.corner_max_error_px > 10.0 or not result.derived_points_within_frame:
            quality = "suspect"
            warnings.append(
                "Corner reprojection error or derived point anomaly — "
                "may indicate poor calibration or swapped points"
            )
        elif result.corner_max_error_px > 5.0:
            quality = "suspect"
            warnings.append(
                f"Corner reprojection error {result.corner_max_error_px:.1f}px > 5.0px "
                f"— calibration may be imprecise"
            )

        if result.aspect_ratio_error > 20.0:
            if quality == "good":
                quality = "suspect"
            warnings.append(
                f"Vanishing point orthogonality deviation {result.aspect_ratio_error:.1f}° > 20° "
                f"— imaged quadrilateral may not be a rectangle under perspective"
            )

        if not result.baseline_direction_valid:
            if quality == "good":
                quality = "suspect"
            warnings.append(
                "Near/far baseline may be swapped — near court projects to top of image"
            )

        if result.homography_condition_number >= 50000:
            if quality == "good":
                quality = "suspect"
            warnings.append(
                f"Homography is ill-conditioned (cond={result.homography_condition_number:.0f}) "
                f"— calibration points may be near-collinear"
            )

        if quality == "good" and not warnings:
            quality = "good"

        return quality, warnings

    def write_artifact(self, output_path: Path, job_id: str) -> Path:
        result = self.diagnose()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "calibration-diagnostics.v1",
            "job_id": job_id,
            "calibration_quality": result.calibration_quality,
            "corner_reprojection_errors_px": result.corner_reprojection_errors_px,
            "corner_mean_error_px": result.corner_mean_error_px,
            "corner_max_error_px": result.corner_max_error_px,
            "derived_points_within_frame": result.derived_points_within_frame,
            "aspect_ratio_error": result.aspect_ratio_error,
            "baseline_direction_valid": result.baseline_direction_valid,
            "homography_condition_number": result.homography_condition_number,
            "warnings": result.warnings,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
