#!/usr/bin/env python3
"""Create one calibrated MP4 derivative without modifying the source media."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from app.services.dual_camera_sync import calibration_from_dict, retime_filter_expression


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--fps", type=int, default=60)
    args = parser.parse_args()

    payload = json.loads(args.calibration.read_text(encoding="utf-8"))
    mapping = payload.get("mappings", {}).get(args.camera_id)
    if not isinstance(mapping, dict):
        raise SystemExit(f"No calibration mapping for camera {args.camera_id}")
    calibration = calibration_from_dict(mapping)
    if calibration.quality not in {"good", "degraded"}:
        raise SystemExit(f"Calibration quality is {calibration.quality}; refusing aligned output")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-v", "error", "-i", str(args.input),
        "-map", "0:v:0", "-an", "-vf", retime_filter_expression(calibration),
        "-fps_mode", "cfr", "-r", str(args.fps),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(args.output),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise SystemExit((result.stderr or "ffmpeg failed").strip()[-2000:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
