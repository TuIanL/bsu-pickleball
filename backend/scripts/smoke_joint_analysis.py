"""Run an isolated real-video acceptance clip using an existing job's inputs.

Run from backend: PYTHONPATH=. .venv/bin/python scripts/smoke_joint_analysis.py
No production job or existing artifact is overwritten.
"""
import argparse
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, UTC

os.environ["PICKLEBALL_ENABLE_MODEL_INFERENCE"] = "true"
os.environ["PICKLEBALL_ENABLE_POSE_INFERENCE"] = "false"

from app.schemas.analysis import AnalysisJobSummary
from app.schemas.pipeline import AnalysisPipelineResult
from app.schemas.analysis import build_match_context
from app.services.storage_service import StorageService
from app.services.multiview_joint_executor import MultiViewJointExecutor
from app.services.canonical_shot_rally_events import generate_and_persist_canonical_events
from app.services.performance_insights.service import generate_and_persist_insights
from app.services.metric_normalization import generate_and_persist_normalized_metrics
from app.services.real_report_builder import build_real_performance_report
from app.services.multiview_result_composer import MultiViewResultComposer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--start-ms", type=int, default=17750)
    parser.add_argument("--end-ms", type=int, default=23750)
    parser.add_argument("--reuse-smoke-job", help="Revalidate post-processing without rerunning detection")
    args = parser.parse_args()
    storage = StorageService()
    source = Path("data/outputs/jobs") / f"{args.source_job}.json"
    job = AnalysisJobSummary.model_validate(json.loads(source.read_text()))
    source_job = job
    job = job.model_copy(update={
        "id": f"smoke-{uuid4().hex[:10]}", "jointRunId": None,
        "clipStartMs": args.start_ms, "clipEndMs": args.end_ms,
        "segmentationRequired": False, "segmentationRunId": None, "windowPlanHash": None,
        "enableModelInference": True, "enablePoseInference": False,
        "rallyContextMode": "legacy", "analysisRallyContextSetHash": None,
    })
    if args.reuse_smoke_job:
        if not args.reuse_smoke_job.startswith("smoke-"):
            raise ValueError("Only isolated smoke jobs may be reprocessed")
        root = storage.resolve_capture_job_root(args.reuse_smoke_job, source_job.metadata.capture_take_id)
        job = AnalysisJobSummary.model_validate_json((root / "smoke_job.json").read_text())
    storage.resolve_capture_job_root(job.id, job.metadata.capture_take_id)
    last = [0.0]

    def progress(stage):
        now = time.monotonic()
        if now - last[0] > 20 or stage.status != "active":
            print(stage.id, stage.status, stage.progress, stage.detail, flush=True)
            last[0] = now

    print("SMOKE_JOB", job.id, flush=True)
    token = SimpleNamespace(raise_if_cancelled=lambda: None, is_cancel_requested=lambda: False)
    if args.reuse_smoke_job:
        result = AnalysisPipelineResult.model_validate(storage.read_json(storage.output_json_path(job.id)))
        fused = storage.read_json(storage.fused_trajectory_json_path(job.id))
        roster = storage.read_json(storage.roster_manifest_json_path(job.id))
        result.metrics = MultiViewResultComposer(storage).recompute_metrics(
            fused, build_match_context(job.metadata.matchFormat),
            roster_map={p["global_player_id"]: p["player_id"] for p in roster["players"]},
        )
    else:
        result = MultiViewJointExecutor(SimpleNamespace(update=lambda *a, **kw: None), None).execute(job, token, progress)
    result, events, metrics = generate_and_persist_canonical_events(job, result, storage=storage)
    result, normalized = generate_and_persist_normalized_metrics(job, result, events=events, snapshot=metrics, storage=storage)
    result, insights = generate_and_persist_insights(job, result, storage=storage)
    report = build_real_performance_report(
        job=job, metadata=job.metadata, report_id=f"PV-{job.id}",
        generated_at=datetime.now(UTC).isoformat(), result=result, storage=storage,
    )
    storage.write_json(storage._job_artifact_root(job.id) / "smoke_report.json", report.model_dump(mode="json"))
    storage.write_json(storage.output_json_path(job.id), result.model_dump(mode="json"))
    storage.write_json(storage._job_artifact_root(job.id) / "smoke_job.json", job.model_dump(mode="json"))
    print(json.dumps({"job": job.id, "status": result.status, "players": result.observed_player_count,
                      "tracks": len(result.tracks), "shots": len(events.shots),
                      "landings": result.artifacts.shot_landings_detail,
                      "insights": result.artifacts.performance_insights_status,
                      "normalized_metrics": result.artifacts.normalized_metrics_status,
                      "report": str(storage._job_artifact_root(job.id) / "smoke_report.json"),
                      "path": str(storage._job_artifact_root(job.id))}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
