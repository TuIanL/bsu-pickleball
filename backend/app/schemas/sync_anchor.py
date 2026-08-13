"""CaptureTake-level dual-camera sync anchor contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SyncAnchorState = Literal[
    "not_required",
    "required",
    "draft",
    "confirmed",
    "auto_degraded",
    "invalidated",
]
SyncAnchorSource = Literal["manual_anchors", "auto_degraded_from_recording_timing", "legacy", "none"]


class SyncAnchor(BaseModel):
    """One editable workbench row. Both snake_case and current UI camelCase are accepted."""

    id: str = ""
    label: str = ""
    note: str = ""
    frame_by_camera: dict[str, int] = Field(default_factory=dict)
    pts_by_camera: dict[str, float] = Field(default_factory=dict)
    created_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_workbench_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        aliases = {
            "frameByCamera": "frame_by_camera",
            "ptsByCamera": "pts_by_camera",
            "createdAt": "created_at",
        }
        for source, target in aliases.items():
            if target not in result and source in result:
                result[target] = result[source]
        return result


class SyncAnchorDraftRequest(BaseModel):
    reference_camera: str = Field(min_length=1)
    cameras: list[str] = Field(min_length=2, max_length=8)
    anchors: list[SyncAnchor] = Field(default_factory=list)
    expected_revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_camera_contract(self) -> SyncAnchorDraftRequest:
        self.cameras = list(dict.fromkeys(str(camera).strip() for camera in self.cameras if str(camera).strip()))
        if self.reference_camera not in self.cameras:
            self.cameras.insert(0, self.reference_camera)
        return self


class SyncAnchorExport(BaseModel):
    reference_camera: str
    cameras: list[str]
    anchors: list[dict[str, float]]


class SyncAnchorQualitySummary(BaseModel):
    anchor_count: int = Field(default=0, ge=0)
    coverage_ratio: float = Field(default=0.0, ge=0.0)
    residual_rms_ms: float | None = None
    quality: Literal["good", "degraded", "unknown"] = "unknown"
    valid_start_seconds: float | None = None
    valid_end_seconds: float | None = None
    reason: str | None = None


class SyncAnchorProvenance(BaseModel):
    capture_take_id: str
    slot: str
    camera_id: str
    registered_video_id: str
    media_identity: dict[str, Any] = Field(default_factory=dict)
    timing_sidecar_identity: dict[str, Any] = Field(default_factory=dict)
    timing_authority: str = "missing"
    frame_count: int | None = None
    first_pts_seconds: float | None = None
    last_pts_seconds: float | None = None


class SyncAnchorValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None
    anchor_index: int | None = None
    camera_id: str | None = None


class SyncAnchorStatus(BaseModel):
    capture_take_id: str
    state: SyncAnchorState
    analysis_allowed: bool
    reason_codes: list[str] = Field(default_factory=list)
    source: SyncAnchorSource = "none"
    revision: int = Field(default=0, ge=0)
    quality: SyncAnchorQualitySummary | None = None
    provenance: list[SyncAnchorProvenance] = Field(default_factory=list)
    provenance_fingerprint: str | None = None
    invalidation_reasons: list[str] = Field(default_factory=list)
    confirmed_at: datetime | None = None
    draft: SyncAnchorDraftRequest | None = None


class SyncAnchorDraftResponse(BaseModel):
    capture_take_id: str
    revision: int = Field(ge=0)
    draft: SyncAnchorDraftRequest
    status: SyncAnchorStatus


class SyncAnchorConfirmRequest(BaseModel):
    expected_revision: int = Field(default=0, ge=0)
    reference_camera: str = Field(min_length=1)
    cameras: list[str] = Field(min_length=2, max_length=8)
    anchors: list[SyncAnchor] = Field(default_factory=list)


class SyncAnchorConfirmResponse(BaseModel):
    status: SyncAnchorStatus
    calibration: dict[str, Any]
    anchors: SyncAnchorExport


class SyncAnchorError(BaseModel):
    code: str
    message: str
    current_revision: int | None = None
    issues: list[SyncAnchorValidationIssue] = Field(default_factory=list)
