"""MultiView 同步契约 —— 权威 artifact 加载、质量门控、"无 artifact ≠ offset_ms=0"。"""

from __future__ import annotations

import json

import pytest

from app.services.dual_camera_sync import SyncCalibration, calibration_to_dict
from app.vision.multiview.sync import (
    MultiViewSyncCalibration,
    evaluate_sync_gate,
    load_sync_calibration,
    resolve_sync_authority,
    sync_calibration_path,
    validate_sync_authority,
)
from app.services.frame_timing_provider import FrameTimingProvider


def _sync(reference_camera: str, camera_id: str, quality: str, offset_ms: float = 500.0) -> SyncCalibration:
    return SyncCalibration(
        reference_camera=reference_camera,
        camera_id=camera_id,
        offset_seconds=offset_ms / 1000.0,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.001 if quality == "good" else 0.05,
        anchor_count=2,
        quality=quality,
        reason=None if quality == "good" else "anchor fit residual exceeds threshold",
        valid_start_seconds=0.0,
        valid_end_seconds=90.0,
    )


def test_evaluate_sync_gate_good_fuses():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_1": _sync("cam_1", "cam_1", "good"), "cam_2": _sync("cam_1", "cam_2", "good")},
    )
    decision, reason = evaluate_sync_gate(sync)
    assert decision == "fuse"
    assert "good" in reason


def test_evaluate_sync_gate_degraded_fuses_with_diagnostic():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_1": _sync("cam_1", "cam_1", "good"), "cam_2": _sync("cam_1", "cam_2", "degraded")},
    )
    decision, reason = evaluate_sync_gate(sync)
    assert decision == "fuse_degraded"
    assert "degraded" in reason


def test_evaluate_sync_gate_unknown_single_view():
    decision, reason = evaluate_sync_gate(None)
    assert decision == "single_view"
    assert "unavailable" in reason

    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", "unknown")},
    )
    decision, reason = evaluate_sync_gate(sync)
    assert decision == "single_view"
    assert "unknown" in reason


def test_worst_quality_takes_worst_across_cameras():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={
            "cam_1": _sync("cam_1", "cam_1", "good"),
            "cam_2": _sync("cam_1", "cam_2", "degraded"),
        },
    )
    assert sync.worst_quality() == "degraded"


def test_load_sync_calibration_round_trip(tmp_path):
    # 构造权威 dual_camera_sync_calibration.v1 文件。
    mappings = {
        "cam_1": calibration_to_dict(_sync("cam_1", "cam_1", "good")),
        "cam_2": calibration_to_dict(_sync("cam_1", "cam_2", "good")),
    }
    payload = {
        "schema_version": "dual_camera_sync_calibration.v1",
        "reference_camera": "cam_1",
        "anchor_count": 2,
        "mappings": mappings,
    }
    path = sync_calibration_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    loaded = load_sync_calibration(tmp_path)
    assert loaded is not None
    assert loaded.reference_camera == "cam_1"
    assert loaded.mapping_for("cam_2") is not None
    assert loaded.mapping_for("cam_2").quality == "good"


def test_load_sync_calibration_missing_returns_none(tmp_path):
    # 缺 artifact ≠ offset_ms=0：返回 None（sync authority unavailable）。
    assert load_sync_calibration(tmp_path) is None


def test_load_sync_calibration_corrupt_returns_none(tmp_path):
    path = sync_calibration_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert load_sync_calibration(tmp_path) is None


def test_validate_sync_authority_requires_exact_secondary_identity():
    sync = MultiViewSyncCalibration(
        reference_camera="hardware-ref",
        mappings={"hardware-other": _sync("hardware-ref", "hardware-other", "good")},
    )
    result = validate_sync_authority(
        sync,
        reference_camera_id="hardware-ref",
        secondary_camera_id="hardware-secondary",
    )
    assert not result.valid
    assert {issue.code for issue in result.issues} == {"secondary_mapping_missing"}


def test_validate_sync_authority_rejects_invalid_numeric_quality_and_range():
    bad = SyncCalibration(
        reference_camera="ref",
        camera_id="sec",
        offset_seconds=0.0,
        rate=0.0,
        drift_ppm=0.0,
        residual_rms_seconds=float("nan"),
        anchor_count=-1,
        quality="broken",
        valid_start_seconds=3.0,
        valid_end_seconds=1.0,
    )
    result = validate_sync_authority(
        MultiViewSyncCalibration(reference_camera="ref", mappings={"sec": bad}),
        reference_camera_id="ref",
        secondary_camera_id="sec",
    )
    assert not result.valid
    assert {issue.code for issue in result.issues} >= {
        "rate_invalid",
        "residual_invalid",
        "anchor_count_invalid",
        "quality_invalid",
        "valid_range_invalid",
    }


def test_resolve_sync_authority_good_is_authoritative_joint():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", "good")},
    )
    result = resolve_sync_authority(
        sync,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
    )
    assert result.structural_valid
    assert result.sync_quality == "good"
    assert result.execution_mode == "joint_authoritative"
    assert result.authoritative_joint_eligible


def test_visual_acceptance_requires_manual_three_anchor_calibration():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", "good")},
        anchor_count=2,
        source="auto_degraded_from_recording_timing",
    )
    result = resolve_sync_authority(
        sync,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
        require_authoritative_calibration=True,
    )
    assert not result.structural_valid
    assert not result.authoritative_joint_eligible
    assert "manual_anchor_calibration_required" in result.reason_codes
    assert "anchor_count_insufficient" in result.reason_codes


def test_visual_acceptance_accepts_valid_manual_anchor_metadata():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", "good")},
        anchor_count=4,
        source="manual_anchors",
        anchor_validation={"valid": True, "issues": []},
    )
    result = resolve_sync_authority(
        sync,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
        require_authoritative_calibration=True,
    )
    assert result.execution_mode == "joint_authoritative"
    assert result.authoritative_joint_eligible


def test_resolve_sync_authority_degraded_is_non_authoritative_joint():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", "degraded")},
    )
    result = resolve_sync_authority(
        sync,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
    )
    assert result.execution_mode == "joint_degraded"
    assert not result.authoritative_joint_eligible


@pytest.mark.parametrize("quality", ["unknown"])
def test_resolve_sync_authority_unknown_or_invalid_falls_back(quality):
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", quality)},
    )
    result = resolve_sync_authority(
        sync,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
    )
    assert result.execution_mode == "single_view_fallback"
    assert not result.authoritative_joint_eligible

    missing_mapping = resolve_sync_authority(
        None,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
    )
    assert missing_mapping.execution_mode == "single_view_fallback"
    assert not missing_mapping.structural_valid


def test_resolve_sync_authority_nominal_is_compatibility_only():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", "good")},
    )
    result = resolve_sync_authority(
        sync,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "legacy_nominal_fps"},
    )
    assert result.execution_mode == "compatibility_degraded"
    assert not result.authoritative_joint_eligible
    assert "nominal_timing_not_authoritative" in result.reason_codes


def test_missing_provider_does_not_create_nominal_timestamps(tmp_path):
    provider = FrameTimingProvider.from_media(
        tmp_path / "camera.mp4",
        frame_count=3,
        fps=30.0,
        allow_nominal_fallback=False,
    )
    assert provider.provenance.authority == "missing"
    assert provider.frames == ()


def test_missing_timing_authority_blocks_authoritative_joint_even_with_good_mapping():
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": _sync("cam_1", "cam_2", "good")},
    )
    result = resolve_sync_authority(
        sync,
        reference_camera_id="cam_1",
        secondary_camera_id="cam_2",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "missing"},
    )
    assert result.execution_mode == "single_view_fallback"
    assert result.sync_quality == "unavailable"
    assert "timing_authority_unavailable" in result.reason_codes
