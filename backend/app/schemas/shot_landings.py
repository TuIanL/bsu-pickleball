"""Shot 级首次正式落点 artifact 契约。"""

from __future__ import annotations

from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.shot_rally_events import ArtifactStatus

LandingStatus = Literal[
    "available",
    "no_bounce_before_next_contact",
    "bounce_without_court_coordinate",
    "ambiguous_bounce",
    "unavailable",
]
CourtLocation = Literal["inside_court", "outside_court", "unknown"]
TargetRelation = Literal["target_half", "own_half", "unknown"]
CanonicalizationBasis = Literal[
    "hitter_position_at_contact", "trajectory_direction", "unavailable"
]
OrientationTransform = Literal["identity", "rotate_180", "unavailable"]


class LandingCoordinateSystem(BaseModel):
    source: Literal["canonical_court_ft"] = "canonical_court_ft"
    court_width_ft: float = 20.0
    court_length_ft: float = 44.0
    net_y_ft: float = 22.0


class LandingProfileSnapshot(BaseModel):
    profile_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ShotLanding(BaseModel):
    landing_id: str
    shot_id: str
    rally_id: str | None = None
    ordinal_in_rally: int | None = Field(default=None, ge=1)
    bounce_event_id: str | None = None
    frame_index: int | None = Field(default=None, ge=0)
    timestamp_ms: int | None = Field(default=None, ge=0)
    hitter_player_id: str | None = None
    shot_stage: str | None = None

    landing_status: LandingStatus
    landing_x_ft: float | None = None
    landing_y_ft: float | None = None
    court_location: CourtLocation = "unknown"
    target_relation: TargetRelation = "unknown"

    target_half: Literal["near", "far"] | None = None
    orientation_transform: OrientationTransform = "unavailable"
    target_x_ft: float | None = None
    target_y_ft: float | None = None
    landing_u: float | None = None
    landing_v: float | None = None

    zone_12_id: int | None = Field(default=None, ge=1, le=12)
    zone_12: str | None = None
    zone_12_profile: str | None = None
    zone_6: str | None = None
    zone_6_profile: str | None = None

    landing_source: str = "unavailable"
    bounce_confidence: float | None = Field(default=None, ge=0, le=1)
    geometry_quality: float | None = Field(default=None, ge=0, le=1)
    calibration_uncertainty_ft: float | None = Field(default=None, ge=0)
    canonicalization_basis: CanonicalizationBasis = "unavailable"
    source_segment_id: str | None = None
    source_event_id: str | None = None
    source_artifacts: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> ShotLanding:
        coords = (self.landing_x_ft, self.landing_y_ft)
        has_coords = all(value is not None and isfinite(value) for value in coords)
        if self.landing_status == "available" and not has_coords:
            raise ValueError("available landing requires finite absolute court coordinates")
        if self.landing_status == "bounce_without_court_coordinate" and has_coords:
            raise ValueError("bounce_without_court_coordinate cannot carry absolute coordinates")
        if self.zone_12 is not None:
            if not (
                self.landing_status == "available"
                and self.court_location == "inside_court"
                and self.target_relation == "target_half"
                and self.zone_12_profile == "project12.v1"
                and self.zone_12_id is not None
            ):
                raise ValueError("zone_12 requires an eligible project12.v1 landing")
        if self.canonicalization_basis == "unavailable":
            derived = (
                self.target_x_ft,
                self.target_y_ft,
                self.landing_u,
                self.landing_v,
                self.zone_12,
                self.zone_12_id,
            )
            if any(value is not None for value in derived):
                raise ValueError("unavailable canonicalization cannot carry normalized fields")
        if self.zone_6 is not None or self.zone_6_profile is not None:
            raise ValueError("paper6 profile is not configured in shot-landings.v1")
        return self


class ShotLandingSummary(BaseModel):
    shot_count: int = Field(default=0, ge=0)
    available_landing_count: int = Field(default=0, ge=0)
    formal_bounce_shot_count: int = Field(default=0, ge=0)
    spatially_measurable_count: int = Field(default=0, ge=0)
    no_bounce_before_next_contact_count: int = Field(default=0, ge=0)
    zone_eligible_count: int = Field(default=0, ge=0)
    spatial_measurability_numerator: int = Field(default=0, ge=0)
    spatial_measurability_denominator: int = Field(default=0, ge=0)
    spatial_measurability_rate: float | None = Field(default=None, ge=0, le=1)
    zone_12_counts: dict[str, int] = Field(default_factory=dict)


class ShotLandingDiagnostics(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    missing_segment_ids: list[str] = Field(default_factory=list)
    missing_event_ids: list[str] = Field(default_factory=list)


class ShotLandingsArtifact(BaseModel):
    schema_version: Literal["shot-landings.v1"] = "shot-landings.v1"
    job_id: str
    video_id: str | None = None
    status: ArtifactStatus
    detail: str
    generated_at: str
    coordinate_system: LandingCoordinateSystem = Field(default_factory=LandingCoordinateSystem)
    normalization_profile: LandingProfileSnapshot
    zone_profiles: dict[str, LandingProfileSnapshot | None]
    landings: list[ShotLanding] = Field(default_factory=list)
    summary: ShotLandingSummary = Field(default_factory=ShotLandingSummary)
    diagnostics: ShotLandingDiagnostics = Field(default_factory=ShotLandingDiagnostics)
    source_artifacts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_identity(self) -> ShotLandingsArtifact:
        landing_ids = [item.landing_id for item in self.landings]
        shot_ids = [item.shot_id for item in self.landings]
        if len(landing_ids) != len(set(landing_ids)):
            raise ValueError("landing_id must be unique within a job")
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("each canonical shot may have at most one ShotLanding record")
        return self
