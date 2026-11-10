"""Resume optional visual inference from a verified, composed tracking result.

This checkpoint never changes the tracking verdict or the frozen roster. A
worker retry still runs requested pose/ball inference and publishes normally.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.schemas.pipeline import AnalysisPipelineResult, PipelineStageResult


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(job, videos):
    return {
        "job_id": job.id, "joint_run_id": job.jointRunId,
        "input_signature": job.inputSignature, "config_signature": job.configSignature,
        "roster_hash": job.rosterSnapshotHash,
        "clip_start_ms": job.clipStartMs, "clip_end_ms": job.clipEndMs,
        "joint_view_inputs": job.jointViewInputs,
        "videos": {view: {"id": video.id, "path": str(Path(video.path).resolve()),
                           "size": Path(video.path).stat().st_size,
                           "mtime_ns": Path(video.path).stat().st_mtime_ns}
                   for view, video in videos.items()},
    }


def save_joint_visual_checkpoint(*, job, result, storage, videos):
    root = storage._job_artifact_root(job.id)
    overlay = storage.fused_player_overlay_json_path(job.id)
    if result.artifacts.fused_player_overlay_status != "available" or not overlay.is_file():
        raise RuntimeError("Cannot checkpoint tracking without an available formal person overlay")
    result_path = root / "joint_tracking_result.checkpoint.json"
    storage.write_json_atomic(result_path, result.model_dump(mode="json"))
    storage.write_json_atomic(root / "joint_visual_checkpoint.json", {
        "schema_version": "joint_visual_checkpoint.v1",
        "identity": _identity(job, videos),
        "result_sha256": _sha(result_path), "overlay_sha256": _sha(overlay),
    })


def load_joint_visual_checkpoint(*, job, storage, videos):
    root = storage._job_artifact_root(job.id)
    marker = root / "joint_visual_checkpoint.json"
    if not marker.is_file():
        return None
    manifest = storage.read_json(marker)
    if manifest.get("schema_version") != "joint_visual_checkpoint.v1" or manifest.get("identity") != _identity(job, videos):
        raise RuntimeError("Tracking checkpoint input/roster mismatch; refusing to reuse")
    result_path = root / "joint_tracking_result.checkpoint.json"
    overlay = storage.fused_player_overlay_json_path(job.id)
    if _sha(result_path) != manifest.get("result_sha256") or _sha(overlay) != manifest.get("overlay_sha256"):
        raise RuntimeError("Tracking checkpoint artifact hash mismatch; refusing to reuse")
    result = AnalysisPipelineResult.model_validate(storage.read_json(result_path))
    if result.job_id != job.id or result.artifacts.fused_player_overlay_status != "available":
        raise RuntimeError("Tracking checkpoint result is not authoritative")
    return result


def report_reused_tracking(progress_callback, result):
    if progress_callback:
        for stage_id, label in [("multiview-input-check", "素材与同步检查"),
                                ("multiview-joint", "双摄协同跟踪"),
                                ("multiview-ball-analysis", "双摄球路分析"),
                                ("multiview-metrics", "运动指标重算")]:
            prior = next((s for s in result.stages if s.id == stage_id), None)
            progress_callback(PipelineStageResult(
                id=stage_id, label=label, status=prior.status if prior else "done",
                progress=100, detail="复用同一任务已校验的跟踪检查点；二维球检测将在基础叠加阶段执行",
            ))


def save_joint_f0_checkpoint(*, job, diagnostics, storage, videos, run_dir):
    """Preserve authoritative runtime evidence before optional native refinement."""
    names = ["fused_player_trajectory.f0.v2.json", "f0_refinement_snapshot.v1.json"]
    if not all((run_dir/name).is_file() for name in names):
        raise RuntimeError("F0 checkpoint requires complete trajectory and snapshot")
    storage.write_json_atomic(run_dir/"f0_runtime_diagnostics.v1.json", diagnostics)
    names.append("f0_runtime_diagnostics.v1.json")
    storage.write_json_atomic(run_dir/"joint_f0_checkpoint.v1.json", {
        "schema_version":"joint_f0_checkpoint.v1", "identity":_identity(job,videos),
        "files":{name:_sha(run_dir/name) for name in names},
    })


def load_joint_f0_checkpoint(*, job, storage, videos, run_dir):
    marker=run_dir/"joint_f0_checkpoint.v1.json"
    if not marker.is_file():
        return None
    manifest=storage.read_json(marker)
    if manifest.get("schema_version")!="joint_f0_checkpoint.v1" or manifest.get("identity")!=_identity(job,videos):
        raise RuntimeError("F0 checkpoint identity mismatch")
    expected={"fused_player_trajectory.f0.v2.json","f0_refinement_snapshot.v1.json","f0_runtime_diagnostics.v1.json"}
    if set(manifest.get('files',{}))!=expected:
        raise RuntimeError("F0 checkpoint files mismatch")
    for name,digest in manifest['files'].items():
        if not (run_dir/name).is_file() or _sha(run_dir/name)!=digest:
            raise RuntimeError("F0 checkpoint content mismatch")
    return storage.read_json(run_dir/"f0_runtime_diagnostics.v1.json")
