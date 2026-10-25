"""CLI/API 共用门面。创建任务仍交给既有 JobStore/Worker。"""
from __future__ import annotations

from uuid import uuid4

from app.analysis_runtime.artifact_store import ArtifactStore
from app.analysis_runtime.contracts import AnalysisRequest, ModularRunManifest, NodeRun, now
from app.analysis_runtime.hashing import AnalysisRuntimeError, digest
from app.analysis_runtime.planner import Planner, model_identity
from app.analysis_runtime.registry import builtin_registry


def artifact_store(jobs) -> ArtifactStore:
    configured = getattr(jobs.storage.settings, "modular_artifacts_dir", None)
    root = jobs.storage.settings.resolve_path(configured) if configured else jobs.storage.outputs_dir / "_artifacts"
    return ArtifactStore(jobs.control_plane, root)


def planner(jobs, db=None):
    artifacts = artifact_store(jobs)
    from app.analysis_runtime.web_sources import validate_binding
    return Planner(builtin_registry(), artifacts.source, artifacts.model, artifacts.manifest, artifacts.cached,
                   binding_validator=lambda request, sources: validate_binding(request, sources, db=db))


def submit(jobs, request: AnalysisRequest, metadata, *, priority=0, expected_plan_hash=None, db=None):
    from app.schemas.analysis import AnalysisJobSummary
    if not jobs.storage.settings.modular_analysis_enabled:
        raise AnalysisRuntimeError("modular_submission_disabled", "模块任务提交已关闭")
    plan = planner(jobs, db=db).plan(request)
    if expected_plan_hash is not None and plan.plan_hash != expected_plan_hash:
        raise AnalysisRuntimeError("plan_preview_stale", "分析计划已变化，请重新预览")
    from app.analysis_runtime.web_sources import verified_metadata
    metadata = verified_metadata(metadata, plan.sources, request.source_binding, db=db)
    timestamp = now()
    job = AnalysisJobSummary(
        id="job-" + uuid4().hex[:12], status="queued", canonicalStatus="queued",
        displayStatus="queued", stage="modular", progress=0, stages=[],
        metadata=metadata, createdAt=timestamp, updatedAt=timestamp, queuedAt=timestamp,
        analysisEngine="modular_v1", planId=plan.plan_id, planHash=plan.plan_hash,
        resultKind="modular", analysisKind="multiview" if len(plan.sources)==2 else "single_view",
        analysisMode="real", priority=priority, frameStride=plan.sampling.stride,
        clipStartMs=plan.requested_window.start_ms, clipEndMs=plan.requested_window.end_ms,
        inputSignature=plan.plan_hash, configSignature="modular_v1",
        videoId=next((s.video_id for s in plan.sources if s.view_id==plan.reference_view_id), None),
        recordingSessionId=metadata.recording_session_id, cameraSlot=metadata.camera_slot,
        analysisTargets=list(plan.targets),
        reportId=None, referenceViewId=plan.reference_view_id, nodeRuns=[
            NodeRun(node_key=n.node_key, capability_id=n.capability_id,
                    implementation_id=n.implementation.implementation_id, implementation_version=n.implementation.version,
                    configuration_digest=digest({"parameters": n.parameters, "model": model_identity(n.model)})) for n in plan.nodes],
    )
    payload = artifact_store(jobs).submit(plan, job.model_dump(mode="json"), new_version=request.new_version)
    return jobs.get(payload["id"])


def inspect_run(jobs, job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None or job.analysisEngine != "modular_v1":
        raise AnalysisRuntimeError("module_job_not_found", "模块任务不存在")
    artifacts = artifact_store(jobs)
    value = artifacts.result(job_id)
    runs = artifacts.node_runs(job_id) or list(job.nodeRuns)
    if value is None or value.get("status") != job.canonicalStatus:
        targets = artifacts.plan(job.planId).targets
        completed = [r for r in runs if r.node_key in targets and r.status in {"completed", "cached"}]
        terminal = job.canonicalStatus in {"failed","canceled","interrupted"}
        if terminal:
            runs = [r.model_copy(update={"status": "canceled" if job.canonicalStatus=="canceled" else "blocked"})
                    if r.status in {"pending","running"} else r for r in runs]
        value = ModularRunManifest(
            job_id=job_id, plan_id=job.planId, plan_hash=job.planHash,
            status=job.canonicalStatus,
            completeness="complete" if len(completed)==len(targets) else "partial" if completed else "none",
            targets=targets, nodes=tuple(runs), artifacts=tuple(r.artifact for r in runs if r.artifact),
        ).model_dump(mode="json")
    value["artifact_details"] = [
        {"manifest": manifest.model_dump(mode="json"), "availability": artifacts.availability(manifest)}
        for ref in value["artifacts"]
        if (manifest := artifacts.manifest(ref["artifact_id"])) is not None
    ]
    return value


def resume(jobs, job_id: str):
    """显式恢复同一冻结计划；不擦除失败证据，也不重新读取默认配置。"""
    from app.services.job_orchestration import canonical_to_display_status
    job = jobs.get(job_id)
    if job is None or job.analysisEngine != "modular_v1":
        raise AnalysisRuntimeError("module_job_not_found", "模块任务不存在")
    if job.canonicalStatus not in {"failed", "interrupted"}:
        raise AnalysisRuntimeError("module_resume_not_allowed", "当前任务状态不可恢复")
    artifacts = artifact_store(jobs)
    if artifacts.plan(job.planId) is None:
        raise AnalysisRuntimeError("plan_unavailable", "冻结计划不可用")

    def mutator(payload):
        if payload.get("canonicalStatus") not in {"failed","interrupted"}:
            return None
        payload.update(canonicalStatus="queued", status=canonical_to_display_status("queued"),
                       displayStatus="queued", queuedAt=now(), finishedAt=None,
                       cancelRequestedAt=None, errorCode=None, errorMessage=None, publicErrorMessage=None)
        return payload
    return jobs._persist_payload(jobs.control_plane.mutate(job_id, mutator, expected_status=job.canonicalStatus))
