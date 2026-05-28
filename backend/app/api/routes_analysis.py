from __future__ import annotations

from typing import Literal, Union

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

# 导入分析相关的模式（Schemas）
from app.schemas.analysis import AnalysisDeleteRequest, AnalysisDeleteResult, AnalysisJobCreate, AnalysisJobSummary, AnalysisReport
from app.schemas.pipeline import AnalysisPipelineResult
# 导入模拟分析服务
from app.services.mock_analysis import (
    batch_delete_analysis_jobs,
    cancel_analysis_job,
    create_analysis_job,
    delete_analysis_job,
    get_mock_job,
    get_mock_report,
    get_pipeline_result,
    list_analysis_jobs,
)
from app.services.storage_service import StorageService

# 定义 API 路由，前缀为 /api/analysis，标签为 analysis
router = APIRouter(prefix="/api/analysis", tags=["analysis"])
_STORAGE = StorageService()


@router.post("/jobs", response_model=AnalysisJobSummary)
def create_analysis_job_route(
    payload: AnalysisJobCreate,
) -> AnalysisJobSummary:
    """
    创建分析任务
    """
    return create_analysis_job(payload)


@router.get("/jobs", response_model=list[AnalysisJobSummary])
def list_analysis_jobs_route() -> list[AnalysisJobSummary]:
    """
    读取所有已知分析任务，用于前端任务管理页
    """
    return list_analysis_jobs()


@router.delete("/jobs/{job_id}", response_model=AnalysisDeleteResult)
def delete_analysis_job_route(job_id: str) -> AnalysisDeleteResult:
    """
    删除单个分析任务及其本地产物
    """
    return delete_analysis_job(job_id)


@router.post("/jobs/delete", response_model=list[AnalysisDeleteResult])
def delete_analysis_jobs_route(payload: AnalysisDeleteRequest) -> list[AnalysisDeleteResult]:
    """
    批量删除分析任务及其本地产物
    """
    return batch_delete_analysis_jobs(payload.job_ids)


@router.get("/jobs/{job_id}", response_model=AnalysisJobSummary)
def read_analysis_job(job_id: str) -> AnalysisJobSummary:
    """
    读取分析任务详情
    """
    job = get_mock_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    return job


@router.post("/jobs/{job_id}/cancel", response_model=AnalysisJobSummary)
def cancel_analysis_job_route(job_id: str) -> AnalysisJobSummary:
    """
    请求取消排队中或运行中的分析任务
    """
    job = cancel_analysis_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    return job


@router.get("/jobs/{job_id}/result", response_model=Union[AnalysisPipelineResult, AnalysisJobSummary])
def read_analysis_result(job_id: str) -> Union[AnalysisPipelineResult, AnalysisJobSummary]:
    """
    读取分析结果，如果结果尚未生成，则返回任务状态
    """
    result = get_pipeline_result(job_id)
    if result is not None:
        return result

    job = get_mock_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    return job


@router.get("/jobs/{job_id}/report", response_model=AnalysisReport)
def read_analysis_report(job_id: str) -> AnalysisReport:
    """
    读取分析报告
    """
    report = get_mock_report(job_id)

    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    return report


@router.get("/jobs/{job_id}/artifacts/{artifact_name}")
def read_analysis_artifact(
    job_id: str,
    artifact_name: Literal[
        "tracking-overlay",
        "pose-overlay",
        "player-trajectories",
        "serve-events",
        "serve-debug-candidates",
        "serve-score-series",
        "serve-clips-manifest",
        "serve-debug-overlay",
    ],
) -> JSONResponse | FileResponse:
    """
    读取浏览器可消费的分析 overlay artifact
    """
    job = get_mock_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    if artifact_name == "tracking-overlay":
        path = _STORAGE.tracking_overlay_json_path(job_id)
    elif artifact_name == "pose-overlay":
        path = _STORAGE.pose_overlay_json_path(job_id)
    elif artifact_name == "player-trajectories":
        path = _STORAGE.player_trajectory_json_path(job_id)
    elif artifact_name == "serve-events":
        path = _STORAGE.serve_events_json_path(job_id)
    elif artifact_name == "serve-debug-candidates":
        path = _STORAGE.serve_debug_candidates_json_path(job_id)
    elif artifact_name == "serve-score-series":
        path = _STORAGE.serve_score_series_json_path(job_id)
    elif artifact_name == "serve-clips-manifest":
        path = _STORAGE.serve_clips_manifest_json_path(job_id)
    else:
        path = _STORAGE.serve_debug_overlay_video_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Analysis artifact not found")
    if artifact_name == "serve-debug-overlay":
        return FileResponse(path, media_type="video/mp4")
    return JSONResponse(_STORAGE.read_json(path))
