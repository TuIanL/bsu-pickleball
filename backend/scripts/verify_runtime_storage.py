"""Opt-in real-media/storage acceptance; uses an isolated control DB and explicit faults.

Run from the repository root with backend/.venv/bin/python. No production job or
capture index is changed. A uniquely named analysis trace is retained in the
provided real capture session; evidence and temporary volume live under --output.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
from unittest.mock import patch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--video-a", type=Path, required=True)
    parser.add_argument("--video-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mount-probe", action="store_true", help="Mount/unmount a disposable disk image on macOS")
    parser.add_argument("--resume-mount-probe", action="store_true", help="Reuse completed real-media evidence")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=args.resume_mount_probe)
    session = args.session_dir.resolve(strict=True)
    media = [args.video_a.resolve(strict=True), args.video_b.resolve(strict=True)]
    for key, child in {
        "DATA_DIR": "data", "DATABASE_PATH": "data/app.sqlite3",
        "ANALYSIS_CONTROL_DATABASE_PATH": "data/control.sqlite3", "OUTPUTS_DIR": "data/outputs",
        "UPLOADS_DIR": "data/uploads", "CALIBRATIONS_DIR": "data/calibrations", "TMP_DIR": "data/tmp",
        "RECORDINGS_DIR": "data/recordings", "CAMERAS_DIR": "data/cameras",
        "STATIC_TEST_FRAMES_DIR": "data/frames", "MATCH_STATE_CANDIDATE_DIR": "data/candidates",
    }.items():
        os.environ[f"PICKLEBALL_{key}"] = str(output / child)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import cv2
    from app.core.config import get_settings
    from app.schemas.analysis import AnalysisJobCreate, AnalysisStage, AnalysisUploadMetadata
    from app.services.analysis_progress import stage_ids
    from app.services.analysis_run_trace import read_run_trace
    from app.services.job_orchestration import AnalysisWorkerRuntime, JobStore
    from app.services.storage_service import StorageService
    from app.sqlite_runtime import apply_sqlite_pragmas

    storage = StorageService(get_settings())
    store = JobStore(storage)
    if args.resume_mount_probe:
        evidence = json.loads((output / "evidence.json").read_text())
    else:
        metadata = AnalysisUploadMetadata(fileName="real-dual-storage-probe", matchTitle="可靠性故障注入验收",
            venue="isolated acceptance", matchDate="2026-10-06", matchFormat="doubles", cameraAngle="baseline",
            athleteLabel="acceptance", level="acceptance", capture_take_id="acceptance-real-dual-source")
        job = store.claim(store.create_job(AnalysisJobCreate(metadata=metadata, videoId="acceptance-real-media")).id, "acceptance-worker")
        assert job is not None
        for earlier in list(stage_ids("single_view"))[:list(stage_ids("single_view")).index("video-read")]:
            job = store.mark_stage(job, AnalysisStage(id=earlier, label=earlier, status="done", detail="probe", progress=100))
        job = store.mark_stage(job, AnalysisStage(id="video-read", label="video-read", status="active", detail="probe", progress=10))
        attempts = []

        class FaultProbe:
            def execute(self, current_job, token, callback):
                dimensions = []
                for path in media:
                    print(f"attempt {len(attempts)+1}: decoding {path.name}", flush=True)
                    capture = cv2.VideoCapture(str(path))
                    try:
                        assert capture.isOpened(), f"cannot open {path.name}"
                        ok, frame = capture.read()
                        assert ok and frame is not None, f"cannot decode {path.name}"
                        dimensions.append(list(frame.shape))
                    finally:
                        capture.release()
                    assert not capture.isOpened(), "video handle was not released"
                attempts.append(dimensions)
                raise RuntimeError("acceptance injected decode failure after both real source frames; originals unchanged")

        # Resolve the supplied, already-existing take without touching its production DB.
        with patch.object(StorageService, "_read_capture_session_dir", return_value=session), patch(
            "app.services.analysis_executor_dispatch.resolve_executor", return_value=FaultProbe()
        ):
            runtime = AnalysisWorkerRuntime(store, pipeline_factory=lambda: None, on_completed=lambda *_: None)
            final = runtime._execute_pipeline(job, threading.Event())
            trace_path = storage.resolve_run_trace_path(job.id, metadata.capture_take_id)
        events, availability, reason = read_run_trace(trace_path)
        retries = [event for event in events if event["event"] == "retry"]
        assert final.canonicalStatus == "failed" and final.failureEvidence.failureClass == "input_media"
        assert len(attempts) == 2 and len(retries) == 1
        assert all(key in retries[0] for key in ["exception_type", "exception_message", "traceback_digest", "retry_index", "retry_limit", "will_retry"])
        assert availability == "available", reason
        assert trace_path == session / "analysis" / job.id / "run_trace.jsonl"
        assert not (storage.outputs_dir / job.id / "run_trace.jsonl").exists()
        shutil.copyfile(trace_path, output / "real-media-run_trace.jsonl")
        evidence = {"scope": "real dual-source decode + injected fault; not joint-analysis algorithm validation",
                    "job_id": job.id, "trace_path": str(trace_path), "canonical_status": final.canonicalStatus,
                    "failure_class": final.failureEvidence.failureClass, "attempt_frames": attempts,
                    "retry_events": len(retries), "handles_released": True}
        (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
        print("Real external-volume trace and retry evidence passed.", flush=True)

    if args.mount_probe:
        image = output / "disposable.dmg"
        mount = output / "mount"
        if args.resume_mount_probe and image.exists():
            image.unlink()
        subprocess.run(["hdiutil", "create", "-size", "16m", "-fs", "HFS+", "-volname", "PickleballReliabilityProbe", str(image), "-quiet"], check=True)
        mounted = False
        probe_job = "acceptance-mount-reconnect"
        def attach():
            mount.mkdir(exist_ok=True)
            subprocess.run(["hdiutil", "attach", str(image), "-mountpoint", str(mount), "-nobrowse", "-quiet"], check=True)
        try:
            attach(); mounted = True
            external_session = mount / "session"
            external_session.mkdir(exist_ok=True)
            StorageService.register_capture_job(probe_job, external_session)
            original = storage.output_json_path(probe_job)
            storage.write_json(original, {"probe": "mounted"})
            with sqlite3.connect(mount / "probe.sqlite3") as connection:
                apply_sqlite_pragmas(connection, mount / "probe.sqlite3")
                mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                connection.execute("CREATE TABLE probe (value TEXT)")
                connection.execute("INSERT INTO probe VALUES ('ok')")
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            connection.close()
            subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=True); mounted = False
            assert not external_session.exists()
            degraded = storage.resolve_capture_job_root(probe_job, "acceptance-mount")
            assert degraded == storage.outputs_dir / "_degraded" / probe_job
            storage.write_json(storage.output_json_path(probe_job), {"probe": "detached"})
            assert not external_session.exists(), "offline external session was recreated locally"
            attach(); mounted = True
            StorageService.unregister_capture_job(probe_job)
            assert storage.resolve_capture_job_root(probe_job, "acceptance-mount") == degraded
            assert storage.read_json(storage.output_json_path(probe_job)) == {"probe": "detached"}
            evidence["disposable_volume"] = {"mounted_write": True, "detached_degradation": True,
                "reconnect_restart_read": True, "journal_mode": mode, "integrity_check": "ok"}
        finally:
            if mounted:
                subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=True)
            StorageService.unregister_capture_job(probe_job)
        (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
        print("Disposable-volume detach/reconnect acceptance passed.", flush=True)
    print(f"Evidence: {output / 'evidence.json'}", flush=True)


if __name__ == "__main__":
    main()
