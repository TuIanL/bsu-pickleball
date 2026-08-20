"""Frame-time indexing and explicit calibration for dual-camera recordings.

The MPEG-TS PTS written by the current recorder is local to each file. This
module therefore treats frame PTS as per-camera timing and only creates a
cross-camera mapping when explicit calibration anchors are supplied.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class FrameTiming:
    frame_index: int
    pts_seconds: float
    dts_seconds: float | None = None
    keyframe: bool = False


@dataclass(frozen=True)
class SyncCalibration:
    reference_camera: str
    camera_id: str
    offset_seconds: float
    rate: float
    drift_ppm: float
    residual_rms_seconds: float
    anchor_count: int
    quality: str
    reason: str | None = None
    # anchor evidence span：人工同步锚点所覆盖的 reference-camera 时间区间 [start, end]。
    # 仅表示"有直接证据验证 affine mapping"的范围，并非 Cam-2 媒体可用的有效窗口。
    # 锚点区间外的 canonical tick 仍可能映射到 Cam-2 真实媒体帧（外推显示），
    # 见 analysis_clock._select_extrapolated_display_frame。字段名/读写保持历史 artifact 兼容。
    valid_start_seconds: float | None = None
    valid_end_seconds: float | None = None

    @property
    def offset_ms(self) -> float:
        return self.offset_seconds * 1000.0


@dataclass(frozen=True)
class FrameSelection:
    target_time_seconds: float
    source_frame_index: int | None
    source_pts_seconds: float | None
    selection_error_seconds: float | None
    status: str


def write_frame_timing_sidecar(
    media_path: str | os.PathLike[str],
    sidecar_path: str | os.PathLike[str],
    *,
    ffprobe_bin: str = "ffprobe",
) -> dict[str, object]:
    """Export decoded video frame timing as compact JSONL without changing media."""
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time,pkt_dts_time,key_frame",
            "-of",
            "json",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(60, int(os.environ.get("PICKLEBALL_PTS_PROBE_TIMEOUT_SECONDS", "3600"))),
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "ffprobe failed").strip()[-2000:])

    target = Path(sidecar_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    first: float | None = None
    last: float | None = None
    previous_pts: float | None = None
    count = 0
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".part",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        try:
            payload = json.loads(result.stdout or "{}")
            raw_frames = payload.get("frames", [])
            if not isinstance(raw_frames, list) or not raw_frames:
                raise ValueError("ffprobe returned no video frames with usable PTS")
            for frame in raw_frames:
                raw_pts = frame.get("best_effort_timestamp_time")
                if raw_pts in (None, "", "N/A"):
                    continue
                pts = float(raw_pts)
                if not math.isfinite(pts):
                    raise ValueError("frame PTS must be finite")
                if previous_pts is not None and pts < previous_pts:
                    raise ValueError("frame PTS must be monotonically non-decreasing")
                raw_dts = frame.get("pkt_dts_time")
                dts = None if raw_dts in (None, "", "N/A") else float(raw_dts)
                if dts is not None and not math.isfinite(dts):
                    raise ValueError("frame DTS must be finite")
                keyframe = int(frame.get("key_frame", 0)) == 1
                row = {
                    "frame_index": count,
                    "pts_seconds": pts,
                    "dts_seconds": dts,
                    "keyframe": keyframe,
                }
                handle.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n")
                first = pts if first is None else first
                last = pts
                previous_pts = pts
                count += 1
            if count == 0:
                raise ValueError("ffprobe returned no video frames with usable PTS")
            handle.flush()
            os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)

    duration = (last - first) if first is not None and last is not None else 0.0
    return {
        "status": "ready",
        "timing_authority": "source_pts",
        "provenance": "ffprobe_frame_pts",
        "media_path": str(media_path),
        "sidecar_path": str(target),
        "frame_count": count,
        "fps": (count - 1) / duration if count > 1 and duration > 0 else None,
        "first_pts_seconds": first,
        "last_pts_seconds": last,
    }


def read_frame_timing_sidecar(sidecar_path: str | os.PathLike[str]) -> list[FrameTiming]:
    frames: list[FrameTiming] = []
    with Path(sidecar_path).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            frames.append(
                FrameTiming(
                    frame_index=int(row["frame_index"]),
                    pts_seconds=float(row["pts_seconds"]),
                    dts_seconds=None if row.get("dts_seconds") is None else float(row["dts_seconds"]),
                    keyframe=bool(row.get("keyframe", False)),
                )
            )
    return frames


def summarize_frame_timing_sidecar(
    sidecar_path: str | os.PathLike[str],
    *,
    media_path: str | os.PathLike[str] | None = None,
    require_bound_path: bool = False,
) -> dict[str, object]:
    """Validate an existing sidecar and expose the same readiness contract."""
    if require_bound_path and media_path is not None:
        expected = Path(f"{Path(media_path)}.pts.jsonl")
        if Path(sidecar_path).resolve(strict=False) != expected.resolve(strict=False):
            raise ValueError(f"PTS sidecar is not bound to registered video: expected {expected}")
    frames = read_frame_timing_sidecar(sidecar_path)
    if not frames:
        raise ValueError("PTS sidecar is empty")
    previous_index = -1
    previous_pts: float | None = None
    for frame in frames:
        if frame.frame_index <= previous_index:
            raise ValueError("frame indices must be strictly increasing")
        if not math.isfinite(frame.pts_seconds):
            raise ValueError("frame PTS must be finite")
        if previous_pts is not None and frame.pts_seconds < previous_pts:
            raise ValueError("frame PTS must be monotonically non-decreasing")
        previous_index = frame.frame_index
        previous_pts = frame.pts_seconds
    first = frames[0].pts_seconds
    last = frames[-1].pts_seconds
    duration = last - first
    return {
        "status": "ready",
        "timing_authority": "source_pts",
        "provenance": "ffprobe_frame_pts",
        "media_path": str(media_path) if media_path is not None else None,
        "sidecar_path": str(sidecar_path),
        "frame_count": len(frames),
        "fps": (len(frames) - 1) / duration if len(frames) > 1 and duration > 0 else None,
        "first_pts_seconds": first,
        "last_pts_seconds": last,
    }


def fit_affine_calibration(
    reference_times: Sequence[float],
    camera_times: Sequence[float],
    *,
    reference_camera: str,
    camera_id: str,
    max_residual_seconds: float = 1 / 30,
    minimum_anchor_count: int = 2,
) -> SyncCalibration:
    """Fit ``camera_time = offset + rate * reference_time`` from anchors."""
    if len(reference_times) != len(camera_times) or len(reference_times) < 2:
        return SyncCalibration(
            reference_camera,
            camera_id,
            0.0,
            1.0,
            0.0,
            math.inf,
            min(len(reference_times), len(camera_times)),
            "unknown",
            "at least two paired anchors are required",
        )
    pairs = list(zip(reference_times, camera_times, strict=False))
    x_mean = sum(x for x, _ in pairs) / len(pairs)
    y_mean = sum(y for _, y in pairs) / len(pairs)
    denominator = sum((x - x_mean) ** 2 for x, _ in pairs)
    rate = 1.0 if denominator == 0 else sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denominator
    offset = y_mean - rate * x_mean
    residuals = [y - (offset + rate * x) for x, y in pairs]
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    if len(pairs) < minimum_anchor_count:
        quality = "degraded"
        reason = f"at least {minimum_anchor_count} paired anchors are required for authoritative calibration"
    else:
        quality = "good" if rms <= max_residual_seconds else "degraded"
        reason = None if quality == "good" else "anchor fit residual exceeds threshold"
    return SyncCalibration(
        reference_camera=reference_camera,
        camera_id=camera_id,
        offset_seconds=offset,
        rate=rate,
        drift_ppm=(rate - 1.0) * 1_000_000,
        residual_rms_seconds=rms,
        anchor_count=len(pairs),
        quality=quality,
        reason=reason,
        valid_start_seconds=min(reference_times),
        valid_end_seconds=max(reference_times),
    )


def map_reference_time(calibration: SyncCalibration, reference_time_seconds: float) -> float:
    return calibration.offset_seconds + calibration.rate * reference_time_seconds


def calibrations_from_anchor_rows(
    anchor_rows: Sequence[dict[str, object]],
    *,
    reference_camera: str,
    camera_ids: Sequence[str],
    max_residual_seconds: float = 1 / 30,
    minimum_anchor_count: int = 2,
) -> dict[str, SyncCalibration]:
    """Fit one mapping per camera from explicit shared-event observations."""
    result: dict[str, SyncCalibration] = {}
    for camera_id in camera_ids:
        reference_times: list[float] = []
        camera_times: list[float] = []
        for row in anchor_rows:
            ref_value = row.get(reference_camera)
            camera_value = row.get(camera_id)
            if ref_value is None or camera_value is None:
                continue
            reference_times.append(float(ref_value))
            camera_times.append(float(camera_value))
        result[camera_id] = fit_affine_calibration(
            reference_times,
            camera_times,
            reference_camera=reference_camera,
            camera_id=camera_id,
            max_residual_seconds=max_residual_seconds,
            minimum_anchor_count=minimum_anchor_count,
        )
    return result


def validate_anchor_payload(
    payload: object,
    *,
    minimum_anchor_count: int = 3,
) -> list[str]:
    """Validate the auditable input contract for manual shared-event anchors.

    The fitter remains usable with two points for backwards-compatible unit
    callers.  This validator is the gate used by the manual calibration CLI,
    where at least three events are required to support a drift claim.
    """
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["anchor payload must be a JSON object"]
    reference = str(payload.get("reference_camera", "")).strip()
    if not reference:
        issues.append("reference_camera is required")
    raw_cameras = payload.get("cameras")
    cameras = [str(value).strip() for value in raw_cameras] if isinstance(raw_cameras, list) else []
    cameras = list(dict.fromkeys(camera for camera in cameras if camera))
    if reference and reference not in cameras:
        cameras.insert(0, reference)
    if len(cameras) < 2:
        issues.append("at least two camera identities are required")
    raw_anchors = payload.get("anchors")
    anchors = raw_anchors if isinstance(raw_anchors, list) else []
    if len(anchors) < minimum_anchor_count:
        issues.append(f"at least {minimum_anchor_count} shared-event anchors are required")
    valid_reference_times: list[float] = []
    for index, row in enumerate(anchors):
        if not isinstance(row, dict):
            issues.append(f"anchor {index} must be an object keyed by camera identity")
            continue
        for camera in cameras:
            value = row.get(camera)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                issues.append(f"anchor {index}/{camera} must be numeric")
                continue
            if not math.isfinite(numeric):
                issues.append(f"anchor {index}/{camera} must be finite")
            if camera == reference and math.isfinite(numeric):
                valid_reference_times.append(numeric)
        if reference and row.get(reference) is not None:
            for camera in cameras:
                if camera == reference:
                    continue
                if row.get(camera) is None:
                    continue
                # The row is a usable pair for this camera only if both values
                # were numeric; malformed values are reported above.
                try:
                    if math.isfinite(float(row[reference])) and math.isfinite(float(row[camera])):
                        pass
                except (TypeError, ValueError):
                    pass
    if len(valid_reference_times) >= 2 and max(valid_reference_times) <= min(valid_reference_times):
        issues.append("anchors must span a positive reference-camera time range")
    for camera in cameras:
        paired = 0
        for row in anchors:
            if not isinstance(row, dict) or row.get(reference) is None or row.get(camera) is None:
                continue
            try:
                if math.isfinite(float(row[reference])) and math.isfinite(float(row[camera])):
                    paired += 1
            except (TypeError, ValueError):
                continue
        if paired < minimum_anchor_count:
            issues.append(f"camera {camera} has only {paired} usable paired anchors")
    return list(dict.fromkeys(issues))


def build_dual_camera_sync_calibration(
    payload: object,
    *,
    max_residual_seconds: float = 1 / 30,
    minimum_anchor_count: int = 3,
) -> dict[str, object]:
    """Build the stable CLI/API calibration artifact from one anchor payload.

    Validation intentionally stays separate from fitting so maintenance callers
    can preserve the historical CLI behavior of writing a diagnostic artifact
    even when the payload is not confirmable.
    """
    if not isinstance(payload, dict):
        payload = {}
    reference = str(payload.get("reference_camera", "")).strip()
    raw_cameras = payload.get("cameras", [])
    cameras = [str(camera).strip() for camera in raw_cameras] if isinstance(raw_cameras, list) else []
    if reference and reference not in cameras:
        cameras.insert(0, reference)
    cameras = list(dict.fromkeys(camera for camera in cameras if camera))
    anchors = payload.get("anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    issues = validate_anchor_payload(payload, minimum_anchor_count=minimum_anchor_count)
    calibrations = calibrations_from_anchor_rows(
        anchors,
        reference_camera=reference,
        camera_ids=cameras,
        max_residual_seconds=max(0.0, max_residual_seconds),
        minimum_anchor_count=minimum_anchor_count,
    )
    return {
        "schema_version": "dual_camera_sync_calibration.v1",
        "reference_camera": reference,
        "anchor_count": len(anchors),
        "source": "manual_anchors",
        "anchor_validation": {"valid": not issues, "issues": issues},
        "mappings": {camera: calibration_to_dict(value) for camera, value in calibrations.items()},
    }


def derive_sync_calibration_from_segment_timing(
    segments: Sequence[object],
) -> dict[str, object]:
    """从双摄录制各 segment 的 `input_start_time` 推导 degraded 同步校准。

    与手动锚点（`calibrations_from_anchor_rows`，权威路径）不同：本函数由录制时序元数据
    推导两机位媒体时间轴的 offset（同一真实事件 wall T → cam_2 = cam_1 + (start_1 - start_2)），
    **quality 恒为 degraded**（未经人工锚点校验，不冒充 authoritative good；
    按 P0 门控 `degraded → 允许融合但降权并输出诊断`）。

    `segments` 为 duck-typed：每个 segment 需有 `.files`，文件需有 `.role / .input_start_time / .media_duration_sec`。
    """
    offset_seconds: float | None = None
    duration_sec = 0.0
    for segment in segments:
        files_by_role: dict[str, object] = {}
        for file_ in getattr(segment, "files", []):
            role = getattr(file_, "role", None)
            if role is not None:
                files_by_role[str(role)] = file_
        f1 = files_by_role.get("cam_1")
        f2 = files_by_role.get("cam_2")
        if not f1 or not f2:
            continue
        s1 = getattr(f1, "input_start_time", None)
        s2 = getattr(f2, "input_start_time", None)
        if s1 is None or s2 is None:
            continue
        duration_sec = min(
            float(getattr(f1, "media_duration_sec", 0.0) or 0.0),
            float(getattr(f2, "media_duration_sec", 0.0) or 0.0),
        )
        if duration_sec <= 0:
            continue
        offset_seconds = float(s1) - float(s2)
        reference_camera_id = str(getattr(f1, "camera_id", None) or "cam_1")
        secondary_camera_id = str(getattr(f2, "camera_id", None) or "cam_2")
        break

    if offset_seconds is None:
        raise ValueError("no usable segment timing metadata (input_start_time) found")

    anchors = [
        {reference_camera_id: 0.0, secondary_camera_id: offset_seconds},
        {reference_camera_id: duration_sec, secondary_camera_id: duration_sec + offset_seconds},
    ]
    calibrations = calibrations_from_anchor_rows(
        anchors,
        reference_camera=reference_camera_id,
        camera_ids=[reference_camera_id, secondary_camera_id],
    )
    calibrations = {
        camera_id: replace(
            cal,
            quality="degraded",
            reason="auto-derived from recording timing (input_start_time); not anchor-verified",
        )
        for camera_id, cal in calibrations.items()
    }
    return {
        "schema_version": "dual_camera_sync_calibration.v1",
        "reference_camera": reference_camera_id,
        "anchor_count": len(anchors),
        "mappings": {camera_id: calibration_to_dict(cal) for camera_id, cal in calibrations.items()},
        "source": "auto_degraded_from_recording_timing",
    }


def calibration_to_dict(calibration: SyncCalibration) -> dict[str, object]:
    return {
        "reference_camera": calibration.reference_camera,
        "camera_id": calibration.camera_id,
        "offset_ms": calibration.offset_ms,
        "rate": calibration.rate,
        "drift_ppm": calibration.drift_ppm,
        "residual_rms_ms": calibration.residual_rms_seconds * 1000.0,
        "anchor_count": calibration.anchor_count,
        "quality": calibration.quality,
        "reason": calibration.reason,
        "valid_start_seconds": calibration.valid_start_seconds,
        "valid_end_seconds": calibration.valid_end_seconds,
    }


def calibration_from_dict(payload: dict[str, object]) -> SyncCalibration:
    return SyncCalibration(
        reference_camera=str(payload["reference_camera"]),
        camera_id=str(payload["camera_id"]),
        offset_seconds=float(payload.get("offset_ms", 0.0)) / 1000.0,
        rate=float(payload.get("rate", 1.0)),
        drift_ppm=float(payload.get("drift_ppm", 0.0)),
        residual_rms_seconds=float(payload.get("residual_rms_ms", math.inf)) / 1000.0,
        anchor_count=int(payload.get("anchor_count", 0)),
        quality=str(payload.get("quality", "unknown")),
        reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
        valid_start_seconds=None
        if payload.get("valid_start_seconds") is None
        else float(payload["valid_start_seconds"]),
        valid_end_seconds=None if payload.get("valid_end_seconds") is None else float(payload["valid_end_seconds"]),
    )


def retime_filter_expression(calibration: SyncCalibration) -> str:
    """Return an FFmpeg setpts expression mapping local time to reference time."""
    # PTS is normalized to each file's start before applying the calibration.
    return f"setpts=(PTS-STARTPTS-{calibration.offset_seconds:.9f}/TB)/{calibration.rate:.12f}"


def build_frame_map(
    target_times: Iterable[float],
    frames: Sequence[FrameTiming],
    *,
    calibration: SyncCalibration | None = None,
    max_selection_error_seconds: float = 1 / 30,
) -> list[FrameSelection]:
    """Select the nearest local frame for each target time on a camera timeline."""
    if not frames:
        return [FrameSelection(t, None, None, None, "unavailable") for t in target_times]
    ordered = sorted(frames, key=lambda frame: frame.pts_seconds)
    selections: list[FrameSelection] = []
    for target in target_times:
        if calibration is not None:
            if calibration.valid_start_seconds is not None and target < calibration.valid_start_seconds:
                selections.append(FrameSelection(target, None, None, None, "unavailable_outside_valid_interval"))
                continue
            if calibration.valid_end_seconds is not None and target > calibration.valid_end_seconds:
                selections.append(FrameSelection(target, None, None, None, "unavailable_outside_valid_interval"))
                continue
        local_target = target if calibration is None else map_reference_time(calibration, target)
        if local_target < ordered[0].pts_seconds or local_target > ordered[-1].pts_seconds:
            selections.append(FrameSelection(target, None, None, None, "unavailable_out_of_media_range"))
            continue
        nearest = min(ordered, key=lambda frame: abs(frame.pts_seconds - local_target))
        error = nearest.pts_seconds - local_target
        status = "ok" if abs(error) <= max_selection_error_seconds else "unavailable_selection_error"
        selections.append(FrameSelection(target, nearest.frame_index, nearest.pts_seconds, error, status))
    return selections
