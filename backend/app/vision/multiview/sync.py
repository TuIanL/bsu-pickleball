"""多视角同步契约（sync）—— 权威 dual_camera_sync_calibration.v1 的引用、加载与质量门控。

复用 `app.services.dual_camera_sync` 既有的 `SyncCalibration` / `calibration_from_dict` /
`map_reference_time` / `build_frame_map`，本模块只负责把权威 artifact 接到 Multi-view 层，
并定义 `good / degraded / unknown` 门控。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Literal

from app.services.capture_storage_service import sync_calibration_path
from app.services.dual_camera_sync import SyncCalibration, calibration_from_dict

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
    )
