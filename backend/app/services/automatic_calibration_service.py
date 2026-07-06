"""自动标定服务 —— 基于场地边线分割模型生成半自动标定建议。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from app.core.config import Settings, get_settings
from app.schemas.calibration import (
    AutomaticCalibrationFrame,
    AutomaticCalibrationKeypoints,
    AutomaticCalibrationMaskDiagnostics,
    AutomaticCalibrationRequest,
    AutomaticCalibrationResponse,
    CalibrationQuality,
    ManualImageKeypoints,
    ManualKeypointCalibrationRequest,
    SemiAutomaticCalibrationAcceptRequest,
)
from app.services.calibration_service import CalibrationService
from app.services.storage_service import StorageService
from app.services.video_service import VideoService
from app.vision.courtvision_calibration_engine.court_line_segmentation import (
    CourtLineSegmentationResult,
    CourtLineSegmentationUnavailable,
    CourtLineSegmenter,
)
from app.vision.courtvision_calibration_engine.court_overlay import draw_court_overlay
from app.vision.courtvision_calibration_engine.homography import compute_homography
from app.vision.courtvision_calibration_engine.mask_to_keypoints import (
    MaskGeometryError,
    MaskToKeypointsResult,
    mask_to_court_keypoints,
)


@dataclass(frozen=True)
class ExtractedFrame:
    frame: np.ndarray
    frame_index: int
    timestamp_seconds: float
    width: int
    height: int


class AutomaticCalibrationService:
    def __init__(
        self,
        video_service: VideoService | None = None,
        calibration_service: CalibrationService | None = None,
        storage: StorageService | None = None,
        settings: Settings | None = None,
        segmenter: CourtLineSegmenter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.video_service = video_service or VideoService()
        self.calibration_service = calibration_service or CalibrationService()
        self.storage = storage or StorageService(self.settings)
        self.segmenter = segmenter or CourtLineSegmenter(
            model_path=self.settings.court_line_model_path,
            confidence=self.settings.court_line_confidence,
            device=self.settings.court_line_device,
        )

    def suggest(self, payload: AutomaticCalibrationRequest) -> AutomaticCalibrationResponse:
        video = self.video_service.get_video(payload.video_id)
        if video is None:
            return self._unavailable("Uploaded video not found", video_id=payload.video_id)

        try:
            extracted = self._extract_frame(video.path, payload)
        except ValueError as exc:
            return self._unavailable(str(exc), video_id=payload.video_id)

        selected_frame = AutomaticCalibrationFrame(
            video_id=payload.video_id,
            frame_index=extracted.frame_index,
            timestamp_seconds=extracted.timestamp_seconds,
            width=extracted.width,
            height=extracted.height,
        )

        try:
            segmentation = self.segmenter.segment(extracted.frame)
        except CourtLineSegmentationUnavailable as exc:
            return AutomaticCalibrationResponse(
                status="unavailable",
                detail=str(exc),
                selected_frame=selected_frame,
                mask=AutomaticCalibrationMaskDiagnostics(
                    model_configured=self.segmenter.configured,
                    model_path=self.settings.court_line_model_path,
                    detail=str(exc),
                ),
            )

        try:
            geometry = mask_to_court_keypoints(
                segmentation.mask,
                min_area_ratio=self.settings.court_line_geometry_min_area_ratio,
            )
            calibration_quality = self._quality_for_keypoints(geometry.keypoints)
        except (MaskGeometryError, ValueError) as exc:
            preview_url = self._write_preview(
                extracted.frame,
                segmentation=segmentation,
                geometry=None,
                suggestion_id=f"auto-calib-{uuid4().hex[:10]}",
            )
            return AutomaticCalibrationResponse(
                status="rejected",
                detail=str(exc),
                suggestion_id=None,
                selected_frame=selected_frame,
                confidence=segmentation.confidence,
                mask=AutomaticCalibrationMaskDiagnostics(
                    model_configured=True,
                    model_path=segmentation.model_path,
                    confidence=segmentation.confidence,
                    mask_area_ratio=float(np.count_nonzero(segmentation.mask)) / float(segmentation.mask.size),
                    line_count=0,
                    detail="Court-line mask was produced but geometry validation failed",
                ),
                preview_image_url=preview_url,
            )

        suggestion_id = f"auto-calib-{uuid4().hex[:10]}"

        from app.vision.courtvision_calibration_engine.reference_line_support import (
            build_confidence_breakdown,
            build_reference_diagnostics,
            compute_reference_line_support,
            DEFAULT_REFERENCE_REJECT_THRESHOLD,
        )

        reference_result = compute_reference_line_support(
            segmentation.mask,
            geometry.keypoints,
        )
        reference_diag = build_reference_diagnostics(reference_result)

        # 组合置信度：seg(0.3) + geo(0.3) + ref(0.4)
        combined_confidence = (
            0.3 * segmentation.confidence
            + 0.3 * geometry.confidence
            + 0.4 * reference_result.reference_score
        )
        combined_confidence = float(max(0.0, min(1.0, combined_confidence)))

        breakdown = build_confidence_breakdown(
            segmentation_confidence=segmentation.confidence,
            geometry_confidence=geometry.confidence,
            reference_score=reference_result.reference_score,
            combined_confidence=combined_confidence,
        )

        # 判定逻辑：geometry 必须通过基础验证，reference 低于下限直接 reject
        if reference_result.reference_score < DEFAULT_REFERENCE_REJECT_THRESHOLD:
            status = "rejected"
            detail = f"Reference line support too low ({reference_result.reference_score:.2f} < {DEFAULT_REFERENCE_REJECT_THRESHOLD:.2f})"
        elif combined_confidence >= self.settings.court_line_confidence:
            status = "available"
            detail = "Automatic court calibration suggestion is ready"
        else:
            status = "rejected"
            detail = f"Combined confidence ({combined_confidence:.2f}) below threshold ({self.settings.court_line_confidence:.2f})"

        preview_url = self._write_preview(
            extracted.frame,
            segmentation=segmentation,
            geometry=geometry,
            suggestion_id=suggestion_id,
            reference_diag=reference_diag,
        )

        mask_diag_detail = (
            f"seg={segmentation.confidence:.2f} geo={geometry.confidence:.2f} "
            f"ref={reference_result.reference_score:.2f} combined={combined_confidence:.2f}"
        )

        return AutomaticCalibrationResponse(
            status=status,
            detail=detail,
            suggestion_id=suggestion_id if status == "available" else None,
            selected_frame=selected_frame,
            keypoints=geometry.keypoints,
            confidence=combined_confidence,
            quality=calibration_quality,
            mask=AutomaticCalibrationMaskDiagnostics(
                model_configured=True,
                model_path=segmentation.model_path,
                confidence=segmentation.confidence,
                mask_area_ratio=geometry.mask_area_ratio,
                line_count=geometry.line_count,
                detail=mask_diag_detail,
            ),
            reference=reference_diag,
            confidence_breakdown=breakdown,
            preview_image_url=preview_url,
        )

    def accept(self, payload: SemiAutomaticCalibrationAcceptRequest):
        request = ManualKeypointCalibrationRequest(
            video_id=payload.video_id,
            image_points=payload.image_points,
        )
        return self.calibration_service.create_semi_automatic_calibration(request)

    def response_for_accepted(self, payload: SemiAutomaticCalibrationAcceptRequest) -> AutomaticCalibrationResponse:
        calibration = self.accept(payload)
        manual = self.calibration_service.manual_response(calibration)
        keypoints = _manual_points_to_keypoints(payload.image_points)
        return AutomaticCalibrationResponse(
            status="accepted",
            detail="Semi-automatic calibration was stored",
            keypoints=keypoints,
            confidence=1.0 if payload.source == "corrected" else None,
            quality=manual.quality,
            calibration_id=manual.calibration_id,
            mask=AutomaticCalibrationMaskDiagnostics(
                model_configured=self.segmenter.configured,
                model_path=self.settings.court_line_model_path,
                detail=f"Calibration stored from {payload.source} keypoints",
            ),
        )

    def _extract_frame(self, video_path: str, payload: AutomaticCalibrationRequest) -> ExtractedFrame:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise ValueError("OpenCV is required to extract calibration frames") from exc

        path = Path(video_path)
        if not path.exists():
            raise ValueError("Video file not found")

        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise ValueError("Could not read uploaded video")

        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if payload.frame_index is not None:
                target_frame = payload.frame_index
            elif payload.timestamp_seconds is not None and fps > 0:
                target_frame = int(round(payload.timestamp_seconds * fps))
            elif frame_count > 0:
                target_frame = int(frame_count * self.settings.court_line_frame_ratio)
            else:
                target_frame = 0

            if frame_count > 0:
                target_frame = min(max(target_frame, 0), max(frame_count - 1, 0))
            capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ok, frame = capture.read()
            if not ok or frame is None:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = capture.read()
                target_frame = 0
            if not ok or frame is None:
                raise ValueError("Could not extract a readable calibration frame")

            height, width = frame.shape[:2]
            timestamp = target_frame / fps if fps > 0 else float(target_frame)
            return ExtractedFrame(
                frame=frame,
                frame_index=int(target_frame),
                timestamp_seconds=float(timestamp),
                width=int(width),
                height=int(height),
            )
        finally:
            capture.release()

    def _quality_for_keypoints(self, keypoints: AutomaticCalibrationKeypoints) -> CalibrationQuality:
        matrix = compute_homography(
            _keypoints_to_image_tuples(keypoints),
            [(0, 0), (20, 0), (20, 44), (0, 44)],
        )
        image_points = _keypoints_to_image_tuples(keypoints)
        projected = []
        from app.vision.courtvision_calibration_engine.homography import image_to_court

        result = image_to_court(image_points, matrix)
        projected = result if isinstance(result, list) else [result]
        expected = [(0, 0), (20, 0), (20, 44), (0, 44)]
        errors = [
            float(np.linalg.norm(np.asarray(point, dtype=float) - np.asarray(target, dtype=float)))
            for point, target in zip(projected, expected)
        ]
        reprojection_error = float(np.mean(errors)) if errors else 0.0
        return CalibrationQuality(
            reprojection_error=reprojection_error,
            status="ok" if reprojection_error <= 1.0 else "warning",
        )

    def _write_preview(
        self,
        frame: np.ndarray,
        segmentation: CourtLineSegmentationResult,
        geometry: MaskToKeypointsResult | None,
        suggestion_id: str,
        reference_diag=None,
    ) -> str | None:
        try:
            import cv2  # type: ignore
        except ImportError:
            return None

        output = frame.copy()
        mask = (segmentation.mask > 0).astype(np.uint8) * 255
        green = np.zeros_like(output)
        green[:, :] = (60, 220, 120)
        output = np.where(mask[:, :, None] > 0, cv2.addWeighted(output, 0.55, green, 0.45, 0), output)

        if geometry is not None:
            points = _keypoints_to_image_tuples(geometry.keypoints)
            for index, (x, y) in enumerate(points):
                cv2.circle(output, (round(x), round(y)), 7, (30, 255, 255), -1)
                cv2.putText(
                    output,
                    str(index + 1),
                    (round(x) + 8, round(y) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                )
            try:
                matrix = compute_homography(points, [(0, 0), (20, 0), (20, 44), (0, 44)])
                inverse = np.linalg.inv(matrix)
                output = draw_court_overlay(output, inverse)

                # 绘制 projected court lines 高亮
                from app.vision.courtvision_calibration_engine.court_overlay import court_line_image_points
                projected_lines = court_line_image_points(inverse)
                for line_name, start, end in projected_lines:
                    cv2.line(output, start, end, (255, 200, 40), 2)
            except Exception:
                pass

        # 绘制 reference support 摘要文本
        if reference_diag is not None:
            lines = [
                f"ref_score={reference_diag.reference_score:.2f}",
                f"supported={reference_diag.supported_lines}/{reference_diag.total_lines}",
                f"coverage={reference_diag.coverage:.2f}",
            ]
            if reference_diag.rejection_reason:
                lines.append(f"REJECT: {reference_diag.rejection_reason[:60]}")
            y_offset = 30
            for line_text in lines:
                cv2.putText(
                    output, line_text,
                    (12, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1,
                )
                cv2.putText(
                    output, line_text,
                    (12, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 0, 0), 1,
                )
                y_offset += 22

        path = self.storage.automatic_calibration_preview_path(suggestion_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), output):
            return None
        return f"/calibration/automatic/previews/{suggestion_id}"

    def _unavailable(self, detail: str, video_id: str | None = None) -> AutomaticCalibrationResponse:
        selected = (
            AutomaticCalibrationFrame(video_id=video_id, frame_index=0, timestamp_seconds=0.0, width=0, height=0)
            if video_id
            else None
        )
        return AutomaticCalibrationResponse(
            status="unavailable",
            detail=detail,
            selected_frame=selected,
            mask=AutomaticCalibrationMaskDiagnostics(
                model_configured=self.segmenter.configured,
                model_path=self.settings.court_line_model_path,
                detail=detail,
            ),
        )


def _manual_points_to_keypoints(points: ManualImageKeypoints) -> AutomaticCalibrationKeypoints:
    named = points.as_named_points()
    return AutomaticCalibrationKeypoints(
        top_left=_tuple_to_image_point(named["top_left"]),
        top_right=_tuple_to_image_point(named["top_right"]),
        bottom_right=_tuple_to_image_point(named["bottom_right"]),
        bottom_left=_tuple_to_image_point(named["bottom_left"]),
    )


def _tuple_to_image_point(point: tuple[float, float]):
    from app.schemas.calibration import ImagePoint

    return ImagePoint(x=float(point[0]), y=float(point[1]))


def _keypoints_to_image_tuples(keypoints: AutomaticCalibrationKeypoints) -> list[tuple[float, float]]:
    return [
        (keypoints.top_left.x, keypoints.top_left.y),
        (keypoints.top_right.x, keypoints.top_right.y),
        (keypoints.bottom_right.x, keypoints.bottom_right.y),
        (keypoints.bottom_left.x, keypoints.bottom_left.y),
    ]


automatic_calibration_service = AutomaticCalibrationService()
