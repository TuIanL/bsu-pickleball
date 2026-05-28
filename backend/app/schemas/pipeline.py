"""分析流水线（Pipeline）结果相关的 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.metrics import PerformanceMetrics
from app.schemas.tracking import ProjectedTrackPoint

# 流水线阶段状态
PipelineStageStatus = Literal["pending", "active", "done", "failed", "skipped", "canceled"]


class PipelineStageResult(BaseModel):
    """单个流水线阶段的执行结果。"""
    id: str
    label: str
    status: PipelineStageStatus
    detail: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    progress: int = Field(default=0, ge=0, le=100)
    error_code: Optional[str] = None
    public_message: Optional[str] = None
    internal_message: Optional[str] = None
    retry_count: int = Field(default=0, ge=0)
    counters: dict[str, Any] = Field(default_factory=dict)


class AnalysisArtifacts(BaseModel):
    result_json_path: Optional[str] = None
    tracking_result_json_path: Optional[str] = None
    tracking_overlay_json_path: Optional[str] = None
    tracking_overlay_url: Optional[str] = None
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
    source_video_url: Optional[str] = None
    tracking_overlay_status: Optional[str] = None
    tracking_overlay_detail: Optional[str] = None
    pose_overlay_status: Optional[str] = None
    pose_overlay_detail: Optional[str] = None
    serve_events_status: Optional[str] = None
    serve_events_detail: Optional[str] = None
    serve_debug_artifacts_status: Optional[str] = None
    serve_debug_artifacts_detail: Optional[str] = None
    player_trajectory_status: Optional[str] = None
    player_trajectory_detail: Optional[str] = None
    overlay_video_path: Optional[str] = None


class AnalysisPipelineResult(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    calibration_id: Optional[str] = None
    status: Literal["completed", "failed"]
    generated_at: datetime
    stages: List[PipelineStageResult]
    tracks: List[ProjectedTrackPoint] = Field(default_factory=list)
    metrics: PerformanceMetrics
    artifacts: AnalysisArtifacts
    message: str
