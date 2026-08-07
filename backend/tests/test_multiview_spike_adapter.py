"""P0 Spike 数据源适配器测试 —— 读取 render trajectory v2、过滤 observed、canonical 归一化。"""

from __future__ import annotations

import json

import pytest

from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.spike_adapter import (
    SpikeAdapterError,
    canonicalize_view_observations,
    extract_render_observations,
    load_render_payload,
    load_view_observations,
)


def _sample(*, frame_index, timestamp, x, y, source, player_id, projection_status="inside_court"):
    return {
        "sequence_index": frame_index,
        "frame_index": frame_index,
        "timestamp_seconds": timestamp,
        "x_ft": x,
        "y_ft": y,
        "source": source,
        "confidence": 0.8,
        "player_id": player_id,
        "render_slot": "slot_1",
        "side": "near",
        "segment_id": "seg_1",
        "identity_epoch": 0,
        "source_track_id": 7,
        "projection_status": projection_status,
        "projection_confidence": 0.7,
        "footpoint_method": "bbox_bottom_center",
    }


def _payload(samples):
    return {
        "schema_version": "player-render-trajectory.v2",
        "players": [],
        "segments": [],
        "samples": samples,
    }


def test_extract_filters_interpolated_only():
    samples = [
        _sample(frame_index=0, timestamp=0.0, x=1.0, y=2.0, source="observed", player_id="Player_1"),
        _sample(frame_index=1, timestamp=1 / 30.0, x=3.0, y=4.0, source="interpolated", player_id="Player_1"),
    ]
    observations = extract_render_observations(_payload(samples), view_id="cam_1")
    assert len(observations) == 1
    assert observations[0].source_frame_index == 0
    assert observations[0].local_x_ft == 1.0
    assert observations[0].local_y_ft == 2.0
    assert observations[0].projection_confidence == 0.7
    assert observations[0].footpoint_method == "bbox_bottom_center"
    assert observations[0].source_track_id == 7


def test_load_render_payload_rejects_wrong_schema(tmp_path):
    path = tmp_path / "render.json"
    path.write_text(json.dumps({"schema_version": "other.v1", "samples": []}), encoding="utf-8")
    with pytest.raises(SpikeAdapterError, match="schema"):
        load_render_payload(path)


def test_load_view_observations_smoke_assertion(tmp_path):
    # 只有 interpolated → require_observed 冒烟断言触发，避免 Spike 静默滤光。
    path = tmp_path / "render.json"
    interp_only = [
        _sample(frame_index=0, timestamp=0.0, x=1.0, y=2.0, source="interpolated", player_id="Player_1")
    ]
    path.write_text(json.dumps(_payload(interp_only)), encoding="utf-8")
    with pytest.raises(SpikeAdapterError, match="observed"):
        load_view_observations(path, view_id="cam_1")

    # 有一个 observed 即通过。
    mixed = [
        _sample(frame_index=0, timestamp=0.0, x=1.0, y=2.0, source="observed", player_id="Player_1"),
        _sample(frame_index=1, timestamp=1 / 30.0, x=3.0, y=4.0, source="interpolated", player_id="Player_1"),
    ]
    path.write_text(json.dumps(_payload(mixed)), encoding="utf-8")
    observations = load_view_observations(path, view_id="cam_1")
    assert len(observations) == 1


def test_canonicalize_view_observations():
    samples = [
        _sample(frame_index=0, timestamp=0.0, x=4.0, y=8.0, source="observed", player_id="Player_1"),
        _sample(frame_index=1, timestamp=1 / 30.0, x=6.0, y=10.0, source="observed", player_id="Player_1"),
    ]
    observations = extract_render_observations(_payload(samples), view_id="cam_1")
    canonical = canonicalize_view_observations(observations, CourtOrientation.mirror_y)
    # mirror_y: (x, 44 - y)
    assert canonical[0] == pytest.approx((4.0, 36.0))
    assert canonical[1] == pytest.approx((6.0, 34.0))


def test_canonicalize_requires_orientation():
    observations = extract_render_observations(
        _payload([_sample(frame_index=0, timestamp=0.0, x=1.0, y=2.0, source="observed", player_id="Player_1")]),
        view_id="cam_1",
    )
    with pytest.raises(SpikeAdapterError, match="court_orientation"):
        canonicalize_view_observations(observations, None)
