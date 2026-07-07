"""
Court-view（场地视角）门控与检测 ROI 相关的数据模型。

"场地视角"指摄像机正对球场、能看到完整场地的画面。系统会判断每一帧是不是场地视角，
只有场地视角帧才做检测/分析（非场地视角帧可跳过，省算力）。
ROI = Region Of Interest（感兴趣区域），即只在这块区域内做目标检测。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 场地视角 ROI 状态：可用 / 部分 / 跳过 / 不可用
CourtViewRoiStatus = Literal["available", "partial", "skipped", "unavailable"]
# 单帧被判定为某种"原因"
CourtViewFrameReason = Literal[
    "court_view",            # 是场地视角
    "gated_non_court_view",  # 被门控拦截：非场地视角
    "gate_unavailable",      # 门控不可用
    "diagnostic_only",       # 仅诊断模式
]


class CourtViewThresholds(BaseModel):
    """场地视角判定的阈值参数。"""
    match_threshold: float = Field(ge=0.0, le=1.0)  # 匹配分数阈值（高于才算场地视角）
    start_frames: int = Field(ge=1)                # 判定开始的连续帧数
    end_frames: int = Field(ge=1)                  # 判定结束的连续帧数
    diagnostic_only: bool = False                 # 仅诊断（不出正式结果）
    skip_non_court_frames: bool = True            # 跳过非场地视角帧


class CourtViewSegment(BaseModel):
    """一段连续的"场地视角"时间段（从某帧到某帧）。"""
    id: str
    kind: Literal["court_view_candidate"] = "court_view_candidate"
    start_frame_index: int = Field(ge=0)
    end_frame_index: int = Field(ge=0)
    start_timestamp_seconds: float = Field(ge=0.0)
    end_timestamp_seconds: float = Field(ge=0.0)
    duration_seconds: float = Field(ge=0.0)
    start_reason: str
    end_reason: str
    low_score_frame_count: int = Field(default=0, ge=0)  # 低分帧数
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)


class DetectionRoiBounds(BaseModel):
    """检测 ROI 的像素范围（检测只在这块矩形框内做）。"""
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    x2: int = Field(ge=0)
    y2: int = Field(ge=0)
    source_width: int = Field(ge=1)     # 原图宽
    source_height: int = Field(ge=1)    # 原图高
    padding_ratio: float = Field(ge=0.0)  # 外扩比例
    clipped_to_frame: bool = False        # 是否被裁剪到画面内


class DetectionRoiArtifact(BaseModel):
    """检测 ROI 产物（描述本视频检测区域的情况）。"""
    status: CourtViewRoiStatus
    detail: str
    bounds: DetectionRoiBounds | None = None       # ROI 范围（可能为 None）
    calibration_id: str | None = None
    source: Literal["calibration_keypoints", "unavailable"] = "unavailable"
    full_frame_fallback_count: int = Field(default=0, ge=0)  # 退回全帧检测的次数
    filtered_detection_count: int = Field(default=0, ge=0)   # 被过滤掉的检测数
    disabled: bool = False                           # 是否关闭 ROI 过滤
    diagnostics: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CourtViewFrameSample(BaseModel):
    """单帧的场地视角判定采样。"""
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0.0)
    score: float | None = Field(default=None, ge=0.0, le=1.0)  # 匹配分数
    is_court_view: bool | None = None                           # 是否场地视角
    reason: CourtViewFrameReason                                # 判定原因


class CourtViewRoiArtifact(BaseModel):
    """一次分析的场地视角 + ROI 完整产物。"""
    job_id: str
    video_id: str | None = None
    calibration_id: str | None = None
    status: CourtViewRoiStatus
    detail: str
    detector_version: str = "court-view-template-v1"   # 检测器版本
    thresholds: CourtViewThresholds                    # 判定阈值
    processed_frame_count: int = Field(default=0, ge=0)
    court_view_frame_count: int = Field(default=0, ge=0)       # 场地视角帧数
    non_court_view_frame_count: int = Field(default=0, ge=0)   # 非场地视角帧数
    gated_frame_count: int = Field(default=0, ge=0)            # 被门控拦截帧数
    roi_filtered_detection_count: int = Field(default=0, ge=0)  # ROI 过滤掉的检测数
    full_frame_fallback_count: int = Field(default=0, ge=0)
    candidate_segments: list[CourtViewSegment] = Field(default_factory=list)  # 候选场地视角段
    roi: DetectionRoiArtifact                                           # ROI 信息
    frame_samples: list[CourtViewFrameSample] = Field(default_factory=list)  # 逐帧采样
    diagnostics: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
