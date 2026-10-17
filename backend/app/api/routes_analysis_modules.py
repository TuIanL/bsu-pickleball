"""能力级开发验证入口，与既有 /jobs 共用控制面。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.analysis_runtime.contracts import AnalysisRequest
from app.analysis_runtime.hashing import AnalysisRuntimeError
from app.analysis_runtime.registry import builtin_registry
from app.analysis_runtime.service import artifact_store, inspect_run, planner, resume

router = APIRouter(prefix="/api/analysis", tags=["analysis-modules"])


def jobs():
    from app.services import mock_analysis
    mock_analysis._sync_orchestration_storage()
    return mock_analysis._JOB_STORE


def public(value):
    from app.services.analysis_run_trace import redact_public_strings
    # 公共入口不包含内部异常原文/栈，即使其中没有文件路径。
    def scrub(item):
        if isinstance(item, list):
            return [scrub(v) for v in item]
        if isinstance(item, dict):
            return {k: scrub(v) for k, v in item.items() if k not in {"internal_message", "diagnostics", "internalErrorMessage", "media_path", "timing_path", "sidecar_path"}}
        return item
    return redact_public_strings(scrub(value))


def runtime_error(exc):
    return HTTPException(status_code=400, detail={"code": exc.code, "message": "模块请求无法执行，请检查参数或准备状态", "details": public(exc.details)})


class SourcePreparation(BaseModel):
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    view_id: str = Field(default="cam_1", pattern=r"^[A-Za-z0-9_-]+$")
    camera_id: str | None = None
    require_pts: bool = False


@router.get("/capabilities")
def capabilities():
    return builtin_registry().catalog()


@router.post("/sources/prepare")
def prepare_registered_source(request: SourcePreparation):
    from pathlib import Path
    from app.services.video_service import video_service
    from app.analysis_runtime.sources import prepare_source
    video = video_service.get_video(request.video_id)
    if video is None:
        raise HTTPException(404, detail="Video not found")
    try:
        source = prepare_source(artifact_store(jobs()), Path(video.path), view_id=request.view_id,
                                camera_id=request.camera_id, video_id=video.id, require_pts=request.require_pts)
        return public(source.model_dump(mode="json"))
    except AnalysisRuntimeError as exc:
        raise runtime_error(exc) from exc


@router.post("/models/prepare")
def prepare_registered_models():
    from app.analysis_runtime.sources import prepare_models
    store = jobs()
    return prepare_models(artifact_store(store), store.storage.settings)


@router.post("/plans/preview")
def preview(request: AnalysisRequest):
    try:
        return public(planner(jobs()).plan(request).model_dump(mode="json"))
    except AnalysisRuntimeError as exc:
        raise runtime_error(exc) from exc


@router.get("/jobs/{job_id}/manifest")
def read_manifest(job_id: str):
    try:
        return public(inspect_run(jobs(), job_id))
    except AnalysisRuntimeError as exc:
        raise HTTPException(404, detail={"code": exc.code, "message": "Module manifest not found"}) from exc


@router.post("/jobs/{job_id}/resume")
def resume_module(job_id: str):
    try:
        result = resume(jobs(), job_id)
        from app.services import mock_analysis
        if mock_analysis._WORKER is not None:
            mock_analysis._WORKER.notify()
        return public(result.model_dump(mode="json"))
    except AnalysisRuntimeError as exc:
        raise runtime_error(exc) from exc


@router.get("/artifacts/{artifact_id}")
def read_artifact(artifact_id: str, content: bool = Query(default=False)):
    artifacts = artifact_store(jobs())
    manifest = artifacts.manifest(artifact_id)
    if manifest is None:
        raise HTTPException(404, detail="Artifact not found")
    availability = artifacts.availability(manifest)
    if content:
        if availability != "available":
            raise HTTPException(409, detail={"code": availability, "message": "Artifact unavailable"})
        return public(artifacts.payload(manifest.ref))
    return public({"manifest": manifest.model_dump(mode="json"), "availability": availability})
