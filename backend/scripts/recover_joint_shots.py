"""Recover missing Shot links from persisted exact segment/event references.

This does not rerun ball detection or guess event associations. --write backs
up every replaced artifact, then republishes optional facts for the same job.
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, UTC
from dataclasses import fields
from pathlib import Path

import numpy as np

from app.schemas.analysis import AnalysisJobSummary
from app.schemas.pipeline import AnalysisPipelineResult
from app.services.storage_service import StorageService
from app.services.calibration_service import CalibrationService
from app.services.canonical_shot_rally_events import generate_and_persist_canonical_events, build_shot_rally_events
from app.services.shot_landings import build_shot_landings
from app.services.performance_insights.service import generate_and_persist_insights
from app.vision.pickleball_game_analysis.reconstruction_schemas import FlightSegment, TrajectoryEvent, TrajectoryEventType
from app.vision.pickleball_game_analysis.ball_shot_assembler import BallShotAssembler


def recover(payload, job):
    if any(segment.get("shot_id") for segment in payload.get("segments", [])):
        return payload
    windows = payload.get("diagnostics", {}).get("segment_windows", [])
    if not windows:
        raise ValueError("Missing persisted segment windows; cannot recover exact links")
    calibrations = {}
    for view in job.jointViewInputs:
        slot = view.get("cameraSlot") or view.get("camera_slot")
        calibration = CalibrationService().get_calibration(view.get("calibrationId") or view.get("calibration_id"))
        if calibration and calibration.homography:
            calibrations[slot] = (calibration.homography.values, view.get("courtOrientation") or view.get("court_orientation"))
    events = {}
    accepted_fields = {field.name for field in fields(TrajectoryEvent)} - {"attribution"}
    for raw in payload.get("events", []):
        view = raw.get("diagnostics", {}).get("view_id")
        if raw["event_type"] == "bounce" and raw.get("court_xy") is None and raw.get("image_xy") and view in calibrations:
            matrix, orientation = calibrations[view]
            p = np.asarray(matrix) @ np.array([*raw["image_xy"], 1.0])
            if np.isfinite(p).all() and abs(p[2]) > 1e-9:
                x, y = (p[:2] / p[2]).tolist()
                raw["court_xy"] = [20-x, 44-y] if orientation == "rotate_180" else [x, y]
                raw.setdefault("diagnostics", {})["court_coordinate_source"] = "calibrated_ground_homography"
        values = {key: value for key, value in raw.items() if key in accepted_fields}
        values["event_type"] = TrajectoryEventType(values["event_type"])
        events[raw["event_id"]] = TrajectoryEvent(**values)
    flights = []
    for i, window in enumerate(sorted(windows, key=lambda row: row["start_sec"])):
        start_id, end_id = window.get("start_event_id"), window.get("end_event_id")
        if any(event_id and event_id not in events for event_id in (start_id, end_id)):
            raise ValueError("Dangling event reference; recovery refused")
        flights.append(FlightSegment(
            segment_id=window["segment_id"], start_index=i, end_index=i,
            start_event_id=start_id, end_event_id=end_id,
            start_event_type=events[start_id].event_type if start_id else None,
            end_event_type=events[end_id].event_type if end_id else TrajectoryEventType.END_OF_STREAM,
        ))
    BallShotAssembler().assemble(flights, events)
    by_id = {flight.segment_id: flight for flight in flights}
    for segment in payload["segments"]:
        flight = by_id[segment["segment_id"]]
        for key in ("shot_id", "hitter_player_id", "ownership_status", "ownership_confidence",
                    "ownership_source_event_id", "start_event_id", "end_event_id"):
            segment[key] = getattr(flight, key)
        segment["start_event_type"] = flight.start_event_type.value if flight.start_event_type else None
        segment["end_event_type"] = flight.end_event_type.value if flight.end_event_type else None
    payload.setdefault("diagnostics", {})["shot_link_recovery"] = "persisted_segment_windows_v1"
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    storage = StorageService()
    job = AnalysisJobSummary.model_validate_json((Path("data/outputs/jobs") / f"{args.job}.json").read_text())
    root = storage.resolve_capture_job_root(job.id, job.metadata.capture_take_id)
    path = storage.reconstructed_ball_trajectory_json_path(job.id)
    payload = recover(storage.read_json(path), job)
    facts = build_shot_rally_events(job_id=job.id, video_id=job.videoId, match_format=job.metadata.matchFormat,
                                   reconstructed_payload=payload)
    landings = build_shot_landings(job_id=job.id, video_id=job.videoId, shot_events=facts, reconstructed_payload=payload)
    print(json.dumps({"shots": len(facts.shots), "landings": landings.summary.model_dump()}, ensure_ascii=False), flush=True)
    if not args.write:
        return
    backup = root / ("backup-before-shot-recovery-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    backup.mkdir()
    for artifact in root.glob("*.json"):
        if artifact.name not in {"fused_diagnostics.json", "multiview_ball_stereo_evidence.json"}:
            shutil.copy2(artifact, backup / artifact.name)
    previous_digest = payload.pop("content_sha256", None)
    payload.setdefault("diagnostics", {}).setdefault("recovery_provenance", {
        "source_content_sha256": previous_digest,
        "method": "persisted_segment_windows_v1",
        "backup_path": str(backup),
    })
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    storage.write_json_atomic(path, payload)
    result = AnalysisPipelineResult.model_validate(storage.read_json(storage.output_json_path(job.id)))
    result, _, _ = generate_and_persist_canonical_events(job, result, storage=storage)
    result, insights = generate_and_persist_insights(job, result, storage=storage)
    storage.write_json_atomic(storage.output_json_path(job.id), storage.publicize_pipeline_result(result).model_dump(mode="json"))
    print("RECOVERED", root, "BACKUP", backup, "INSIGHTS", getattr(insights, "status", None), flush=True)


if __name__ == "__main__":
    main()
