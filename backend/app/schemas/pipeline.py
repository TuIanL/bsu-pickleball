"""
分析流水线（Pipeline）结果相关的 Pydantic 数据模型。

一次完整分析的"最终产出"用这里的模型描述：包含各阶段执行情况、
球场投影后的轨迹点、运动指标，以及所有中间产物（artifact）的文件路径清单。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.metrics import PerformanceMetrics
from app.schemas.tracking import ProjectedTrackPoint

# 流水线阶段状态：与 analysis 里的阶段状态含义一致
PipelineStageStatus = Literal["pending", "active", "done", "partial", "failed", "skipped", "unavailable", "canceled"]


class PipelineStageResult(BaseModel):
    """单个流水线阶段的执行结果。"""
    id: str
    label: str
    status: PipelineStageStatus
    detail: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    progress: int = Field(default=0, ge=0, le=100)  # 进度百分比
    error_code: Optional[str] = None
    public_message: Optional[str] = None            # 给用户看的信息
    internal_message: Optional[str] = None          # 内部调试信息
    retry_count: int = Field(default=0, ge=0)
    counters: dict[str, Any] = Field(default_factory=dict)


class AnalysisArtifacts(BaseModel):
    """所有分析中间产物的路径/URL 清单。

    每个产物通常有 *_path（磁盘路径）和 *_url（访问地址）两对字段，
    以及 *_status / *_detail（生成状态与说明）。这里集中列出，便于前端按名取用。
    """
    result_json_path: Optional[str] = None
    tracking_result_json_path: Optional[str] = None
    tracking_overlay_json_path: Optional[str] = None
    tracking_overlay_url: Optional[str] = None
    player_selection_json_path: Optional[str] = None
    player_selection_url: Optional[str] = None
    player_selection_training_samples_json_path: Optional[str] = None
    player_selection_training_samples_url: Optional[str] = None
    detections_jsonl_path: Optional[str] = None
    detections_url: Optional[str] = None
    ball_overlay_json_path: Optional[str] = None
    ball_overlay_url: Optional[str] = None
    ball_trajectory_json_path: Optional[str] = None
    ball_trajectory_url: Optional[str] = None
    cleaned_ball_trajectory_json_path: Optional[str] = None
    cleaned_ball_trajectory_url: Optional[str] = None
    bounce_events_json_path: Optional[str] = None
    bounce_events_url: Optional[str] = None
    analysis_overlay_video_path: Optional[str] = None
    analysis_overlay_video_url: Optional[str] = None
    heatmaps_manifest_json_path: Optional[str] = None
    heatmaps_url: Optional[str] = None
    scatter_plots_manifest_json_path: Optional[str] = None
    scatter_plots_url: Optional[str] = None
    pose_overlay_json_path: Optional[str] = None
    pose_overlay_url: Optional[str] = None
    serve_events_json_path: Optional[str] = None
    serve_events_url: Optional[str] = None
    serve_debug_candidates_json_path: Optional[str] = None
    serve_debug_candidates_url: Optional[str] = None
    serve_score_series_json_path: Optional[str] = None
    serve_score_series_url: Optional[str] = None
    serve_clips_manifest_json_path: Optional[str] = None
    serve_clips_manifest_url: Optional[str] = None
    serve_debug_overlay_path: Optional[str] = None
    serve_debug_overlay_url: Optional[str] = None
    player_trajectory_json_path: Optional[str] = None
    player_trajectory_csv_path: Optional[str] = None
    player_trajectory_url: Optional[str] = None
    court_view_roi_json_path: Optional[str] = None
    court_view_roi_url: Optional[str] = None
    source_video_url: Optional[str] = None
    # 下面是各产物的状态/说明（用于前端判断某个 overlay 是否可用）
    tracking_overlay_status: Optional[str] = None
    tracking_overlay_detail: Optional[str] = None
    player_selection_status: Optional[str] = None
    player_selection_detail: Optional[str] = None
    detections_status: Optional[str] = None
    detections_detail: Optional[str] = None
    ball_overlay_status: Optional[str] = None
    ball_overlay_detail: Optional[str] = None
    ball_trajectory_status: Optional[str] = None
    ball_trajectory_detail: Optional[str] = None
    cleaned_ball_trajectory_status: Optional[str] = None
    cleaned_ball_trajectory_detail: Optional[str] = None
    bounce_events_status: Optional[str] = None
    bounce_events_detail: Optional[str] = None
    analysis_overlay_video_status: Optional[str] = None
    analysis_overlay_video_detail: Optional[str] = None
    position_visualizations_status: Optional[str] = None
    position_visualizations_detail: Optional[str] = None
    pose_overlay_status: Optional[str] = None
    pose_overlay_detail: Optional[str] = None
    serve_events_status: Optional[str] = None
    serve_events_detail: Optional[str] = None
    serve_debug_artifacts_status: Optional[str] = None
    serve_debug_artifacts_detail: Optional[str] = None
    player_trajectory_status: Optional[str] = None
    player_trajectory_detail: Optional[str] = None
    court_view_roi_status: Optional[str] = None
    court_view_roi_detail: Optional[str] = None
    overlay_video_path: Optional[str] = None


class AnalysisPipelineResult(BaseModel):
    """一次分析的完整流水线结果（前端读 /jobs/{id}/result 时返回这个）。"""
    job_id: str
    video_id: Optional[str] = None
    calibration_id: Optional[str] = None
    status: Literal["completed", "failed"]    # 整体结果状态
    generated_at: datetime                     # 生成时间
    stages: List[PipelineStageResult]          # 各阶段执行情况
    tracks: List[ProjectedTrackPoint] = Field(default_factory=list)  # 球场投影后的轨迹点
    metrics: PerformanceMetrics                # 运动指标
    artifacts: AnalysisArtifacts               # 产物路径清单
    message: str                               # 结果说明
