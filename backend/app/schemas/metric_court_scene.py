"""Metric court scene calibration contracts.

The first version is intentionally file-backed and capture-take scoped.  It
keeps the static court/net geometry separate from AnalysisJob artifacts so a
fixed camera setup can be reused by multiple recordings and re-runs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SceneCalibrationStatus = Literal["draft", "ready", "degraded", "invalidated"]
SceneCalibrationSource = Literal["manual", "auto_suggested", "manual_verified"]
SceneHeightSource = Literal["standard", "measured"]
CameraModelSource = Literal["net_refined_virtual", "homography_constrained_virtual"]
MetricValidity = Literal["metric_multiview", "approximate_multiview", "visualization_only", "unavailable"]


class SceneImagePoint(BaseModel):
    x: float
    y: float


class ScenePoint3D(BaseModel):
    x: float
    y: float
    z: float


class NetProfileControlPoint(BaseModel):
    id: str
    world: ScenePoint3D
    image_by_view: dict[str, SceneImagePoint] = Field(default_factory=dict)
    provenance: SceneCalibrationSource = "manual"
    confirmed: bool = False


class NetProfile(BaseModel):
    profile_type: Literal["standard", "measured"] = "standard"
    height_source: SceneHeightSource = "standard"
    coordinate_units: Literal["feet"] = "feet"
    control_points: list[NetProfileControlPoint] = Field(default_factory=list)
    sampled_top_profile: list[ScenePoint3D] = Field(default_factory=list)
    post_world_points: list[ScenePoint3D] = Field(default_factory=list)


class SceneCameraQuality(BaseModel):
    court_reprojection_error_px: float | None = Field(default=None, ge=0.0)
    net_reprojection_error_px: float | None = Field(default=None, ge=0.0)
    holdout_reprojection_error_px: float | None = Field(default=None, ge=0.0)
    ray_angle_deg: float | None = Field(default=None, ge=0.0)
    height_uncertainty_ft: float | None = Field(default=None, ge=0.0)
    status: Literal["ok", "warning", "failed"] = "warning"
    rejection_reasons: list[str] = Field(default_factory=list)


class SceneCameraModel(BaseModel):
    source: CameraModelSource = "homography_constrained_virtual"
    projection: list[list[float]] | None = None
    rotation: list[list[float]] | None = None
    translation: list[float] | None = None
    focal_px: float | None = Field(default=None, ge=0.0)
    image_width: int | None = Field(default=None, ge=0)
    image_height: int | None = Field(default=None, ge=0)


class SceneViewCalibration(BaseModel):
    view_id: str
    camera_id: str | None = None
    video_id: str | None = None
    calibration_id: str | None = None
    image_width: int | None = Field(default=None, ge=0)
    image_height: int | None = Field(default=None, ge=0)
    frame_index: int | None = Field(default=None, ge=0)
    timestamp_seconds: float | None = Field(default=None, ge=0.0)
    court_orientation: str | None = None
    net_annotations: dict[str, SceneImagePoint] = Field(default_factory=dict)
    holdout_annotations: dict[str, SceneImagePoint] = Field(default_factory=dict)
    camera_model: SceneCameraModel | None = None
    quality: SceneCameraQuality = Field(default_factory=SceneCameraQuality)
    provenance: SceneCalibrationSource = "manual"


class MetricCourtSceneCalibration(BaseModel):
    schema_version: Literal["metric_court_scene.v1"] = "metric_court_scene.v1"
    capture_take_id: str
    revision: int = Field(default=0, ge=0)
    status: SceneCalibrationStatus = "draft"
    canonical_frame_id: str | None = None
    coordinate_units: Literal["feet"] = "feet"
    court_width_ft: float = Field(default=20.0, gt=0.0)
    court_length_ft: float = Field(default=44.0, gt=0.0)
    net_y_ft: float = Field(default=22.0, ge=0.0, le=44.0)
    net_profile: NetProfile = Field(default_factory=NetProfile)
    holdout_control_points: list[NetProfileControlPoint] = Field(default_factory=list)
    views: list[SceneViewCalibration] = Field(default_factory=list)
    provenance: SceneCalibrationSource = "manual"
    quality: SceneCameraQuality = Field(default_factory=SceneCameraQuality)
    fallback_metric_validity: MetricValidity = "unavailable"
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    rejection_reasons: list[str] = Field(default_factory=list)


class MetricCourtSceneDraftRequest(BaseModel):
    canonical_frame_id: str | None = None
    net_profile: NetProfile = Field(default_factory=NetProfile)
    holdout_control_points: list[NetProfileControlPoint] = Field(default_factory=list)
    views: list[SceneViewCalibration] = Field(default_factory=list)
    provenance: SceneCalibrationSource = "manual"


class MetricCourtSceneValidationResponse(BaseModel):
    capture_take_id: str
    status: Literal["ready", "degraded", "invalidated"]
    quality: SceneCameraQuality
    rejection_reasons: list[str] = Field(default_factory=list)
    scene: MetricCourtSceneCalibration


class MetricCourtSceneRevisionSummary(BaseModel):
    revision: int
    status: SceneCalibrationStatus
    provenance: SceneCalibrationSource
    created_at: datetime
    published_at: datetime | None = None
