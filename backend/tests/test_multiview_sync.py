"""MultiView 同步契约 —— 权威 artifact 加载、质量门控、"无 artifact ≠ offset_ms=0"。"""

from __future__ import annotations

import json

from app.services.dual_camera_sync import SyncCalibration, calibration_to_dict
from app.vision.multiview.sync import (
    MultiViewSyncCalibration,
    evaluate_sync_gate,
    load_sync_calibration,
    sync_calibration_path,
    validate_sync_authority,
)


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
