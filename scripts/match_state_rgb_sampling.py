"""Dependency-free RGB manifest timebase helpers."""
from __future__ import annotations

from typing import Any


def experiment_id_for_manifest(rgb_manifest: dict[str, Any]) -> str:
    if rgb_manifest.get("schema_version") == "match_state_rgb_canonical_sync_manifest.v2":
        return "rgb_only_v2_canonical_sync"
    return "rgb_only_v1"



def sample_timestamp_ms(clip: dict[str, Any], view: dict[str, Any], offset: int, fps: float) -> float:
    """将 canonical clip 内的采样偏移映射到当前 view 的本地 RGB cache 时间。"""
    start_ms = float(view.get("mapped_start_ms", clip["requested_start_ms"]))
    rate = float(view.get("canonical_to_local_rate", 1.0))
    return start_ms + offset * 1000.0 / fps * rate
