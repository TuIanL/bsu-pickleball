"""
分析流水线（Pipeline）结果相关的 Pydantic 数据模型。

一次完整分析的"最终产出"用这里的模型描述：包含各阶段执行情况、
球场投影后的轨迹点、运动指标，以及所有中间产物（artifact）的文件路径清单。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import MatchAnalysisContext
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
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    progress: int = Field(default=0, ge=0, le=100)  # 进度百分比
    error_code: str | None = None
    public_message: str | None = None  # 给用户看的信息
    internal_message: str | None = None  # 内部调试信息
    retry_count: int = Field(default=0, ge=0)
    counters: dict[str, Any] = Field(default_factory=dict)


class AnalysisArtifacts(BaseModel):
    """所有分析中间产物的路径/URL 清单。

    每个产物通常有 *_path（磁盘路径）和 *_url（访问地址）两对字段，
    以及 *_status / *_detail（生成状态与说明）。这里集中列出，便于前端按名取用。
    """

    result_json_path: str | None = None
    tracking_result_json_path: str | None = None
    tracking_overlay_json_path: str | None = None
    tracking_overlay_url: str | None = None
    player_selection_json_path: str | None = None
    player_selection_url: str | None = None
    player_selection_training_samples_json_path: str | None = None
    player_selection_training_samples_url: str | None = None
    detections_jsonl_path: str | None = None
    detections_url: str | None = None
    ball_overlay_json_path: str | None = None
    ball_overlay_url: str | None = None
    ball_trajectory_json_path: str | None = None
    ball_trajectory_url: str | None = None
    cleaned_ball_trajectory_json_path: str | None = None
    cleaned_ball_trajectory_url: str | None = None
    bounce_events_json_path: str | None = None
    bounce_events_url: str | None = None
    reconstructed_ball_trajectory_json_path: str | None = None
    reconstructed_ball_trajectory_url: str | None = None
    analysis_overlay_video_path: str | None = None
    analysis_overlay_video_url: str | None = None
    heatmaps_manifest_json_path: str | None = None
    heatmaps_url: str | None = None
    scatter_plots_manifest_json_path: str | None = None
    scatter_plots_url: str | None = None
    pose_overlay_json_path: str | None = None
    pose_overlay_url: str | None = None
    serve_events_json_path: str | None = None
    serve_events_url: str | None = None
    serve_debug_candidates_json_path: str | None = None
    serve_debug_candidates_url: str | None = None
    serve_score_series_json_path: str | None = None
    serve_score_series_url: str | None = None
    serve_clips_manifest_json_path: str | None = None
    serve_clips_manifest_url: str | None = None
    serve_debug_overlay_path: str | None = None
    serve_debug_overlay_url: str | None = None
    player_trajectory_json_path: str | None = None
    player_trajectory_csv_path: str | None = None
    player_trajectory_url: str | None = None
    player_render_trajectory_json_path: str | None = None
    player_render_trajectory_url: str | None = None
    court_view_roi_json_path: str | None = None
    court_view_roi_url: str | None = None
    source_video_url: str | None = None
    calibration_diagnostics_json_path: str | None = None
    calibration_diagnostics_url: str | None = None
    # 下面是各产物的状态/说明（用于前端判断某个 overlay 是否可用）
    tracking_overlay_status: str | None = None
    tracking_overlay_detail: str | None = None
    player_selection_status: str | None = None
    player_selection_detail: str | None = None
    detections_status: str | None = None
    detections_detail: str | None = None
    ball_overlay_status: str | None = None
    ball_overlay_detail: str | None = None
    ball_trajectory_status: str | None = None
    ball_trajectory_detail: str | None = None
    cleaned_ball_trajectory_status: str | None = None
    cleaned_ball_trajectory_detail: str | None = None
    bounce_events_status: str | None = None
    bounce_events_detail: str | None = None
    reconstructed_ball_trajectory_status: str | None = None
    reconstructed_ball_trajectory_detail: str | None = None
    analysis_overlay_video_status: str | None = None
    analysis_overlay_video_detail: str | None = None
    position_visualizations_status: str | None = None
    position_visualizations_detail: str | None = None
    pose_overlay_status: str | None = None
    pose_overlay_detail: str | None = None
    serve_events_status: str | None = None
    serve_events_detail: str | None = None
    serve_debug_artifacts_status: str | None = None
    serve_debug_artifacts_detail: str | None = None
    player_trajectory_status: str | None = None
    player_trajectory_detail: str | None = None
    court_view_roi_status: str | None = None
    court_view_roi_detail: str | None = None
    overlay_video_path: str | None = None
    analysis_window: dict[str, Any] | None = None
    analysis_overlay_video_metadata: dict[str, Any] | None = None


class AnalysisPipelineResult(BaseModel):
    """一次分析的完整流水线结果（前端读 /jobs/{id}/result 时返回这个）。"""

    job_id: str
    video_id: str | None = None
    calibration_id: str | None = None
    status: Literal["completed", "failed"]  # 整体结果状态
    generated_at: datetime  # 生成时间
    stages: list[PipelineStageResult]  # 各阶段执行情况
    tracks: list[ProjectedTrackPoint] = Field(default_factory=list)  # 球场投影后的轨迹点
    metrics: PerformanceMetrics  # 运动指标
    artifacts: AnalysisArtifacts  # 产物路径清单
    message: str  # 结果说明
    match_context: MatchAnalysisContext | None = None  # 比赛分析上下文
    observed_player_count: int | None = None  # 实际观察到的球员数
    analysis_window: dict[str, Any] | None = None
    requested_execution_mode: str | None = None
    effective_multiview_mode: str | None = None
    execution_mode: str | None = None
    authoritative_joint_eligible: bool | None = None
