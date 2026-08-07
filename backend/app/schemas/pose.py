"""
人体姿态估计相关的 Pydantic 数据模型 —— RTMPose26 关键点、骨架边、姿态叠加帧等。

姿态（Pose）就是识别人体关键点的位置（鼻子、肩、肘、膝、脚踝……），
并用"骨架连线"画出来。本文件定义这些关键点和逐帧的姿态叠加结果。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.tracking import SourceFrameSize

# 姿态产物状态：可用 / 无姿态 / 不可用
PoseArtifactStatus = Literal["available", "no_poses", "unavailable"]

# RTMPose26 模型的 26 个关键点名称（从上到下：头/脸 → 肩/臂 → 髋/腿 → 脚）
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


# 骨架连线（哪些关键点之间画一条线），用于把散点连成"人体骨架"
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
    """单个姿态关键点。"""

    name: str
    x: float
    y: float
    confidence: float = Field(ge=0, le=1)  # 该点置信度（0~1）
    visible: bool = True  # 是否可见


class SkeletonEdge(BaseModel):
    """一条骨架连线：从某关键点到某关键点。"""

    from_keypoint: str
    to_keypoint: str


class PoseSubject(BaseModel):
    """一帧里一个人的姿态：检测框 + 置信度 + 所有关键点。"""

    track_id: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    keypoints: list[PoseKeypoint] = Field(default_factory=list)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        # 校验 bbox 必须是 4 个数值
        if len(value) != 4:
            raise ValueError("bbox must contain exactly 4 numeric values")
        return [float(item) for item in value]


class PoseOverlayFrame(BaseModel):
    """某一帧的姿态叠加数据：包含该帧所有人。"""

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    subjects: list[PoseSubject] = Field(default_factory=list)


class PoseOverlayArtifact(BaseModel):
    """一次分析的完整姿态叠加产物（给前端画骨架用）。"""

    job_id: str
    video_id: str | None = None
    status: PoseArtifactStatus = "unavailable"
    detail: str
    keypoint_schema: str = "rtmpose26"  # 关键点方案名
    source: SourceFrameSize  # 原图尺寸
    skeleton_edges: list[SkeletonEdge] = Field(default_factory=list)  # 骨架连线定义
    frames: list[PoseOverlayFrame] = Field(default_factory=list)


def default_skeleton_edges() -> list[SkeletonEdge]:
    # 用上面的默认连线生成 SkeletonEdge 对象列表
    return [SkeletonEdge(from_keypoint=start, to_keypoint=end) for start, end in DEFAULT_SKELETON_EDGES]
