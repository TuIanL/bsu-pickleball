import json
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.dual_camera_sync import (
    FrameTiming,
    build_frame_map,
    fit_affine_calibration,
    calibrations_from_anchor_rows,
    write_frame_timing_sidecar,
    read_frame_timing_sidecar,
    retime_filter_expression,
)


def test_fit_affine_calibration_reports_offset_and_drift():
    calibration = fit_affine_calibration(
        [0.0, 10.0, 20.0],
        [0.050, 10.051, 20.052],
        reference_camera="174",
        camera_id="175",
    )

    assert calibration.offset_ms == pytest.approx(50.0)
    assert calibration.drift_ppm == pytest.approx(100.0)
    assert calibration.quality == "good"


def test_fit_affine_calibration_rejects_insufficient_anchors():
    calibration = fit_affine_calibration(
        [0.0], [0.05], reference_camera="174", camera_id="175"
    )

    assert calibration.quality == "unknown"
    assert calibration.anchor_count == 1


def test_build_frame_map_applies_camera_mapping():
    calibration = fit_affine_calibration(
        [0.0, 10.0], [0.050, 10.050], reference_camera="174", camera_id="175"
    )
    frames = [FrameTiming(i, i / 60) for i in range(601)]
    selected = build_frame_map([0.0, 1.0], frames, calibration=calibration)

    assert selected[0].source_frame_index == 3
    assert selected[1].source_frame_index == 63
    assert all(item.status == "ok" for item in selected)


def test_build_frame_map_marks_out_of_range_targets_unavailable():
    frames = [FrameTiming(i, i / 60) for i in range(61)]

    selected = build_frame_map([-1.0, 0.0, 1.0, 2.0], frames)

    assert selected[0].status == "unavailable"
    assert selected[1].status == "ok"
    assert selected[2].status == "ok"
    assert selected[3].status == "unavailable"


def test_calibrations_from_anchor_rows_fits_each_camera():
    mappings = calibrations_from_anchor_rows(
        [{"174": 0.0, "175": 0.05}, {"174": 10.0, "175": 10.051}],
        reference_camera="174",
        camera_ids=["174", "175"],
    )

    assert mappings["174"].offset_ms == pytest.approx(0.0)
    assert mappings["175"].drift_ppm == pytest.approx(100.0)


def test_retime_filter_expression_uses_offset_and_rate():
    calibration = fit_affine_calibration(
        [0.0, 10.0], [0.05, 10.051], reference_camera="174", camera_id="175"
    )

    expression = retime_filter_expression(calibration)

    assert expression.startswith("setpts=(PTS-STARTPTS-")
    assert "/1.000100000000" in expression


def test_write_frame_timing_sidecar_is_atomic(tmp_path: Path):
    sidecar = tmp_path / "frames.jsonl"
    fake = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"frames": [
            {"best_effort_timestamp_time": "1.400000", "pkt_dts_time": "1.400000", "key_frame": 1},
            {"best_effort_timestamp_time": "1.416667", "pkt_dts_time": "1.416667", "key_frame": 0},
        ]}),
        stderr="",
    )
    with patch("app.services.dual_camera_sync.subprocess.run", return_value=fake):
        summary = write_frame_timing_sidecar("source.ts", sidecar)

    rows = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert summary["frame_count"] == 2
    assert rows[0]["frame_index"] == 0
    assert rows[0]["pts_seconds"] == pytest.approx(1.4)
    assert rows[0]["keyframe"] is True
    assert rows[1]["pts_seconds"] == pytest.approx(1.416667)
    assert rows[1]["keyframe"] is False
    assert read_frame_timing_sidecar(sidecar)[1].frame_index == 1
