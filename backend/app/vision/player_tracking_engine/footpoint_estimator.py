"""脚点估计器 —— 从检测框/姿态关键点推算球员在图像中的脚部位置。"""

from __future__ import annotations

from collections.abc import Mapping

# BoundingBox：图像空间检测框；FootpointEstimate：脚点估计结果（含方法与像素坐标）；
# FootpointMethod：脚点估计方法枚举（字符串）；Track：带轨迹身份的检测框。
from app.schemas.tracking import BoundingBox, FootpointEstimate, FootpointMethod, Track

# COCO 关键点索引
_LEFT_ANKLE = 15
_RIGHT_ANKLE = 16
_LEFT_KNEE = 13
_RIGHT_KNEE = 14

# 置信度阈值
_ANKLE_CONF_THRESHOLD = 0.35
_KNEE_CONF_THRESHOLD = 0.4
# 膝到脚的长度占膝到头顶的比例（用于膝外推）
_KNEE_TO_FOOT_RATIO = 0.28


class FootpointEstimator:
    """Estimate image-space player footpoints from tracked person boxes and pose."""

    def __init__(self, method: FootpointMethod = "hybrid") -> None:
        self.method = method

    def estimate(
        self,
        bbox_or_track: BoundingBox | Track | list[float] | tuple[float, float, float, float],
        pose_keypoints: Mapping[int, dict] | None = None,
    ) -> FootpointEstimate:
        # hybrid 模式：pose > bbox fallback
        if self.method in ("hybrid", "pose_ankle_midpoint", "pose_ankle_single", "knee_extrapolated"):
            pose_result = self._estimate_from_pose(pose_keypoints)
            if pose_result is not None:
                return pose_result
            # non-hybrid pose-only 方法不 fallback
            if self.method != "hybrid":
                raise NotImplementedError(f"Footpoint method {self.method} requires pose keypoints")
        # bbox_bottom_center 或 hybrid fallback
        return self._estimate_from_bbox(bbox_or_track)

    def _estimate_from_pose(self, keypoints: Mapping[int, dict] | None) -> FootpointEstimate | None:
        if keypoints is None:
            return None

        left_ankle = keypoints.get(_LEFT_ANKLE)
        right_ankle = keypoints.get(_RIGHT_ANKLE)

        # 优先级 1：双踝中点
        if (left_ankle and left_ankle.get("confidence", 0) is not None and left_ankle["confidence"] >= _ANKLE_CONF_THRESHOLD
                and right_ankle and right_ankle.get("confidence", 0) is not None and right_ankle["confidence"] >= _ANKLE_CONF_THRESHOLD):
            return FootpointEstimate(
                image_footpoint=[
                    float(left_ankle["x"] + right_ankle["x"]) / 2.0,
                    float(left_ankle["y"] + right_ankle["y"]) / 2.0,
                ],
                method="pose_ankle_midpoint",
                confidence=min(left_ankle["confidence"], right_ankle["confidence"]),
            )

        # 优先级 2：单踝
        single_ankle = None
        if left_ankle and left_ankle.get("confidence", 0) is not None and left_ankle["confidence"] >= _ANKLE_CONF_THRESHOLD:
            single_ankle = left_ankle
        elif right_ankle and right_ankle.get("confidence", 0) is not None and right_ankle["confidence"] >= _ANKLE_CONF_THRESHOLD:
            single_ankle = right_ankle
        if single_ankle is not None:
            return FootpointEstimate(
                image_footpoint=[float(single_ankle["x"]), float(single_ankle["y"])],
                method="pose_ankle_single",
                confidence=single_ankle["confidence"],
            )

        # 优先级 3：膝外推
        left_knee = keypoints.get(_LEFT_KNEE)
        right_knee = keypoints.get(_RIGHT_KNEE)
        if (left_knee and left_knee.get("confidence", 0) is not None and left_knee["confidence"] >= _KNEE_CONF_THRESHOLD
                and right_knee and right_knee.get("confidence", 0) is not None and right_knee["confidence"] >= _KNEE_CONF_THRESHOLD):
            knee_mid_x = (left_knee["x"] + right_knee["x"]) / 2.0
            knee_mid_y = (left_knee["y"] + right_knee["y"]) / 2.0
            # 从双膝中点向下外推估算脚点 y
            hip_y = _estimate_hip_y(keypoints)
            if hip_y is not None:
                foot_y = knee_mid_y + (knee_mid_y - hip_y) * _KNEE_TO_FOOT_RATIO
            else:
                foot_y = knee_mid_y + 30  # 保守 fallback：向下 30px
            return FootpointEstimate(
                image_footpoint=[knee_mid_x, foot_y],
                method="knee_extrapolated",
                confidence=min(left_knee["confidence"], right_knee["confidence"]) * 0.8,
            )

        return None

    def _estimate_from_bbox(self, bbox_or_track: BoundingBox | Track | list[float] | tuple[float, float, float, float]) -> FootpointEstimate:
        x1, _, x2, y2 = _bbox_values(bbox_or_track)
        return FootpointEstimate(
            image_footpoint=[float(x1 + x2) / 2.0, float(y2)],
            method="bbox_bottom_center",
        )


def _estimate_hip_y(keypoints: Mapping[int, dict]) -> float | None:
    """估算臀部 y 坐标（用左右髋中点，若无则用颈部/肩膀估算）。"""
    left_hip = keypoints.get(11)
    right_hip = keypoints.get(12)
    if left_hip and right_hip:
        return (left_hip["y"] + right_hip["y"]) / 2.0
    # 用颈部/肩膀粗略估算
    neck = keypoints.get(5) or keypoints.get(6)
    if neck:
        return neck["y"] + 50
    return None


def estimate_footpoint(bbox: BoundingBox | list[float] | tuple[float, float, float, float]) -> tuple[float, float]:
    """Compatibility wrapper returning the bbox bottom-center tuple."""
    estimate = FootpointEstimator(method="bbox_bottom_center").estimate(bbox)
    return (estimate.image_footpoint[0], estimate.image_footpoint[1])


def _bbox_values(bbox_or_track: BoundingBox | Track | list[float] | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if isinstance(bbox_or_track, Track):
        x1, y1, x2, y2 = bbox_or_track.bbox
    elif isinstance(bbox_or_track, BoundingBox):
        x1, y1, x2, y2 = bbox_or_track.x1, bbox_or_track.y1, bbox_or_track.x2, bbox_or_track.y2
    else:
        x1, y1, x2, y2 = bbox_or_track
    return (float(x1), float(y1), float(x2), float(y2))
