#!/usr/bin/env python3
"""在远端验证双摄 PTS 网格与内容级运动时间偏移，输出机器可读报告。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA_VERSION = "match_state_dual_sync_report.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pts_summary(path: Path) -> dict[str, Any]:
    count = 0
    first: dict[str, Any] | None = None
    last: dict[str, Any] | None = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            if first is None:
                first = item
            last = item
            count += 1
    if first is None or last is None:
        raise ValueError(f"PTS sidecar 为空: {path}")
    return {
        "sha256": _sha256(path),
        "frame_count": count,
        "first_pts_seconds": float(first["pts_seconds"]),
        "last_pts_seconds": float(last["pts_seconds"]),
    }


def _motion_energy(video: Path, *, fps: float, width: int, height: int) -> np.ndarray:
    frame_bytes = width * height
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-an",
        "-vf",
        f"fps={fps},scale={width}:{height}:flags=fast_bilinear,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    previous: np.ndarray | None = None
    energies: list[float] = []
    while True:
        chunk = process.stdout.read(frame_bytes)
        if not chunk:
            break
        if len(chunk) != frame_bytes:
            process.kill()
            raise RuntimeError(f"ffmpeg 返回不完整帧: {video}")
        frame = np.frombuffer(chunk, dtype=np.uint8).astype(np.int16)
        if previous is not None:
            energies.append(float(np.mean(np.abs(frame - previous))))
        previous = frame
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise RuntimeError(f"ffmpeg 解码失败 {video}: {stderr[-2000:]}")
    values = np.asarray(energies, dtype=np.float64)
    if values.size < max(30, round(fps * 10)):
        raise ValueError(f"运动序列过短: {video}")
    # 平滑压制压缩噪声，并裁掉首尾启动/停止瞬间。
    kernel = np.ones(5, dtype=np.float64) / 5
    values = np.convolve(values, kernel, mode="same")
    trim = min(round(fps * 5), values.size // 10)
    return values[trim:-trim] if trim else values


def _correlation(first: np.ndarray, second: np.ndarray, lag: int) -> float:
    if lag > 0:
        first, second = first[lag:], second[:-lag]
    elif lag < 0:
        first, second = first[:lag], second[-lag:]
    size = min(first.size, second.size)
    if size < 20:
        return float("nan")
    first = first[:size]
    second = second[:size]
    first_std = float(first.std())
    second_std = float(second.std())
    if first_std < 1e-9 or second_std < 1e-9:
        return 0.0
    return float(np.mean(((first - first.mean()) / first_std) * ((second - second.mean()) / second_std)))


def _estimate_motion_offset(first: np.ndarray, second: np.ndarray, *, fps: float, max_lag_ms: int) -> dict[str, Any]:
    max_lag_frames = max(1, round(max_lag_ms * fps / 1000))
    correlations = {lag: _correlation(first, second, lag) for lag in range(-max_lag_frames, max_lag_frames + 1)}
    best_lag = max(correlations, key=lambda lag: (correlations[lag], -abs(lag)))
    alternatives = [value for lag, value in correlations.items() if abs(lag - best_lag) > 1]
    second_best = max(alternatives) if alternatives else correlations[best_lag]
    return {
        "sampling_fps": fps,
        "max_lag_ms": max_lag_ms,
        "cam_1_sample_count": int(first.size),
        "cam_2_sample_count": int(second.size),
        "estimated_cam_2_offset_ms": round(best_lag * 1000 / fps),
        "peak_correlation": round(correlations[best_lag], 6),
        "zero_lag_correlation": round(correlations.get(0, float("nan")), 6),
        "peak_margin_over_non_neighbor": round(correlations[best_lag] - second_best, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证比赛状态数据集双摄同步")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sampling-fps", type=float, default=8.0)
    parser.add_argument("--max-lag-ms", type=int, default=2000)
    parser.add_argument("--pass-offset-ms", type=int, default=250)
    parser.add_argument("--min-correlation", type=float, default=0.10)
    args = parser.parse_args()

    sessions: list[dict[str, Any]] = []
    for session_dir in sorted((args.dataset_root / "media").iterdir()):
        if not session_dir.is_dir():
            continue
        session_id = session_dir.name
        videos = {role: session_dir / f"{role}.ts" for role in ("cam_1", "cam_2")}
        sidecars = {
            role: args.dataset_root / "timing" / session_id / f"{role}.pts.jsonl"
            for role in ("cam_1", "cam_2")
        }
        if not all(path.exists() for path in [*videos.values(), *sidecars.values()]):
            raise FileNotFoundError(f"双摄媒体或 PTS 缺失: {session_id}")
        pts = {role: _pts_summary(path) for role, path in sidecars.items()}
        pts_grid_identical = pts["cam_1"] == pts["cam_2"]
        motion = {
            role: _motion_energy(path, fps=args.sampling_fps, width=160, height=90)
            for role, path in videos.items()
        }
        estimate = _estimate_motion_offset(
            motion["cam_1"], motion["cam_2"], fps=args.sampling_fps, max_lag_ms=args.max_lag_ms
        )
        offset_pass = abs(estimate["estimated_cam_2_offset_ms"]) <= args.pass_offset_ms
        content_evidence_pass = estimate["peak_correlation"] >= args.min_correlation
        status = "passed" if pts_grid_identical and offset_pass and content_evidence_pass else "insufficient_evidence"
        sessions.append(
            {
                "source_session_id": session_id,
                "status": status,
                "pts_grid_identical": pts_grid_identical,
                "pts": pts,
                "motion_alignment": estimate,
                "gates": {
                    "pts_grid_identical": pts_grid_identical,
                    "absolute_offset_within_ms": args.pass_offset_ms,
                    "offset_pass": offset_pass,
                    "minimum_peak_correlation": args.min_correlation,
                    "content_evidence_pass": content_evidence_pass,
                },
            }
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_root": str(args.dataset_root),
        "session_count": len(sessions),
        "passed_count": sum(item["status"] == "passed" for item in sessions),
        "overall_status": "passed" if sessions and all(item["status"] == "passed" for item in sessions) else "insufficient_evidence",
        "config": {
            "sampling_fps": args.sampling_fps,
            "max_lag_ms": args.max_lag_ms,
            "pass_offset_ms": args.pass_offset_ms,
            "min_correlation": args.min_correlation,
        },
        "sessions": sessions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("session_count", "passed_count", "overall_status")}, ensure_ascii=False))
    return 0 if report["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
