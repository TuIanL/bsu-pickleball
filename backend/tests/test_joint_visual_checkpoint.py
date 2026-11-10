from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult, PerformanceMetrics
from app.services.joint_visual_checkpoint import load_joint_visual_checkpoint, save_joint_visual_checkpoint
from app.services.storage_service import StorageService
from app.schemas.metrics import Heatmap


def case(tmp_path):
    storage = StorageService()
    storage.unregister_capture_job("checkpoint-test")
    storage.register_capture_job("checkpoint-test", tmp_path)
    job = SimpleNamespace(id="checkpoint-test", jointRunId="run", inputSignature="input", configSignature="config",
                          rosterSnapshotHash="roster", clipStartMs=30000, clipEndMs=60000, jointViewInputs=[])
    video = tmp_path / "video.mp4"
    video.write_bytes(b"source media")
    videos = {"cam_1": SimpleNamespace(id="video", path=str(video))}
    overlay = storage.fused_player_overlay_json_path(job.id)
    storage.write_json_atomic(overlay, {"status": "available", "frames": []})
    result = AnalysisPipelineResult(job_id=job.id, status="completed", generated_at=datetime.now(UTC), stages=[],
                                    metrics=PerformanceMetrics(distances=[], speeds=[], kitchen_dwell=[], doubles_spacing=[],
                                                               heatmap=Heatmap(rows=1, cols=1, cells=[])), artifacts=AnalysisArtifacts(
                                        fused_player_overlay_status="available"), message="tracking only; quality not accepted")
    return job, videos, storage, result


def test_retry_reuses_exact_tracking_result_and_preserves_quality_message(tmp_path):
    job, videos, storage, result = case(tmp_path)
    save_joint_visual_checkpoint(job=job, result=result, storage=storage, videos=videos)
    loaded = load_joint_visual_checkpoint(job=job, storage=storage, videos=videos)
    assert loaded.model_dump() == result.model_dump()


@pytest.mark.parametrize("change", ["roster", "config", "clip", "video", "overlay", "result"])
def test_changed_evidence_cannot_reuse_checkpoint(tmp_path, change):
    job, videos, storage, result = case(tmp_path)
    save_joint_visual_checkpoint(job=job, result=result, storage=storage, videos=videos)
    if change == "roster": job.rosterSnapshotHash = "other"
    elif change == "config": job.configSignature = "other"
    elif change == "clip": job.clipEndMs = 61000
    elif change == "video": Path(videos["cam_1"].path).write_bytes(b"different source media")
    elif change == "overlay": storage.fused_player_overlay_json_path(job.id).write_text("{}")
    elif change == "result": (storage._job_artifact_root(job.id) / "joint_tracking_result.checkpoint.json").write_text("{}")
    with pytest.raises(RuntimeError, match="mismatch"):
        load_joint_visual_checkpoint(job=job, storage=storage, videos=videos)


def test_f0_preserves_runtime_diagnostics_before_refinement_and_rejects_changed_inputs(tmp_path):
    from app.services.joint_visual_checkpoint import save_joint_f0_checkpoint, load_joint_f0_checkpoint
    job,videos,storage,_=case(tmp_path)
    for name in ('fused_player_trajectory.f0.v2.json','f0_refinement_snapshot.v1.json'):
        storage.write_json_atomic(tmp_path/name,{'run_id':job.jointRunId})
    diagnostics={'frozen_roster':{'confirmed_count':4},'association_counters':{'quarantined':3}}
    save_joint_f0_checkpoint(job=job,diagnostics=diagnostics,storage=storage,videos=videos,run_dir=tmp_path)
    assert load_joint_f0_checkpoint(job=job,storage=storage,videos=videos,run_dir=tmp_path)==diagnostics
    storage.write_json_atomic(tmp_path/'f0_runtime_diagnostics.v1.json',{'association_counters':{}})
    with pytest.raises(RuntimeError,match='content mismatch'):
        load_joint_f0_checkpoint(job=job,storage=storage,videos=videos,run_dir=tmp_path)
