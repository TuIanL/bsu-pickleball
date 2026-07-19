#!/usr/bin/env python3
"""Map CaptureTake event timestamps to local frames for each camera."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.dual_camera_sync import (
    build_frame_map,
    calibration_from_dict,
    read_frame_timing_sidecar,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path, help="timeline/events.json")
    parser.add_argument("manifest", type=Path, help="timeline/annotation_manifest.json")
    parser.add_argument("calibration", type=Path, help="sync_calibration.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    events_payload = json.loads(args.events.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    calibration_payload = json.loads(args.calibration.read_text(encoding="utf-8"))
    mappings = calibration_payload.get("mappings", {})

    camera_frames = {}
    for source in manifest.get("sources", []):
        camera_id = str(source["camera_id"])
        sidecars = source.get("timing_sidecar_paths", [])
        if sidecars:
            camera_frames[camera_id] = read_frame_timing_sidecar(sidecars[0])

    exported_events = []
    for event in events_payload.get("events", []):
        target_seconds = int(event.get("timestamp_ms", 0)) / 1000.0
        camera_mappings = {}
        for camera_id, frames in camera_frames.items():
            calibration = mappings.get(camera_id)
            calibration_obj = calibration_from_dict(calibration) if calibration else None
            selection = build_frame_map([target_seconds], frames, calibration=calibration_obj)[0]
            camera_mappings[camera_id] = {
                "frame_index": selection.source_frame_index,
                "source_pts_seconds": selection.source_pts_seconds,
                "selection_error_ms": None if selection.selection_error_seconds is None else selection.selection_error_seconds * 1000.0,
                "status": selection.status,
            }
        exported_events.append({**event, "camera_mappings": camera_mappings})

    output = {
        "schema_version": "dual_camera_annotations.v1",
        "capture_take_id": events_payload.get("capture_take_id"),
        "reference_camera": calibration_payload.get("reference_camera"),
        "events": exported_events,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
