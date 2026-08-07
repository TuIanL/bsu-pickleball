"""
事件分析相关的 Pydantic 数据模型（当前主要是"发球开始"事件）。

发球事件检测：从视频里找出"运动员发球那一刻"，并给出证据分数、调试产物等，
供前端展示和研发诊断使用。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# 发球事件整体状态：可用 / 无候选 / 部分 / 不可用
ServeEventStatus = Literal["available", "no_candidates", "partial", "unavailable"]
# 用于判断发球的信号来源
ServeSignal = Literal["tracking", "pose", "trajectory", "roi", "video"]
# 检测模式
ServeDetectionMode = Literal["pose", "roi", "trajectory", "tracking"]
# 上下文状态：准备好发球 / 候选 / 被拒 / 不可用
ServeContextState = Literal["ready_to_serve", "candidate", "rejected", "unavailable"]


class ServeSignalScores(BaseModel):
    """各类信号的得分（0~1），综合起来判断是不是发球。"""

    baseline_position_score: float | None = Field(default=None, ge=0, le=1)  # 底线站位分
    pre_stillness_score: float | None = Field(default=None, ge=0, le=1)  # 发球前静止分
    arm_motion_peak_score: float | None = Field(default=None, ge=0, le=1)  # 手臂动作峰值分
    roi_motion_peak_score: float | None = Field(default=None, ge=0, le=1)  # ROI 运动峰值分
    rally_after_score: float | None = Field(default=None, ge=0, le=1)  # 发球后回合分
    receiver_waiting_score: float | None = Field(default=None, ge=0, le=1)  # 接球方等待分


class ServeCoverageDiagnostics(BaseModel):
    """发球检测在各信号源上的"覆盖度"诊断（哪些时间段有数据、覆盖率如何）。"""

    source_duration_seconds: float | None = Field(default=None, ge=0)
    tracking_first_timestamp_seconds: float | None = Field(default=None, ge=0)
    tracking_last_timestamp_seconds: float | None = Field(default=None, ge=0)
    pose_first_timestamp_seconds: float | None = Field(default=None, ge=0)
    pose_last_timestamp_seconds: float | None = Field(default=None, ge=0)
    trajectory_first_timestamp_seconds: float | None = Field(default=None, ge=0)
    trajectory_last_timestamp_seconds: float | None = Field(default=None, ge=0)
    score_series_first_timestamp_seconds: float | None = Field(default=None, ge=0)
    score_series_last_timestamp_seconds: float | None = Field(default=None, ge=0)
    score_series_count: int = Field(default=0, ge=0)
    candidate_first_timestamp_seconds: float | None = Field(default=None, ge=0)
    candidate_last_timestamp_seconds: float | None = Field(default=None, ge=0)
    candidate_count: int = Field(default=0, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)  # 整体覆盖率
    warnings: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ServeDebugArtifactRefs(BaseModel):
    """发球调试产物的引用（各种调试文件的地址）。"""

    candidates_url: str | None = None
    score_series_url: str | None = None
    clips_manifest_url: str | None = None
    debug_overlay_url: str | None = None
    status: str | None = None
    detail: str | None = None


class ServeEventCandidate(BaseModel):
    """一个发球事件候选（可能是真正的发球，也可能被后续过滤）。"""

    id: str
    timestamp_seconds: float = Field(ge=0)  # 事件发生时间
    frame_index: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)  # 置信度
    seek_time_seconds: float = Field(ge=0)  # 跳转/剪辑定位时间
    reason: str  # 判定理由
    source_signals: list[ServeSignal] = Field(default_factory=list)  # 来自哪些信号
    track_id: str | None = None
    player_id: str | None = None
    start_time_seconds: float | None = Field(default=None, ge=0)
    end_time_seconds: float | None = Field(default=None, ge=0)
    detection_mode: ServeDetectionMode | None = None
    context_state: ServeContextState | None = None
    court_position: list[float] | None = Field(default=None, min_length=2, max_length=2)  # 球场坐标 [x, y]
    court_unit: str | None = None
    signals: ServeSignalScores | None = None  # 各信号得分明细

    @model_validator(mode="after")
    def validate_seek_time(self) -> ServeEventCandidate:
        # 时间逻辑校验：跳转/起止时间不应晚于事件发生时间
        if self.seek_time_seconds > self.timestamp_seconds:
            raise ValueError("seek_time_seconds must be less than or equal to timestamp_seconds")
        if self.start_time_seconds is not None and self.start_time_seconds > self.timestamp_seconds:
            raise ValueError("start_time_seconds must be less than or equal to timestamp_seconds")
        if self.end_time_seconds is not None and self.end_time_seconds < self.timestamp_seconds:
            raise ValueError("end_time_seconds must be greater than or equal to timestamp_seconds")
        return self

    @field_validator("source_signals")
    @classmethod
    def validate_source_signals(cls, value: list[ServeSignal]) -> list[ServeSignal]:
        # 去重（保持顺序）
        return list(dict.fromkeys(value))


class ServeEventsArtifact(BaseModel):
    """一次分析的发球事件完整产物。"""

    job_id: str
    video_id: str | None = None
    status: ServeEventStatus = "unavailable"
    detail: str
    detector_version: str = "serve-start-mvp-v1"
    duration_seconds: float | None = Field(default=None, ge=0)
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    detection_mode: ServeDetectionMode | None = None
    available_signals: list[ServeSignal] = Field(default_factory=list)  # 本次可用的信号源
    debug_artifacts: ServeDebugArtifactRefs | None = None  # 调试产物引用
    coverage: ServeCoverageDiagnostics | None = None  # 覆盖度诊断
    events: list[ServeEventCandidate] = Field(default_factory=list)  # 事件候选列表

    @model_validator(mode="after")
    def validate_status_events(self) -> ServeEventsArtifact:
        # 如果有事件，状态必须是 available 或 partial
        if self.events and self.status not in {"available", "partial"}:
            raise ValueError("serve events require available or partial status")
        return self
