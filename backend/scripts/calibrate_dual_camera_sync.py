#!/usr/bin/env python3
"""Fit dual-camera time mappings from manually identified shared-event anchors.

Input JSON format:
{
  "reference_camera": "174",
  "cameras": ["174", "175"],
  "anchors": [
    {"174": 0.0, "175": 0.050},
    {"174": 900.0, "175": 900.115}
  ]
}
Values are camera-local seconds at the same visible event.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.dual_camera_sync import (
    build_dual_camera_sync_calibration,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anchors", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-residual-ms", type=float, default=33.333)
    args = parser.parse_args()

    payload = json.loads(args.anchors.read_text(encoding="utf-8"))
    output = build_dual_camera_sync_calibration(
        payload,
        max_residual_seconds=max(0.0, args.max_residual_ms) / 1000.0,
        minimum_anchor_count=3,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
