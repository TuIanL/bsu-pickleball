from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.tracking import SourceFrameSize


PoseArtifactStatus = Literal["available", "no_poses", "unavailable"]


RTMPOSE26_KEYPOINT_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "head",
    "neck",
    "hip",
    "left_big_toe",
    "right_big_toe",
    "left_small_toe",
    "right_small_toe",
    "left_heel",
    "right_heel",
]


DEFAULT_SKELETON_EDGES = [
    ("left_ankle", "left_knee"),
    ("left_knee", "left_hip"),
    ("left_hip", "hip"),
    ("right_ankle", "right_knee"),
    ("right_knee", "right_hip"),
    ("right_hip", "hip"),
    ("head", "neck"),
    ("neck", "hip"),
    ("neck", "left_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("neck", "right_shoulder"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_eye", "right_eye"),
    ("nose", "left_eye"),
    ("nose", "right_eye"),
    ("left_eye", "left_ear"),
    ("right_eye", "right_ear"),
    ("left_ear", "left_shoulder"),
    ("right_ear", "right_shoulder"),
    ("left_ankle", "left_big_toe"),
    ("left_ankle", "left_small_toe"),
    ("left_ankle", "left_heel"),
    ("right_ankle", "right_big_toe"),
    ("right_ankle", "right_small_toe"),
    ("right_ankle", "right_heel"),
]


class PoseKeypoint(BaseModel):
    name: str
    x: float
    y: float
    confidence: float = Field(ge=0, le=1)
    visible: bool = True


class SkeletonEdge(BaseModel):
    from_keypoint: str
    to_keypoint: str


class PoseSubject(BaseModel):
    track_id: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    keypoints: list[PoseKeypoint] = Field(default_factory=list)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox must contain exactly 4 numeric values")
        return [float(item) for item in value]


class PoseOverlayFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    subjects: list[PoseSubject] = Field(default_factory=list)


class PoseOverlayArtifact(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    status: PoseArtifactStatus = "unavailable"
    detail: str
    keypoint_schema: str = "rtmpose26"
    source: SourceFrameSize
    skeleton_edges: list[SkeletonEdge] = Field(default_factory=list)
    frames: list[PoseOverlayFrame] = Field(default_factory=list)


def default_skeleton_edges() -> list[SkeletonEdge]:
    return [SkeletonEdge(from_keypoint=start, to_keypoint=end) for start, end in DEFAULT_SKELETON_EDGES]
