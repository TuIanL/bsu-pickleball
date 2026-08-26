"""Repair persisted multiview Player overlays without rerunning inference.

Older completed joint jobs may contain a v1 overlay whose top-level frames are
valid for the reference view but which has no per-view payloads.  The joint run
already persists the immutable evidence needed to project the same canonical
players into every calibrated camera, so those jobs can be upgraded in place.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from app.schemas.analysis import AnalysisJobSummary
from app.services.calibration_service import CalibrationService
from app.services.storage_service import StorageService
from app.vision.multiview.bootstrap_display_backfill import BootstrapBackfillObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.fused_overlay_builder import FusedPlayerOverlayBuilder
from app.vision.multiview.fused_overlay_bundle import ViewGeometry, build_overlay_evidence_bundle
from app.vision.multiview.fused_overlay_types import (
    FusedPlayerOverlayView,
    build_fused_player_overlay_payload,
)
from app.vision.multiview.offline_refinement import F0RefinementSnapshot, RecoveredViewObservation


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _input_value(item: object, *names: str) -> Any:
    if isinstance(item, Mapping):
        for name in names:
            if item.get(name) is not None:
                return item.get(name)
    for name in names:
        value = getattr(item, name, None)
        if value is not None:
            return value
    return None


def _load_recovered_observations(path: Path) -> list[RecoveredViewObservation]:
    payload = _read_json(path)
    if not payload:
        return []
    observations: list[RecoveredViewObservation] = []
    for raw in payload.get("observations", []) or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            observations.append(
                RecoveredViewObservation(
                    view_id=str(raw.get("view_id", "")),
                    take_timestamp_ms=float(raw.get("take_timestamp_ms", 0.0)),
                    source_frame_index=int(raw.get("source_frame_index", 0)),
                    canonical_x_ft=float(raw.get("canonical_x_ft", 0.0)),
                    canonical_y_ft=float(raw.get("canonical_y_ft", 0.0)),
                    bbox=tuple(float(value) for value in raw.get("bbox", ())),
                    confidence=float(raw.get("confidence", 0.0)),
                    detection_origin=str(raw.get("detection_origin", "offline_refinement")),
                    global_player_id=str(raw.get("global_player_id", "")),
                    canonical_tick=int(raw.get("canonical_tick", 0)),
                    source_timestamp_ms=(
                        float(raw["source_timestamp_ms"])
                        if raw.get("source_timestamp_ms") is not None
                        else None
                    ),
                    mapped_take_timestamp_ms=(
                        float(raw["mapped_take_timestamp_ms"])
                        if raw.get("mapped_take_timestamp_ms") is not None
                        else None
                    ),
                    selection_error_ms=(
                        float(raw["selection_error_ms"])
                        if raw.get("selection_error_ms") is not None
                        else None
                    ),
                    timing_authority=str(raw.get("timing_authority", "missing")),
                    sync_quality=str(raw.get("sync_quality", "unknown")),
                    donor_view=(str(raw["donor_view"]) if raw.get("donor_view") is not None else None),
                    donor_source_frame_index=(
                        int(raw["donor_source_frame_index"])
                        if raw.get("donor_source_frame_index") is not None
                        else None
                    ),
                    donor_quality=float(raw.get("donor_quality", 0.0)),
                    expected_global_position=(
                        tuple(float(value) for value in raw["expected_global_position"][:2])
                        if isinstance(raw.get("expected_global_position"), (list, tuple))
                        and len(raw["expected_global_position"]) >= 2
                        else None
                    ),
                    residual_ft=(float(raw["residual_ft"]) if raw.get("residual_ft") is not None else None),
                    suppression_reason=(
                        str(raw["suppression_reason"])
                        if raw.get("suppression_reason") is not None
                        else None
                    ),
                )
            )
        except (TypeError, ValueError):
            continue
    return observations


def _load_bootstrap_backfill(path: Path) -> list[BootstrapBackfillObservation]:
    payload = _read_json(path)
    if not payload:
        return []
    observations: list[BootstrapBackfillObservation] = []
    for raw in payload.get("observations", []) or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            observations.append(BootstrapBackfillObservation(**dict(raw)))
        except (TypeError, ValueError):
            continue
    return observations


def repair_persisted_multiview_overlay(
    job: AnalysisJobSummary,
    *,
    storage: StorageService | None = None,
) -> dict[str, object] | None:
    """Build and persist a v2 overlay from an existing joint run.

    Returns ``None`` when the immutable run evidence is unavailable or cannot
    be reconstructed.  No tracker, association, metric, or roster artifact is
    changed; only ``fused_player_overlay.json`` is upgraded.
    """

    if job.analysisKind != "multiview" or not job.jointRunId or not job.referenceViewId:
        return None
    storage = storage or StorageService()
    root = storage._job_artifact_root(job.id)  # noqa: SLF001 - service-owned path resolver
    run_dir = storage.multiview_run_dir(job.id, job.jointRunId)
    snapshot_payload = _read_json(run_dir / "f0_refinement_snapshot.v1.json")
    if snapshot_payload is None:
        return None
    snapshot = F0RefinementSnapshot.from_dict(snapshot_payload)

    refinement = _read_json(run_dir / "refinement_diagnostics.json") or {}
    final_source = str(refinement.get("final_source") or "first_pass_f0")
    trajectory_path = run_dir / "fused_player_trajectory.f1.v2.json"
    if final_source != "refined_f1" or not trajectory_path.exists():
        trajectory_path = run_dir / "fused_player_trajectory.f0.v2.json"
    trajectory = _read_json(trajectory_path)
    if trajectory is None:
        return None

    roster = _read_json(root / "roster.json") or {}
    roster_map = {
        str(item.get("global_player_id")): str(item.get("player_id"))
        for item in roster.get("players", []) or []
        if isinstance(item, Mapping) and item.get("global_player_id") and item.get("player_id")
    }
    if not roster_map:
        return None

    geometry: dict[str, ViewGeometry] = {}
    video_ids: dict[str, str] = {}
    frame_sizes: dict[str, dict[str, int]] = {}
    calibration_service = CalibrationService(storage)
    for raw_input in job.jointViewInputs or []:
        view_id = str(_input_value(raw_input, "cameraSlot", "camera_slot") or "")
        calibration_id = str(_input_value(raw_input, "calibrationId", "calibration_id") or "")
        if not view_id or not calibration_id:
            continue
        calibration = calibration_service.get_calibration(calibration_id)
        if calibration is None or calibration.inverse_homography is None:
            continue
        orientation_value = _input_value(raw_input, "courtOrientation", "court_orientation")
        try:
            orientation = CourtOrientation(str(orientation_value))
        except (TypeError, ValueError):
            continue
        width = int(_input_value(raw_input, "imageWidth", "image_width") or 0)
        height = int(_input_value(raw_input, "imageHeight", "image_height") or 0)
        geometry[view_id] = ViewGeometry(
            view_id=view_id,
            orientation=orientation,
            inverse_homography=np.asarray(calibration.inverse_homography.values, dtype=float),
            frame_width=width,
            frame_height=height,
        )
        video_id = _input_value(raw_input, "videoId", "video_id")
        if video_id:
            video_ids[view_id] = str(video_id)
        frame_sizes[view_id] = {"width": width, "height": height}
    if job.referenceViewId not in geometry:
        return None

    bundle = build_overlay_evidence_bundle(
        f0_snapshot=snapshot,
        reference_view_id=job.referenceViewId,
        roster_map=roster_map,
        view_geometry=geometry,
        fused_trajectory=trajectory,
        recovered_observations=_load_recovered_observations(run_dir / "recovered_view_observations.v1.json"),
        final_source=final_source,
        bootstrap_backfill=_load_bootstrap_backfill(root / "bootstrap_display_backfill.json"),
    )
    expected_player_count = int(roster.get("expected_player_count") or len(roster_map) or 4)
    view_payloads: dict[str, FusedPlayerOverlayView] = {}
    builders: dict[str, FusedPlayerOverlayBuilder] = {}
    view_ids = [view_id for view_id in snapshot.view_ids if view_id in geometry]
    if job.referenceViewId not in view_ids:
        view_ids.insert(0, job.referenceViewId)
    for view_id in view_ids:
        builder = FusedPlayerOverlayBuilder()
        frames = builder.build(
            bundle=bundle,
            expected_player_count=expected_player_count,
            target_view_id=view_id,
        )
        builders[view_id] = builder
        view_payloads[view_id] = FusedPlayerOverlayView(
            view_id=view_id,
            video_id=video_ids.get(view_id),
            status="available" if any(frame.players for frame in frames) else "no_detections",
            detail=(
                f"已生成 {len(frames)} 帧 {view_id} image-space Player overlay；"
                "身份与 canonical tick 复用同一份 joint evidence"
            ),
            source=frame_sizes.get(view_id, {}),
            frames=frames,
        )

    reference_view = view_payloads.get(job.referenceViewId)
    if reference_view is None:
        return None
    payload = build_fused_player_overlay_payload(
        job_id=job.id,
        video_id=job.videoId,
        reference_view_id=job.referenceViewId,
        frame_size=frame_sizes.get(job.referenceViewId),
        frames=reference_view.frames,
        status=reference_view.status,
        detail=(
            f"已生成 {len(reference_view.frames)} 帧 fused overlay（{expected_player_count} 名 canonical 球员，"
            f"包含 {len(view_payloads)} 个展示视角；来源 persisted F0/F1 evidence + roster + view geometry）"
        ),
        diagnostics={
            "view_ids": view_ids,
            "view_diagnostics": {
                view_id: dict(getattr(builder, "diagnostics", {}) or {})
                for view_id, builder in builders.items()
            },
            "repair": {
                "source": "persisted_joint_run",
                "joint_run_id": job.jointRunId,
                "final_source": final_source,
            },
        },
        views=view_payloads,
        schema_version="multiview-fused-player-overlay.v2",
    )
    output_path = storage.fused_player_overlay_json_path(job.id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    storage.write_json_atomic(output_path, payload)
    return payload
