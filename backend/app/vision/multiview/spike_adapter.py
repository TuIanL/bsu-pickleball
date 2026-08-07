"""P0 Spike Adapter（spike_adapter）—— 读取现有单视角 render trajectory，产出真实观测。

数据源契约（已核验）：
- `player_render_trajectory.json` 的 `schema_version` 为 `player-render-trajectory.v2`；
- 每 sample 的 `source ∈ {"observed", "interpolated"}`（**不是 "detector"/"detected"**）；
- 无 `bbox` 字段；`x_ft/y_ft` 为 raw（未平滑）；
- 过滤 `source == "observed"` 得到真实观测（避免插值点互相证明）。
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
from app.vision.multiview.types import ViewObservation

# render trajectory v2 的 source 枚举：真实检测为 observed，补帧为 interpolated。
RENDER_SOURCE_OBSERVED = "observed"
RENDER_SOURCE_INTERPOLATED = "interpolated"
RENDER_SCHEMA_VERSION = "player-render-trajectory.v2"


class SpikeAdapterError(ValueError):
    """Spike 数据源读取/校验失败。"""


def load_render_payload(path: str | os.PathLike[str]) -> dict[str, object]:
    """读取 render trajectory JSON 并校验 schema 版本。"""
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpikeAdapterError(f"cannot read render trajectory artifact: {file_path}") from exc
    if not isinstance(payload, dict):
        raise SpikeAdapterError(f"render trajectory artifact is not a JSON object: {file_path}")
    schema = payload.get("schema_version")
    if schema != RENDER_SCHEMA_VERSION:
        raise SpikeAdapterError(
            f"unexpected render trajectory schema {schema!r} (expected {RENDER_SCHEMA_VERSION!r})"
        )
    return payload


def extract_render_observations(
    payload: dict[str, object],
    *,
    view_id: str,
) -> list[ViewObservation]:
    """从 render trajectory 中取出真实观测（source == "observed"）。

    保留 raw `x_ft/y_ft` 与 `projection_status / projection_confidence /
    footpoint_method / source_track_id`，作为 Spike ViewObservation 输入。
    """
    observations: list[ViewObservation] = []
    samples = payload.get("samples")
    if not isinstance(samples, list):
        return observations
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("source") != RENDER_SOURCE_OBSERVED:
            continue
        observations.append(
            ViewObservation(
                view_id=view_id,
                source_frame_index=int(sample.get("frame_index", 0)),
                timestamp_seconds=float(sample.get("timestamp_seconds", 0.0)),
                local_x_ft=float(sample.get("x_ft", 0.0)),
                local_y_ft=float(sample.get("y_ft", 0.0)),
                view_player_id=str(sample.get("player_id", "")),
                projection_status=sample.get("projection_status"),
                projection_confidence=safe_float(sample.get("projection_confidence")),
                footpoint_method=sample.get("footpoint_method"),
                source_track_id=sample.get("source_track_id"),
                confidence=safe_float(sample.get("confidence")),
            )
        )
    return observations


def load_view_observations(
    path: str | os.PathLike[str],
    *,
    view_id: str,
    require_observed: bool = True,
) -> list[ViewObservation]:
    """读文件 + 取真实观测 + 冒烟断言。

    `require_observed=True` 时，若没有任何 observed sample（例如过滤枚举写错导致全部被滤掉），
    抛 SpikeAdapterError，避免 Spike 静默失败。
    """
    payload = load_render_payload(path)
    observations = extract_render_observations(payload, view_id=view_id)
    if require_observed and not observations:
        raise SpikeAdapterError(
            "no observed samples found; check source filter (expected source == 'observed')"
        )
    return observations


def canonicalize_view_observations(
    observations: Sequence[ViewObservation],
    orientation: CourtOrientation | None,
) -> list[tuple[float, float]]:
    """把一路真实观测的 local 坐标经 court_orientation 变换为 canonical 坐标。"""
    if orientation is None:
        raise SpikeAdapterError("court_orientation is None: cannot canonicalize spike observations")
    return [
        local_to_canonical(obs.local_x_ft, obs.local_y_ft, orientation) for obs in observations
    ]


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
