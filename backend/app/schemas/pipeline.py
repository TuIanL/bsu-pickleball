from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.metrics import PerformanceMetrics
from app.schemas.tracking import ProjectedTrackPoint


PipelineStageStatus = Literal["pending", "done", "failed", "skipped"]


class PipelineStageResult(BaseModel):
    id: str
    label: str
    status: PipelineStageStatus
    detail: str


class AnalysisArtifacts(BaseModel):
    result_json_path: Optional[str] = None
    tracking_result_json_path: Optional[str] = None
    tracking_overlay_json_path: Optional[str] = None
    tracking_overlay_url: Optional[str] = None
    ball_overlay_json_path: Optional[str] = None
    ball_overlay_url: Optional[str] = None
    pose_overlay_json_path: Optional[str] = None
    pose_overlay_url: Optional[str] = None
    source_video_url: Optional[str] = None
    tracking_overlay_status: Optional[str] = None
    tracking_overlay_detail: Optional[str] = None
    ball_overlay_status: Optional[str] = None
    ball_overlay_detail: Optional[str] = None
    pose_overlay_status: Optional[str] = None
    pose_overlay_detail: Optional[str] = None
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
