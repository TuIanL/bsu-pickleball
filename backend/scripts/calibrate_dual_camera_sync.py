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
from pathlib import Path

from app.services.dual_camera_sync import calibration_to_dict, calibrations_from_anchor_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anchors", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.anchors.read_text(encoding="utf-8"))
    reference = str(payload["reference_camera"])
    cameras = [str(camera) for camera in payload.get("cameras", [reference])]
    calibrations = calibrations_from_anchor_rows(
        payload.get("anchors", []),
        reference_camera=reference,
        camera_ids=cameras,
    )
    output = {
        "schema_version": "dual_camera_sync_calibration.v1",
        "reference_camera": reference,
        "anchor_count": len(payload.get("anchors", [])),
        "mappings": {camera: calibration_to_dict(value) for camera, value in calibrations.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
