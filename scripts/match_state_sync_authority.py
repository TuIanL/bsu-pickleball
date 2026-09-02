"""离线比赛状态特征使用的同步 authority adapter。

映射公式、校准解析和 source-frame 选择全部来自旧系统的
``backend/app/services/dual_camera_sync.py``。本模块只负责把相同的规则
应用到已经落盘的 PTS 和结构化特征记录，不实现第二套同步算法。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from bisect import bisect_left
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_SELECTION_ERROR_MS = 1000.0 / 30.0
DEFAULT_FEATURE_SELECTION_GAP_MS = 60.0
SYNC_SCHEMA_VERSION = "dual_camera_sync_calibration.v1"


def _load_system_sync_module() -> Any:
    """加载当前系统的旧同步核心；远程 runner 使用其同步快照。"""

    candidates: list[Path] = []
    configured = os.environ.get("MATCH_STATE_SYSTEM_SYNC_CORE")
    if configured:
        candidates.append(Path(configured))
    script_root = Path(__file__).resolve().parent
    candidates.extend(
        [
            script_root / "system_sync" / "dual_camera_sync.py",
            Path(__file__).resolve().parents[1] / "backend" / "app" / "services" / "dual_camera_sync.py",
        ]
    )
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("match_state_system_dual_camera_sync", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    raise RuntimeError(
        "找不到旧同步核心 dual_camera_sync.py；请设置 MATCH_STATE_SYSTEM_SYNC_CORE，"
        "不能在离线 runner 中退回自写 offset/rate 公式"
    )


_SYSTEM_SYNC = _load_system_sync_module()
FrameTiming = _SYSTEM_SYNC.FrameTiming
FrameSelection = _SYSTEM_SYNC.FrameSelection


def calibration_from_dict(payload: dict[str, Any]) -> Any:
    return _SYSTEM_SYNC.calibration_from_dict(payload)


def map_reference_time(calibration: Any, reference_time_seconds: float) -> float:
    return float(_SYSTEM_SYNC.map_reference_time(calibration, reference_time_seconds))


def build_frame_map(*args: Any, **kwargs: Any) -> list[Any]:
    return _SYSTEM_SYNC.build_frame_map(*args, **kwargs)


def read_frame_timing_sidecar(path: Path) -> list[Any]:
    return _SYSTEM_SYNC.read_frame_timing_sidecar(path)


@dataclass(frozen=True)
class SourceTiming:
    camera_id: str
    frames: tuple[Any, ...]
    by_index: dict[int, Any]
    pts_seconds: tuple[float, ...]

    @classmethod
    def from_sidecar(cls, camera_id: str, path: Path) -> SourceTiming:
        raw_frames = read_frame_timing_sidecar(path)
        if not raw_frames:
            raise ValueError(f"PTS sidecar 为空: {path}")
        first = float(raw_frames[0].pts_seconds)
        frames = tuple(replace(frame, pts_seconds=float(frame.pts_seconds) - first) for frame in raw_frames)
        by_index = {int(frame.frame_index): frame for frame in frames}
        if len(by_index) != len(frames):
            raise ValueError(f"PTS sidecar frame_index 重复: {path}")
        return cls(
            camera_id=camera_id,
            frames=frames,
            by_index=by_index,
            pts_seconds=tuple(float(frame.pts_seconds) for frame in frames),
        )

    @property
    def first_timestamp_seconds(self) -> float:
        return float(self.frames[0].pts_seconds)

    @property
    def last_timestamp_seconds(self) -> float:
        return float(self.frames[-1].pts_seconds)


@dataclass(frozen=True)
class FeatureTiming:
    timestamp_seconds: float
    source_frame_index: int
    record: dict[str, Any]


@dataclass(frozen=True)
class SyncFeatureSelection:
    camera_role: str
    camera_id: str
    target_source_pts_seconds: float
    source_frame_index: int | None
    source_pts_seconds: float | None
    source_alignment_error_seconds: float | None
    feature_source_frame_index: int | None
    feature_pts_seconds: float | None
    feature_alignment_error_seconds: float | None
    sync_status: str
    mapping_mode: str
    sync_quality: str
    timing_authority: str
    reason: str | None = None

    @property
    def usable(self) -> bool:
        return self.feature_source_frame_index is not None and self.sync_status != "unavailable"


def feature_timings(records: list[dict[str, Any]], source_timing: SourceTiming) -> list[FeatureTiming]:
    result: list[FeatureTiming] = []
    for record in records:
        raw_index = record.get("decoded_frame_index")
        if raw_index is None:
            continue
        frame = source_timing.by_index.get(int(raw_index))
        if frame is None:
            continue
        result.append(
            FeatureTiming(
                timestamp_seconds=float(frame.pts_seconds),
                source_frame_index=int(raw_index),
                record=record,
            )
        )
    result.sort(key=lambda item: item.timestamp_seconds)
    if not result:
        raise ValueError(f"结构化缓存没有可绑定到 source PTS 的记录: {source_timing.camera_id}")
    return result


def nearest_feature(
    records: list[FeatureTiming],
    target_seconds: float,
    max_gap_seconds: float,
    timestamps: list[float] | tuple[float, ...] | None = None,
) -> tuple[FeatureTiming | None, float | None]:
    if timestamps is None:
        timestamps = [item.timestamp_seconds for item in records]
    position = bisect_left(timestamps, target_seconds)
    candidate_positions = [max(0, min(len(records) - 1, position + offset)) for offset in (-1, 0)]
    best = min(candidate_positions, key=lambda index: abs(timestamps[index] - target_seconds))
    delta = timestamps[best] - target_seconds
    if abs(delta) > max_gap_seconds:
        return None, delta
    return records[best], delta


class CanonicalFeatureClock:
    """将 reference source PTS 映射为各视角的 feature-cache 观测。"""

    def __init__(
        self,
        *,
        sync_entry: dict[str, Any],
        source_timings: dict[str, SourceTiming],
        feature_timings_by_role: dict[str, list[FeatureTiming]],
        max_source_selection_error_ms: float = DEFAULT_SOURCE_SELECTION_ERROR_MS,
        max_feature_selection_gap_ms: float = DEFAULT_FEATURE_SELECTION_GAP_MS,
    ) -> None:
        self.sync_entry = sync_entry
        self.source_timings = source_timings
        self.feature_timings_by_role = feature_timings_by_role
        self.max_source_selection_error_seconds = max_source_selection_error_ms / 1000.0
        self.max_feature_selection_gap_seconds = max_feature_selection_gap_ms / 1000.0
        self.reference_camera_id = str(sync_entry["reference_camera_id"])
        self.sync_revision = str(sync_entry["sync_revision"])
        self._camera_by_role = {str(item["camera_role"]): str(item["camera_id"]) for item in sync_entry["cameras"]}
        self._mapping_by_camera_id = {
            str(item["camera_id"]): calibration_from_dict(dict(item["mapping"])) for item in sync_entry["cameras"]
        }
        self._feature_by_frame = {
            role: {item.source_frame_index: item for item in records}
            for role, records in feature_timings_by_role.items()
        }
        self._feature_timestamps = {
            role: tuple(item.timestamp_seconds for item in records) for role, records in feature_timings_by_role.items()
        }
        if set(self._camera_by_role) != {"cam_1", "cam_2"}:
            raise ValueError("sync entry 必须明确包含 cam_1 和 cam_2")
        if self.reference_camera_id not in self._mapping_by_camera_id:
            raise ValueError(f"sync entry 缺少 reference mapping: {self.reference_camera_id}")

    def _source_selection(self, role: str, canonical_seconds: float) -> SyncFeatureSelection:
        camera_id = self._camera_by_role[role]
        source_timing = self.source_timings[role]
        mapping = self._mapping_by_camera_id[camera_id]
        target_seconds = canonical_seconds
        mapping_mode = "reference"
        sync_status = "authoritative"
        sync_quality = str(getattr(mapping, "quality", "unknown"))
        if camera_id != self.reference_camera_id:
            target_seconds = map_reference_time(mapping, canonical_seconds)
            mapping_mode = "affine_mapping"
            in_valid_span = (
                mapping.valid_start_seconds is None or canonical_seconds >= mapping.valid_start_seconds
            ) and (mapping.valid_end_seconds is None or canonical_seconds <= mapping.valid_end_seconds)
            if not in_valid_span:
                mapping_mode = "affine_extrapolation"
                sync_status = "extrapolated"
                relaxed = replace(mapping, valid_start_seconds=None, valid_end_seconds=None)
                selection = self._nearest_source_selection(canonical_seconds, source_timing, relaxed)
            else:
                if sync_quality != "good":
                    sync_status = "degraded"
                selection = self._nearest_source_selection(canonical_seconds, source_timing, mapping)
        else:
            selection = self._nearest_source_selection(canonical_seconds, source_timing, None)
        if selection.status != "ok" or selection.source_frame_index is None:
            return SyncFeatureSelection(
                camera_role=role,
                camera_id=camera_id,
                target_source_pts_seconds=target_seconds,
                source_frame_index=None,
                source_pts_seconds=None,
                source_alignment_error_seconds=selection.selection_error_seconds,
                feature_source_frame_index=None,
                feature_pts_seconds=None,
                feature_alignment_error_seconds=None,
                sync_status="unavailable",
                mapping_mode=mapping_mode,
                sync_quality=sync_quality,
                timing_authority="source_pts",
                reason=selection.status,
            )
        selected_frame = source_timing.by_index.get(int(selection.source_frame_index))
        feature, feature_delta = nearest_feature(
            self.feature_timings_by_role[role],
            target_seconds,
            self.max_feature_selection_gap_seconds,
            self._feature_timestamps[role],
        )
        if feature is None:
            return SyncFeatureSelection(
                camera_role=role,
                camera_id=camera_id,
                target_source_pts_seconds=target_seconds,
                source_frame_index=int(selection.source_frame_index),
                source_pts_seconds=None if selected_frame is None else float(selected_frame.pts_seconds),
                source_alignment_error_seconds=selection.selection_error_seconds,
                feature_source_frame_index=None,
                feature_pts_seconds=None,
                feature_alignment_error_seconds=feature_delta,
                sync_status="unavailable",
                mapping_mode=mapping_mode,
                sync_quality=sync_quality,
                timing_authority="source_pts",
                reason="feature_sample_gap_exceeded",
            )
        return SyncFeatureSelection(
            camera_role=role,
            camera_id=camera_id,
            target_source_pts_seconds=target_seconds,
            source_frame_index=int(selection.source_frame_index),
            source_pts_seconds=None if selected_frame is None else float(selected_frame.pts_seconds),
            source_alignment_error_seconds=selection.selection_error_seconds,
            feature_source_frame_index=feature.source_frame_index,
            feature_pts_seconds=feature.timestamp_seconds,
            feature_alignment_error_seconds=feature_delta,
            sync_status=sync_status,
            mapping_mode=mapping_mode,
            sync_quality=sync_quality,
            timing_authority="source_pts",
        )

    def select(self, role: str, canonical_seconds: float) -> tuple[SyncFeatureSelection, dict[str, Any] | None]:
        selection = self._source_selection(role, canonical_seconds)
        feature = self._feature_by_frame[role].get(selection.feature_source_frame_index)
        record = None if feature is None else feature.record
        return selection, record

    def _nearest_source_selection(
        self,
        canonical_seconds: float,
        source_timing: SourceTiming,
        calibration: Any | None,
    ) -> Any:
        """按旧 build_frame_map 的选择语义做二分查找优化。

        旧核心仍提供 calibration 解析和 affine 映射；这里仅把其逐目标的
        O(n) 最近帧扫描优化为 O(log n)，保留范围、误差和 tie-break 规则。
        """
        target = canonical_seconds
        if calibration is not None:
            if calibration.valid_start_seconds is not None and target < calibration.valid_start_seconds:
                return FrameSelection(canonical_seconds, None, None, None, "unavailable_outside_valid_interval")
            if calibration.valid_end_seconds is not None and target > calibration.valid_end_seconds:
                return FrameSelection(canonical_seconds, None, None, None, "unavailable_outside_valid_interval")
            target = map_reference_time(calibration, target)
        if target < source_timing.frames[0].pts_seconds or target > source_timing.frames[-1].pts_seconds:
            return FrameSelection(canonical_seconds, None, None, None, "unavailable_out_of_media_range")
        timestamps = source_timing.pts_seconds
        position = bisect_left(timestamps, target)
        candidates = [max(0, min(len(timestamps) - 1, position + offset)) for offset in (-1, 0)]
        index = min(candidates, key=lambda candidate: abs(timestamps[candidate] - target))
        error = timestamps[index] - target
        status = "ok" if abs(error) <= self.max_source_selection_error_seconds else "unavailable_selection_error"
        frame = source_timing.frames[index]
        return FrameSelection(canonical_seconds, int(frame.frame_index), float(frame.pts_seconds), error, status)

    def canonical_ticks(self, fps: float) -> list[tuple[float, int]]:
        """由 reference source PTS 产生规则采样目标，再落到真实 reference 帧。"""
        if fps <= 0:
            raise ValueError("canonical fps 必须为正数")
        reference = self.source_timings["cam_1"]
        step = 1.0 / fps
        target = 0.0
        result: list[tuple[float, int]] = []
        seen_frames: set[int] = set()
        while target <= reference.last_timestamp_seconds + 1e-9:
            selection = self._nearest_source_selection(target, reference, None)
            if selection.status == "ok" and selection.source_frame_index is not None:
                frame = reference.by_index[int(selection.source_frame_index)]
                if int(frame.frame_index) not in seen_frames:
                    result.append((float(frame.pts_seconds), int(frame.frame_index)))
                    seen_frames.add(int(frame.frame_index))
            target += step
        if not result:
            raise ValueError("reference source PTS 无法生成 canonical ticks")
        return result


def sync_status_priority(status: str) -> int:
    return {"authoritative": 0, "degraded": 1, "extrapolated": 2, "unavailable": 3}.get(status, 3)


def joint_sync_status(selections: list[SyncFeatureSelection]) -> str:
    if not selections or any(item.sync_status == "unavailable" for item in selections):
        return "unavailable"
    return max((item.sync_status for item in selections), key=sync_status_priority)
