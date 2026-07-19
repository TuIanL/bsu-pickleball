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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


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
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "frame=best_effort_timestamp_time,pkt_dts_time,key_frame",
            "-of", "json",
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
    count = 0
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent,
        prefix=f".{target.name}.", suffix=".part", delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        try:
            payload = json.loads(result.stdout or "{}")
            for frame in payload.get("frames", []):
                raw_pts = frame.get("best_effort_timestamp_time")
                if raw_pts in (None, "", "N/A"):
                    continue
                pts = float(raw_pts)
                raw_dts = frame.get("pkt_dts_time")
                dts = None if raw_dts in (None, "", "N/A") else float(raw_dts)
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
                count += 1
            handle.flush()
            os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)

    return {
        "media_path": str(media_path),
        "sidecar_path": str(target),
        "frame_count": count,
        "first_pts_seconds": first,
        "last_pts_seconds": last,
    }


def read_frame_timing_sidecar(sidecar_path: str | os.PathLike[str]) -> list[FrameTiming]:
    frames: list[FrameTiming] = []
    with Path(sidecar_path).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            frames.append(FrameTiming(
                frame_index=int(row["frame_index"]),
                pts_seconds=float(row["pts_seconds"]),
                dts_seconds=None if row.get("dts_seconds") is None else float(row["dts_seconds"]),
                keyframe=bool(row.get("keyframe", False)),
            ))
    return frames


def fit_affine_calibration(
    reference_times: Sequence[float],
    camera_times: Sequence[float],
    *,
    reference_camera: str,
    camera_id: str,
    max_residual_seconds: float = 1 / 30,
) -> SyncCalibration:
    """Fit ``camera_time = offset + rate * reference_time`` from anchors."""
    if len(reference_times) != len(camera_times) or len(reference_times) < 2:
        return SyncCalibration(
            reference_camera, camera_id, 0.0, 1.0, 0.0, math.inf,
            min(len(reference_times), len(camera_times)), "unknown", "at least two paired anchors are required",
        )
    pairs = list(zip(reference_times, camera_times))
    x_mean = sum(x for x, _ in pairs) / len(pairs)
    y_mean = sum(y for _, y in pairs) / len(pairs)
    denominator = sum((x - x_mean) ** 2 for x, _ in pairs)
    rate = 1.0 if denominator == 0 else sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denominator
    offset = y_mean - rate * x_mean
    residuals = [y - (offset + rate * x) for x, y in pairs]
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    quality = "good" if rms <= max_residual_seconds else "degraded"
    return SyncCalibration(
        reference_camera=reference_camera,
        camera_id=camera_id,
        offset_seconds=offset,
        rate=rate,
        drift_ppm=(rate - 1.0) * 1_000_000,
        residual_rms_seconds=rms,
        anchor_count=len(pairs),
        quality=quality,
        reason=None if quality == "good" else "anchor fit residual exceeds threshold",
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
        )
    return result


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
        valid_start_seconds=None if payload.get("valid_start_seconds") is None else float(payload["valid_start_seconds"]),
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
        local_target = target if calibration is None else map_reference_time(calibration, target)
        if local_target < ordered[0].pts_seconds - max_selection_error_seconds or local_target > ordered[-1].pts_seconds + max_selection_error_seconds:
            selections.append(FrameSelection(target, None, None, None, "unavailable"))
            continue
        nearest = min(ordered, key=lambda frame: abs(frame.pts_seconds - local_target))
        error = nearest.pts_seconds - local_target
        status = "ok" if abs(error) <= max_selection_error_seconds else "out_of_tolerance"
        selections.append(FrameSelection(target, nearest.frame_index, nearest.pts_seconds, error, status))
    return selections
