"""Optional RTMPose adapter with lazy heavyweight imports."""

from pathlib import Path
from typing import Any, Sequence

from app.schemas.pose import (
    RTMPOSE26_KEYPOINT_NAMES,
    PoseKeypoint,
    PoseOverlayFrame,
    PoseSubject,
)
from app.schemas.tracking import FrameDetection


class RTMPose26Adapter:
    def __init__(
        self,
        config_path: str | None,
        checkpoint_path: str | None,
        device: str | None = None,
        conf_threshold: float = 0.3,
        keypoint_schema: str = "rtmpose26",
    ) -> None:
        self.config_path = config_path
        self.checkpoint_path = checkpoint_path
        self.device = device or "cpu"
        self.conf_threshold = conf_threshold
        self.keypoint_schema = keypoint_schema
        self._model: Any | None = None

    def estimate_frame(
        self,
        frame: object,
        subjects: Sequence[FrameDetection],
        frame_index: int,
        timestamp_seconds: float,
    ) -> PoseOverlayFrame:
        if not subjects:
            return PoseOverlayFrame(frame_index=frame_index, timestamp_seconds=timestamp_seconds)

        model = self._load_model()
        inference_topdown = self._inference_topdown()

        try:
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise RuntimeError("numpy is required to run RTMPose inference") from exc

        boxes = np.array([subject.bbox for subject in subjects], dtype=float)
        try:
            pose_results = inference_topdown(model, frame, bboxes=boxes, bbox_format="xyxy")
        except TypeError:
            pose_results = inference_topdown(model, frame, boxes)

        rendered_subjects: list[PoseSubject] = []
        for index, subject in enumerate(subjects):
            sample = pose_results[index] if index < len(pose_results) else None
            keypoints, scores = self._extract_keypoints(sample)
            rendered_subjects.append(
                PoseSubject(
                    track_id=subject.track_id or f"subject-{index + 1}",
                    bbox=subject.bbox,
                    confidence=subject.confidence,
                    keypoints=self._normalize_keypoints(keypoints, scores),
                )
            )

        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=rendered_subjects,
        )

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.config_path or not self.checkpoint_path:
            raise RuntimeError("RTMPose config/checkpoint paths are not configured")
        if not Path(self.config_path).exists():
            raise RuntimeError(f"RTMPose config not found: {self.config_path}")
        if not Path(self.checkpoint_path).exists():
            raise RuntimeError(f"RTMPose checkpoint not found: {self.checkpoint_path}")

        try:
            from mmpose.apis import init_model  # type: ignore
        except ImportError as exc:
            raise RuntimeError("mmpose is not installed; install RTMPose runtime dependencies") from exc

        self._model = init_model(self.config_path, self.checkpoint_path, device=self.device)
        return self._model

    @staticmethod
    def _inference_topdown() -> Any:
        try:
            from mmpose.apis import inference_topdown  # type: ignore
        except ImportError as exc:
            raise RuntimeError("mmpose inference_topdown is unavailable") from exc
        return inference_topdown

    @staticmethod
    def _extract_keypoints(sample: Any) -> tuple[list[list[float]], list[float]]:
        if sample is None:
            return ([], [])
        pred_instances = getattr(sample, "pred_instances", None)
        if pred_instances is None and isinstance(sample, dict):
            pred_instances = sample.get("pred_instances")
        if pred_instances is None:
            return ([], [])

        keypoints = getattr(pred_instances, "keypoints", None)
        scores = getattr(pred_instances, "keypoint_scores", None)
        if isinstance(pred_instances, dict):
            keypoints = pred_instances.get("keypoints", keypoints)
            scores = pred_instances.get("keypoint_scores", scores)
        if keypoints is None:
            return ([], [])

        keypoint_rows = keypoints[0] if hasattr(keypoints, "__getitem__") and len(keypoints) else keypoints
        score_rows = scores[0] if scores is not None and hasattr(scores, "__getitem__") and len(scores) else scores
        normalized_keypoints = [[float(point[0]), float(point[1])] for point in keypoint_rows]
        normalized_scores = [float(score) for score in score_rows] if score_rows is not None else [1.0] * len(normalized_keypoints)
        return (normalized_keypoints, normalized_scores)

    def _normalize_keypoints(self, keypoints: list[list[float]], scores: list[float]) -> list[PoseKeypoint]:
        names = RTMPOSE26_KEYPOINT_NAMES if self.keypoint_schema == "rtmpose26" else []
        normalized: list[PoseKeypoint] = []
        for index, point in enumerate(keypoints):
            confidence = scores[index] if index < len(scores) else 0.0
            normalized.append(
                PoseKeypoint(
                    name=names[index] if index < len(names) else f"keypoint_{index}",
                    x=point[0],
                    y=point[1],
                    confidence=confidence,
                    visible=confidence >= self.conf_threshold,
                )
            )
        return normalized
