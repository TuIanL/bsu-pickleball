"""多视角同步契约（sync）—— 权威 dual_camera_sync_calibration.v1 的引用、加载与质量门控。

复用 `app.services.dual_camera_sync` 既有的 `SyncCalibration` / `calibration_from_dict` /
`map_reference_time` / `build_frame_map`，本模块只负责把权威 artifact 接到 Multi-view 层，
并定义 `good / degraded / unknown` 门控。
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Literal

from app.services.capture_storage_service import sync_calibration_path
from app.services.dual_camera_sync import SyncCalibration, calibration_from_dict
from app.services.frame_timing_provider import TimingAuthority

# 权威同步校准 artifact 的 schema 版本。
SYNC_CALIBRATION_SCHEMA_VERSION = "dual_camera_sync_calibration.v1"


@dataclass(frozen=True)
class MultiViewSyncCalibration:
    """Multi-view 输入的权威时间同步契约。

    `mappings[camera_id]` 给出该 camera 的映射 `camera_time = offset + rate * reference_time`。
    """

    reference_camera: str
    mappings: dict[str, SyncCalibration] = field(default_factory=dict)
    schema_version: str = SYNC_CALIBRATION_SCHEMA_VERSION
    source_path: str | None = None
    anchor_count: int | None = None
    source: str | None = None
    anchor_validation: dict[str, object] | None = None

    def mapping_for(self, camera_id: str) -> SyncCalibration | None:
        return self.mappings.get(camera_id)

    def worst_quality(self) -> str:
        """跨全部 camera 的最差同步质量（good > degraded > unknown）。"""
        if not self.mappings:
            return "unknown"
        order = {"good": 0, "degraded": 1, "unknown": 2}
        worst = max(self.mappings.values(), key=lambda m: order.get(m.quality, 2))
        return worst.quality


SyncGateDecision = Literal["fuse", "fuse_degraded", "single_view"]
SyncQuality = Literal["good", "degraded", "unknown", "unavailable"]
ExecutionMode = Literal[
    "joint_authoritative",
    "joint_degraded",
    "compatibility_degraded",
    "single_view_fallback",
]


@dataclass(frozen=True)
class SyncAuthorityIssue:
    """同步 authority 的结构化校验问题。"""

    code: str
    message: str
    camera_id: str | None = None


@dataclass(frozen=True)
class SyncAuthorityValidation:
    """当前多视角 Parent 是否拥有可消费的同步 authority。"""

    valid: bool
    issues: tuple[SyncAuthorityIssue, ...] = ()
    reference_camera_id: str | None = None
    secondary_camera_id: str | None = None
    secondary_mapping: SyncCalibration | None = None


@dataclass(frozen=True)
class SyncAuthorityResolution:
    """Combined structural authority and runtime quality decision.

    Structural validity answers whether the requested reference/secondary
    mapping can be consumed.  ``sync_quality`` and ``execution_mode`` are
    deliberately separate so a degraded run remains executable without being
    reported as an authoritative joint run.
    """

    structural_valid: bool
    timing_authority_by_view: dict[str, TimingAuthority]
    sync_quality: SyncQuality
    execution_mode: ExecutionMode
    authoritative_joint_eligible: bool
    reason_codes: tuple[str, ...] = ()
    validation: SyncAuthorityValidation | None = None

    @property
    def authoritative_eligible(self) -> bool:
        """Compatibility spelling for callers using the shorter contract."""
        return self.authoritative_joint_eligible

    @property
    def mode(self) -> ExecutionMode:
        return self.execution_mode

    @property
    def reason(self) -> str | None:
        return "; ".join(self.reason_codes) or None


def resolve_sync_authority(
    sync: MultiViewSyncCalibration | None,
    *,
    reference_camera_id: str,
    secondary_camera_id: str,
    timing_authority_by_view: Mapping[str, str] | None = None,
    require_authoritative_calibration: bool = False,
) -> SyncAuthorityResolution:
    """Resolve the authority matrix used by a multi-view executor.

    The mapping is keyed by camera/view id.  When omitted, source PTS is
    assumed for backwards-compatible callers that only exercise calibration
    resolution; production executors pass the actual provider authorities.
    """
    validation = validate_sync_authority(
        sync,
        reference_camera_id=reference_camera_id,
        secondary_camera_id=secondary_camera_id,
        require_authoritative_calibration=require_authoritative_calibration,
    )
    authorities: dict[str, TimingAuthority] = {
        reference_camera_id: "source_pts",
        secondary_camera_id: "source_pts",
    }
    if timing_authority_by_view is not None:
        for camera_id in (reference_camera_id, secondary_camera_id):
            raw = str(timing_authority_by_view.get(camera_id, "missing"))
            authorities[camera_id] = raw if raw in {"source_pts", "legacy_nominal_fps", "missing"} else "missing"

    reasons = [issue.code for issue in validation.issues]
    if not validation.valid:
        missing_views = [camera_id for camera_id, authority in authorities.items() if authority == "missing"]
        if missing_views:
            reasons.append("timing_authority_unavailable")
            reasons.extend(f"{camera_id}_timing_authority_missing" for camera_id in missing_views)
        if not reasons:
            reasons.append("sync_authority_unavailable")
        return SyncAuthorityResolution(
            structural_valid=False,
            timing_authority_by_view=authorities,
            sync_quality="unavailable",
            execution_mode="single_view_fallback",
            authoritative_joint_eligible=False,
            reason_codes=tuple(dict.fromkeys(reasons)),
            validation=validation,
        )

    mapping = validation.secondary_mapping
    quality: SyncQuality = (
        mapping.quality if mapping is not None and mapping.quality in {"good", "degraded", "unknown"} else "unknown"
    )
    if mapping is not None and mapping.reason:
        reasons.append("mapping_reason_present")

    missing_views = [camera_id for camera_id, authority in authorities.items() if authority == "missing"]
    nominal_views = [
        camera_id for camera_id, authority in authorities.items() if authority == "legacy_nominal_fps"
    ]
    if missing_views:
        reasons.append("timing_authority_unavailable")
        reasons.extend(f"{camera_id}_timing_authority_missing" for camera_id in missing_views)
        mode: ExecutionMode = "single_view_fallback"
        quality = "unavailable"
    elif nominal_views:
        reasons.append("nominal_timing_not_authoritative")
        reasons.extend(f"{camera_id}_using_legacy_nominal_fps" for camera_id in nominal_views)
        mode = "compatibility_degraded"
    elif quality == "good":
        mode = "joint_authoritative"
        reasons.append("sync_quality_good")
    elif quality == "degraded":
        mode = "joint_degraded"
        reasons.append("sync_quality_degraded")
    else:
        mode = "single_view_fallback"
        reasons.append("sync_quality_unknown")

    eligible = mode == "joint_authoritative" and all(
        authority == "source_pts" for authority in authorities.values()
    )
    return SyncAuthorityResolution(
        structural_valid=True,
        timing_authority_by_view=authorities,
        sync_quality=quality,
        execution_mode=mode,
        authoritative_joint_eligible=eligible,
        reason_codes=tuple(dict.fromkeys(reasons)),
        validation=validation,
    )


def validate_sync_authority(
    sync: MultiViewSyncCalibration | None,
    *,
    reference_camera_id: str,
    secondary_camera_id: str,
    require_authoritative_calibration: bool = False,
) -> SyncAuthorityValidation:
    """严格验证当前 Parent 所需的 reference/secondary mapping。

    reference camera 的 mapping 可以省略，因为 reference timeline 本身是 canonical
    时钟；secondary mapping 则必须精确存在且身份一致。
    """

    issues: list[SyncAuthorityIssue] = []
    if sync is None:
        issues.append(SyncAuthorityIssue("sync_unavailable", "sync authority unavailable"))
        return SyncAuthorityValidation(False, tuple(issues), reference_camera_id, secondary_camera_id)
    if sync.schema_version != SYNC_CALIBRATION_SCHEMA_VERSION:
        issues.append(
            SyncAuthorityIssue(
                "schema_version_mismatch",
                f"expected {SYNC_CALIBRATION_SCHEMA_VERSION}, got {sync.schema_version}",
            )
        )
    if sync.reference_camera != reference_camera_id:
        issues.append(
            SyncAuthorityIssue(
                "reference_camera_mismatch",
                f"expected reference camera {reference_camera_id}, got {sync.reference_camera}",
                sync.reference_camera,
            )
        )

    if require_authoritative_calibration:
        if sync.source != "manual_anchors":
            issues.append(
                SyncAuthorityIssue(
                    "manual_anchor_calibration_required",
                    "authoritative acceptance requires a calibration generated from manual anchors",
                )
            )
        if sync.anchor_count is not None and sync.anchor_count < 3:
            issues.append(
                SyncAuthorityIssue(
                    "anchor_count_insufficient",
                    f"authoritative acceptance requires at least 3 anchors, got {sync.anchor_count}",
                )
            )
        if sync.anchor_validation is not None and sync.anchor_validation.get("valid") is not True:
            issues.append(
                SyncAuthorityIssue(
                    "anchor_validation_failed",
                    "manual anchor payload validation failed",
                )
            )

    mapping = sync.mapping_for(secondary_camera_id)
    if mapping is None:
        issues.append(
            SyncAuthorityIssue(
                "secondary_mapping_missing",
                f"mapping for secondary camera {secondary_camera_id} is missing",
                secondary_camera_id,
            )
        )
        return SyncAuthorityValidation(
            not issues,
            tuple(issues),
            reference_camera_id,
            secondary_camera_id,
            None,
        )

    if mapping.reference_camera != sync.reference_camera:
        issues.append(
            SyncAuthorityIssue(
                "mapping_reference_mismatch",
                "secondary mapping reference_camera differs from top-level reference_camera",
                secondary_camera_id,
            )
        )
    if mapping.camera_id != secondary_camera_id:
        issues.append(
            SyncAuthorityIssue(
                "mapping_camera_mismatch",
                f"mapping camera_id {mapping.camera_id} does not match {secondary_camera_id}",
                secondary_camera_id,
            )
        )
    if not math.isfinite(mapping.offset_seconds):
        issues.append(SyncAuthorityIssue("offset_not_finite", "mapping offset is not finite", secondary_camera_id))
    if not math.isfinite(mapping.rate) or mapping.rate <= 0:
        issues.append(SyncAuthorityIssue("rate_invalid", "mapping rate must be finite and positive", secondary_camera_id))
    if not math.isfinite(mapping.residual_rms_seconds) or mapping.residual_rms_seconds < 0:
        issues.append(
            SyncAuthorityIssue(
                "residual_invalid", "mapping residual_rms_seconds must be finite and non-negative", secondary_camera_id
            )
        )
    if mapping.anchor_count < 0:
        issues.append(SyncAuthorityIssue("anchor_count_invalid", "mapping anchor_count must be non-negative", secondary_camera_id))
    if mapping.quality not in {"good", "degraded", "unknown"}:
        issues.append(SyncAuthorityIssue("quality_invalid", f"unknown sync quality {mapping.quality!r}", secondary_camera_id))
    if mapping.valid_start_seconds is not None and not math.isfinite(mapping.valid_start_seconds):
        issues.append(SyncAuthorityIssue("valid_start_invalid", "valid_start_seconds is not finite", secondary_camera_id))
    if mapping.valid_end_seconds is not None and not math.isfinite(mapping.valid_end_seconds):
        issues.append(SyncAuthorityIssue("valid_end_invalid", "valid_end_seconds is not finite", secondary_camera_id))
    if (
        mapping.valid_start_seconds is not None
        and mapping.valid_end_seconds is not None
        and mapping.valid_end_seconds < mapping.valid_start_seconds
    ):
        issues.append(SyncAuthorityIssue("valid_range_invalid", "sync valid range is reversed", secondary_camera_id))

    return SyncAuthorityValidation(
        not issues,
        tuple(issues),
        reference_camera_id,
        secondary_camera_id,
        mapping,
    )


def evaluate_sync_gate(sync: MultiViewSyncCalibration | None) -> tuple[SyncGateDecision, str]:
    """按同步质量门控融合：

    - `good` → "fuse"（正常双视角融合）
    - `degraded` → "fuse_degraded"（允许融合，但降低时间同步质量权重并输出诊断）
    - `unknown / unavailable` → "single_view"（job-level 单视角 fallback，禁止伪装 synchronized）
    """
    if sync is None:
        return ("single_view", "sync authority unavailable")
    quality = sync.worst_quality()
    if quality == "good":
        return ("fuse", "sync quality good")
    if quality == "degraded":
        return ("fuse_degraded", "sync quality degraded: anchor fit residual exceeds threshold")
    return ("single_view", f"sync quality unknown: {sync.reference_camera} mapping unavailable")


def load_sync_calibration(take_dir: str | os.PathLike[str]) -> MultiViewSyncCalibration | None:
    """读取 take 目录下的权威同步校准；文件缺失或损坏返回 None（= sync authority unavailable）。"""
    path = sync_calibration_path(take_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    reference = str(payload.get("reference_camera", ""))
    mappings_raw = payload.get("mappings")
    if not reference or not isinstance(mappings_raw, dict):
        return None
    mappings: dict[str, SyncCalibration] = {}
    for camera_id, value in mappings_raw.items():
        if not isinstance(value, dict):
            continue
        try:
            mappings[camera_id] = calibration_from_dict(value)
        except (KeyError, TypeError, ValueError):
            continue
    return MultiViewSyncCalibration(
        reference_camera=reference,
        mappings=mappings,
        schema_version=str(payload.get("schema_version", SYNC_CALIBRATION_SCHEMA_VERSION)),
        source_path=str(path),
        anchor_count=(
            int(payload["anchor_count"])
            if payload.get("anchor_count") is not None
            else None
        ),
        source=str(payload.get("source")) if payload.get("source") is not None else None,
        anchor_validation=(
            dict(payload["anchor_validation"])
            if isinstance(payload.get("anchor_validation"), dict)
            else None
        ),
    )
