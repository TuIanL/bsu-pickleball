"""场地标定服务 —— 管理手工/半自动标定的创建、存储和图像→球场坐标投影。

"标定（calibration）"就是告诉系统：画面上的某几个像素点，对应球场上的哪个真实坐标。
有了这个对应关系（数学上叫"单应矩阵 homography"），就能把人在画面里的位置
换算成在球场上的位置。

本服务负责：
- 接收用户标定的关键点（图像点 ↔ 球场点），计算单应矩阵并保存；
- 提供"投影"接口：给定画面上的一个点，算出它在球场上的坐标；
- 生成标定预览图（把标准球场线画到视频帧上）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

from app.schemas.calibration import (
    CalibrationCreate,
    CalibrationKeypoint,
    CalibrationPreviewResponse,
    CalibrationQuality,
    CalibrationReadResponse,
    CalibrationResult,
    CourtCoordinateSystem,
    CourtPoint2D,
    HomographyMatrix,
    ImagePoint,
    ManualCalibrationResponse,
    ManualKeypointCalibrationRequest,
    ProjectionResult,
)
from app.services.storage_service import StorageService
from app.services.video_service import video_service

# 下面是"视觉引擎"里的标定相关工具：
# - PickleballCourtGeometry / standard_court：标准匹克球场地的几何定义
# - draw_court_overlay：把球场线画到图像上
# - compute_homography / image_to_court / project_point：单应矩阵的计算与投影
from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.courtvision_calibration_engine.court_overlay import draw_court_overlay
from app.vision.courtvision_calibration_engine.homography import compute_homography, image_to_court, project_point

# 内存中的标定结果缓存：calibration_id -> CalibrationResult
CALIBRATIONS: dict[str, CalibrationResult] = {}


class CalibrationService:
    """存储手工场地标定数据以及对应的单应矩阵。"""

    def __init__(self, storage: StorageService | None = None, court: PickleballCourtGeometry | None = None) -> None:
        self.storage = storage or StorageService()
        # court 是标准球场几何；不传就用全局默认标准场
        self.court = court or standard_court()

    def create_calibration(self, payload: CalibrationCreate) -> CalibrationResult:
        # 核心方法：根据一组"图像点 + 球场点"计算单应矩阵并保存。
        # 把每个关键点拆成"图像坐标列表"和"球场坐标列表"
        image_points = [(item.image.x, item.image.y) for item in payload.keypoints]
        court_points = [(item.court.x, item.court.y) for item in payload.keypoints]
        # 计算前向单应矩阵（图像 → 球场）
        matrix = compute_homography(image_points, court_points)
        # 求逆矩阵（球场 → 图像），用于在预览图上画球场线
        inverse_matrix = np.linalg.inv(matrix)
        # 评估标定质量（重投影误差）
        quality = self._quality(image_points, court_points, matrix)
        calibration_id = f"calib-{uuid4().hex[:10]}"
        result = CalibrationResult(
            id=calibration_id,
            video_id=payload.video_id,
            keypoints=payload.keypoints,
            # 矩阵用 .tolist() 转成普通 list 才能被 Pydantic/JSON 序列化
            homography=HomographyMatrix(values=matrix.tolist()),
            inverse_homography=HomographyMatrix(values=inverse_matrix.tolist()),
            court_coordinate_system=CourtCoordinateSystem(**self.court.coordinate_system),
            quality=quality,
            method=payload.method,
            created_at=datetime.now(UTC),
        )
        return self._save_calibration(result)

    def create_manual_calibration(self, payload: ManualKeypointCalibrationRequest) -> CalibrationResult:
        # 手工标定：用户直接在画面上点出几个场地角点（按名字命名，如 top_left）。
        # 把每个角点的"球场坐标"从标准场地几何里取出来，组成关键点列表。
        standard_keypoints = self.court.standard_keypoints
        keypoints: list[CalibrationKeypoint] = []

        for name, image_point in payload.image_points.as_named_points().items():
            court_point = standard_keypoints[name]
            keypoints.append(
                CalibrationKeypoint(
                    name=name,
                    image=ImagePoint(x=image_point[0], y=image_point[1]),
                    court=CourtPoint2D(x=court_point.x, y=court_point.y),
                )
            )

        return self.create_calibration(
            CalibrationCreate(
                video_id=payload.video_id,
                keypoints=keypoints,
                method="manual",  # 标记为手工方式
            )
        )

    def create_semi_automatic_calibration(self, payload: ManualKeypointCalibrationRequest) -> CalibrationResult:
        # 半自动标定：流程与手工基本相同，只是 method 标记为 "semi-automatic"。
        # （实际中"半自动"指系统先自动找角点、用户再微调，这里用户已给出点，逻辑一致。）
        standard_keypoints = self.court.standard_keypoints
        keypoints: list[CalibrationKeypoint] = []

        for name, image_point in payload.image_points.as_named_points().items():
            court_point = standard_keypoints[name]
            keypoints.append(
                CalibrationKeypoint(
                    name=name,
                    image=ImagePoint(x=image_point[0], y=image_point[1]),
                    court=CourtPoint2D(x=court_point.x, y=court_point.y),
                )
            )

        return self.create_calibration(
            CalibrationCreate(
                video_id=payload.video_id,
                keypoints=keypoints,
                method="semi-automatic",
            )
        )

    def get_calibration(self, calibration_id: str) -> CalibrationResult | None:
        # 取标定结果：先查内存缓存，再查磁盘。
        cached = CALIBRATIONS.get(calibration_id)
        if cached is not None:
            return cached

        path = self.storage.calibration_json_path(calibration_id)
        if not path.exists():
            return None

        result = CalibrationResult.model_validate(self.storage.read_json(path))
        CALIBRATIONS[calibration_id] = result
        return result

    def manual_response(self, calibration: CalibrationResult) -> ManualCalibrationResponse:
        # 构造"手工标定响应"：把单应矩阵（含逆）和球场坐标系、质量信息返回给前端。
        inverse = calibration.inverse_homography
        if inverse is None:
            # 逆矩阵缺失时现场算一个
            inverse = HomographyMatrix(
                values=np.linalg.inv(np.asarray(calibration.homography.values, dtype=float)).tolist()
            )

        return ManualCalibrationResponse(
            calibration_id=calibration.id,
            homography=calibration.homography.values,
            inverse_homography=inverse.values,
            court_coordinate_system=calibration.court_coordinate_system,
            quality=calibration.quality,
        )

    def read_response(self, calibration: CalibrationResult) -> CalibrationReadResponse:
        # 在 manual_response 基础上，补充 video_id / keypoints / created_at 等完整信息。
        response = self.manual_response(calibration)
        return CalibrationReadResponse(
            calibration_id=response.calibration_id,
            video_id=calibration.video_id,
            keypoints=calibration.keypoints,
            homography=response.homography,
            inverse_homography=response.inverse_homography,
            court_coordinate_system=response.court_coordinate_system,
            quality=response.quality,
            created_at=calibration.created_at,
        )

    def project(self, calibration_id: str, image_point: ImagePoint) -> ProjectionResult | None:
        # 投影接口：给定画面上的一个点，返回它在球场上的坐标。
        calibration = self.get_calibration(calibration_id)
        if calibration is None:
            return None

        x, y = project_point(calibration.homography.values, (image_point.x, image_point.y))
        return ProjectionResult(
            calibration_id=calibration_id,
            image_point=image_point,
            court_point={"x": x, "y": y},
        )

    def create_preview(self, calibration_id: str, frame_path: str | None = None) -> CalibrationPreviewResponse | None:
        # 生成标定预览图：把标准球场线叠加到某一帧画面上，保存成 png。
        calibration = self.get_calibration(calibration_id)
        if calibration is None:
            return None
        # 确保逆矩阵存在
        if calibration.inverse_homography is None:
            calibration.inverse_homography = HomographyMatrix(
                values=np.linalg.inv(np.asarray(calibration.homography.values, dtype=float)).tolist()
            )

        # 读取用于预览的帧（优先用 frame_path，否则从原视频抽一帧）
        frame = self._read_preview_frame(calibration, frame_path)
        if frame is None:
            raise ValueError("No usable frame was provided or available for this calibration")

        # 用逆矩阵把球场线画到帧上
        output = draw_court_overlay(frame, calibration.inverse_homography.values, self.court)
        path = self.storage.preview_image_path(calibration_id)

        # OpenCV 是生成预览图的必要依赖，缺失就明确报错
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise ValueError("OpenCV is required to generate calibration previews") from exc

        if not cv2.imwrite(str(path), output):
            raise ValueError("Failed to write calibration preview image")

        return CalibrationPreviewResponse(calibration_id=calibration_id, preview_image_path=str(path))

    def _save_calibration(self, result: CalibrationResult) -> CalibrationResult:
        # 内部：写入内存缓存 + 落盘 JSON
        CALIBRATIONS[result.id] = result
        self.storage.write_json(
            self.storage.calibration_json_path(result.id),
            result.model_dump(mode="json"),
        )
        return result

    def _quality(
        self,
        image_points: list[tuple[float, float]],
        court_points: list[tuple[float, float]],
        homography: np.ndarray,
    ) -> CalibrationQuality:
        # 评估标定质量：用算出的矩阵把图像点"投影回球场"，
        # 看它和真实球场点差多远（重投影误差，单位与球场坐标一致）。
        projected = image_to_court(image_points, homography)
        projected_points = projected if isinstance(projected, list) else [projected]
        errors = [
            float(np.linalg.norm(np.asarray(projected_point, dtype=float) - np.asarray(court_point, dtype=float)))
            for projected_point, court_point in zip(projected_points, court_points, strict=False)
        ]
        reprojection_error = float(np.mean(errors)) if errors else 0.0
        # 平均误差 <= 1.0（球场坐标单位）算 ok，否则 warning
        status = "ok" if reprojection_error <= 1.0 else "warning"
        return CalibrationQuality(reprojection_error=reprojection_error, status=status)

    def _read_preview_frame(self, calibration: CalibrationResult, frame_path: str | None):
        # 内部：取得用于画预览图的那一帧画面。
        # 优先用调用方传入的 frame_path；否则从标定关联的视频里读第一帧。
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise ValueError("OpenCV is required to generate calibration previews") from exc

        if frame_path:
            path = Path(frame_path)
            if not path.exists():
                raise ValueError("Provided frame_path does not exist")
            frame = cv2.imread(str(path))
            if frame is None:
                raise ValueError("Provided frame_path could not be read as an image")
            return frame

        if calibration.video_id:
            video = video_service.get_video(calibration.video_id)
            if video is not None and Path(video.path).exists():
                capture = cv2.VideoCapture(video.path)
                try:
                    ok, frame = capture.read()
                finally:
                    capture.release()
                if ok and frame is not None:
                    return frame

        return None


# 全局单例
calibration_service = CalibrationService()
