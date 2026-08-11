"""球分析产物的 Pydantic 数据模型 —— ball overlay、轨迹点、弹跳事件等。

本模块定义面向 API 和 artifact 合同的"球分析结果"数据结构，
与 `pickleball_game_analysis/schemas.py`（内部算法数据结构）分离。
前者是稳定契约，后者是内部实现细节。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 字面量类型
# ---------------------------------------------------------------------------

BallTrackStatus = Literal["detected", "missing", "rejected"]
BallOverlayStatus = Literal["available", "partial", "no_detections", "unavailable", "skipped"]


# ---------------------------------------------------------------------------
# 逐帧 ball overlay 数据结构
# ---------------------------------------------------------------------------


class BallOverlayPoint(BaseModel):
    """image-space 球中心点坐标。"""

    x: float | None = Field(default=None, description="球中心在图像中的 X 坐标（像素）")
    y: float | None = Field(default=None, description="球中心在图像中的 Y 坐标（像素）")


class BallOverlayCourtPoint(BaseModel):
    """court-space 球坐标（通过 homography 投影后的球场坐标）。"""

    x: float = Field(..., description="球场 X 坐标（英尺）")
    y: float = Field(..., description="球场 Y 坐标（英尺）")
    unit: str = Field(default="ft", description="坐标单位")


class BallOverlayBall(BaseModel):
    """单帧的球检测数据，用于视频叠加渲染。"""

    center: BallOverlayPoint | None = Field(default=None, description="球中心点（image-space）")
    bbox: list[float] | None = Field(default=None, description="检测框 [x1, y1, x2, y2]（image-space）")
    confidence: float | None = Field(default=None, description="检测置信度")
    track_status: BallTrackStatus = Field(default="missing", description="本帧的球跟踪状态")
    court: BallOverlayCourtPoint | None = Field(default=None, description="球场投影坐标（当 homography 可用时）")


class BallOverlayFrame(BaseModel):
    """ball_overlay.json 中的单帧记录。"""

    frame_index: int = Field(..., description="帧序号（从 0 开始）")
    timestamp_seconds: float = Field(..., description="帧对应的时间戳（秒）")
    ball: BallOverlayBall = Field(..., description="本帧的球检测数据")


class BallOverlaySource(BaseModel):
    """ball_overlay.json 的视频源信息。"""

    width: int = Field(..., description="视频宽度（像素）")
    height: int = Field(..., description="视频高度（像素）")
    fps: float = Field(..., description="视频帧率")
    frame_stride: int = Field(..., description="抽帧步长")
    processed_frame_count: int = Field(..., description="实际处理的帧数")
    timing_provenance: dict[str, object] | None = Field(default=None, description="时间轴来源与兼容模式")


class BallOverlayCoverage(BaseModel):
    """ball_overlay.json 的覆盖率摘要。"""

    overlay_frame_count: int = Field(..., description="有球 overlay 记录的帧数")
    missing_frame_count: int = Field(..., description="球检测未发现候选的帧数")
    detection_rate: float = Field(..., description="检测率（overlay_frame_count / processed_frame_count）")


class BallOverlayArtifact(BaseModel):
    """ball_overlay.json 的完整 artifact 合同。"""

    schema_version: str = Field(default="ball_overlay.v1", description="Schema 版本号")
    job_id: str = Field(..., description="分析任务 ID")
    video_id: str | None = Field(default=None, description="视频 ID")
    status: BallOverlayStatus = Field(..., description="产物状态")
    detail: str = Field(..., description="人类可读的状态说明")
    source: BallOverlaySource = Field(..., description="视频源信息")
    coverage: BallOverlayCoverage = Field(..., description="检测覆盖率摘要")
    frames: list[BallOverlayFrame] = Field(default_factory=list, description="逐帧球检测叠加数据")


# ---------------------------------------------------------------------------
# 轨迹与弹跳事件 artifact 模型（API 合同层）
# ---------------------------------------------------------------------------


class BallTrajectorySample(BaseModel):
    """ball_trajectory.json 中的单条轨迹样本。"""

    frame_index: int
    timestamp_sec: float
    image_xy: tuple[float, float] | None = None
    court_xy: tuple[float, float] | None = None
    confidence: float | None = None
    visible: bool = False
    accepted: bool = False
    interpolated: bool = False
    candidate_count: int = 0
    reject_reason: str | None = None
    source: str = "detector"
    in_bounds: bool | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class BounceEventItem(BaseModel):
    """bounce_events.json 中的单个弹跳事件。"""

    event_id: str
    frame_index: int
    timestamp_sec: float
    image_xy: tuple[float, float]
    court_xy: tuple[float, float] | None = None
    confidence: float
    detection_method: str
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    rally_id: str | None = None
