"""Joint 模式共享类型 —— JointViewObservation(不污染 P0 ViewObservation)。

`JointViewObservation` 是 `joint_tracking_v2` 的观测类型,带图像空间证据
(bbox / frame size / image footpoint)与 `detection_origin` provenance。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DetectionOrigin = Literal["base", "guided_roi", "offline_refinement"]


@dataclass(frozen=True)
class JointViewInput:
    """joint_tracking_v2 一路视角的持久化输入(jointViewInputs[] 元素)。"""

    camera_slot: str  # cam_1 / cam_2
    capture_track_id: str = ""
    camera_id: str = ""
    video_id: str = ""
    calibration_id: str = ""
    court_orientation: str | None = None  # CourtOrientation 名(identity / mirror_x / ...)


@dataclass(frozen=True)
class JointViewObservation:
    """某视角在某 canonical tick 的联合观测。"""

    view_id: str
    take_timestamp_ms: float
    source_frame_index: int
    frame_width: int
    frame_height: int
    bbox: list[float]
    image_footpoint: tuple[float, float]
    local_x_ft: float
    local_y_ft: float
    canonical_x_ft: float
    canonical_y_ft: float
    detector_confidence: float = 0.0
    projection_confidence: float | None = None
    footpoint_confidence: float | None = None
    source_track_id: int | None = None
    view_player_id: str = ""
    detection_origin: DetectionOrigin = "base"
    guidance_id: str | None = None
    tracking_status: str = "detected"  # detected | tentative
    lock_state: str | None = None
