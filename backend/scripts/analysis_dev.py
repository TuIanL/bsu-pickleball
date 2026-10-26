#!/usr/bin/env python3
"""能力级局部验证：prepare-source / prepare-models / plan / run / inspect。"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis_runtime.contracts import AnalysisRequest
from app.analysis_runtime.hashing import AnalysisRuntimeError
from app.analysis_runtime.service import artifact_store, inspect_run, planner, submit
from app.core.config import get_settings


def readonly_jobs(settings):
    """预览不构造 StorageService/JobStore，防止 mkdir、schema 或历史迁移。"""
    path = settings.resolve_path(settings.analysis_control_database_path) if settings.analysis_control_database_path else settings.resolved_outputs_dir.parent / "analysis_control.sqlite3"
    jobs = SimpleNamespace(
        control_plane=SimpleNamespace(path=path.resolve()),
        storage=SimpleNamespace(settings=settings, outputs_dir=settings.resolved_outputs_dir),
    )
    def get(job_id):
        from app.schemas.analysis import AnalysisJobSummary
        value = artifact_store(jobs)._read_json("analysis_jobs", "job_id", job_id, "payload_json")
        return AnalysisJobSummary.model_validate(value) if value else None
    jobs.get = get
    return jobs


def read_request(args):
    if args.request:
        return AnalysisRequest.model_validate_json(Path(args.request).read_text())
    return AnalysisRequest.model_validate({
        "source_ids": args.source_id or [], "targets": args.target or [],
        "window": {"start_ms": args.start_ms, "end_ms": args.end_ms},
        "sampling": {"stride": args.stride, "phase": args.phase},
        "parameters": json.loads(args.parameters_json),
        "failure_policy": args.failure_policy, "new_version": args.new_version,
        "sync": json.loads(Path(args.sync).read_text()) if args.sync else None,
        "reference_view_id": args.reference_view_id,
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-source")
    prepare.add_argument("path")
    prepare.add_argument("--view-id", default="cam_1")
    prepare.add_argument("--camera-id")
    prepare.add_argument("--video-id")
    prepare.add_argument("--require-pts", action="store_true")
    commands.add_parser("prepare-models")
    for name in ["plan", "run"]:
        command = commands.add_parser(name)
        command.add_argument("--request")
        command.add_argument("--source-id", action="append")
        command.add_argument("--target", action="append")
        command.add_argument("--start-ms", type=int)
        command.add_argument("--end-ms", type=int)
        command.add_argument("--stride", type=int, default=1)
        command.add_argument("--phase", type=int, default=0)
        command.add_argument("--parameters-json", default="{}")
        command.add_argument("--failure-policy", choices=["all_targets","best_effort"], default="all_targets")
        command.add_argument("--new-version", action="store_true")
        command.add_argument("--sync")
        command.add_argument("--reference-view-id")
        if name=="run":
            command.add_argument("--wait", action="store_true", help="通过同一 Worker 在当前进程领取本任务并等待结果")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("identity")
    args = parser.parse_args(argv)
    try:
        settings = get_settings()
        if args.command in {"plan","inspect"}:
            jobs = readonly_jobs(settings)
        else:
            from app.services.job_orchestration import JobStore
            from app.services.storage_service import StorageService
            jobs = JobStore(StorageService(settings))
        artifacts = artifact_store(jobs)
        if args.command == "prepare-source":
            from app.analysis_runtime.sources import prepare_source
            output = prepare_source(artifacts, Path(args.path), view_id=args.view_id,
                                    camera_id=args.camera_id, video_id=args.video_id,
                                    require_pts=args.require_pts).model_dump(mode="json")
        elif args.command == "prepare-models":
            from app.analysis_runtime.sources import prepare_models
            output = prepare_models(artifacts, settings)
        elif args.command == "plan":
            output = planner(jobs).plan(read_request(args)).model_dump(mode="json")
        elif args.command == "run":
            from app.schemas.analysis import AnalysisUploadMetadata
            request = read_request(args)
            metadata = AnalysisUploadMetadata(
                fileName="局部能力验证", matchTitle="局部能力验证", venue="",
                matchDate=date.today().isoformat(), matchFormat="doubles", cameraAngle="unknown",
                athleteLabel="", level="",
            )
            job = submit(jobs, request, metadata)
            if args.wait:
                from app.services.job_orchestration import AnalysisWorkerRuntime
                def forbidden(*a, **kw):
                    raise AssertionError("module job invoked legacy pipeline/report")
                worker = AnalysisWorkerRuntime(jobs, pipeline_factory=forbidden, on_completed=forbidden,
                                               worker_id="analysis-dev")
                worker.run_job(job.id)
                output = inspect_run(jobs, job.id)
            else:
                output = job.model_dump(mode="json")
        elif args.identity.startswith("artifact-"):
            manifest = artifacts.manifest(args.identity)
            if manifest is None:
                raise AnalysisRuntimeError("artifact_missing", "产物不存在")
            output = {"manifest": manifest.model_dump(mode="json"), "availability": artifacts.availability(manifest)}
        elif args.identity.startswith("plan-"):
            plan = artifacts.plan(args.identity)
            if plan is None:
                raise AnalysisRuntimeError("plan_unavailable", "计划不存在")
            output = plan.model_dump(mode="json")
        else:
            output = inspect_run(jobs, args.identity)
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if output.get("status") in {"failed","canceled","interrupted"} else 0
    except (AnalysisRuntimeError, ValueError, OSError) as exc:
        print(json.dumps({"error_code": getattr(exc,"code","invalid_request"), "message": str(exc),
                          "details": getattr(exc,"details",None)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
