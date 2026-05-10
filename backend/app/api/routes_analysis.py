from __future__ import annotations

from typing import Literal, Union

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

# 导入分析相关的模式（Schemas）
from app.schemas.analysis import AnalysisJobCreate, AnalysisJobSummary, AnalysisReport
from app.schemas.pipeline import AnalysisPipelineResult
# 导入模拟分析服务
from app.services.mock_analysis import create_analysis_job, get_mock_job, get_mock_report, get_pipeline_result
from app.services.storage_service import StorageService

# 定义 API 路由，前缀为 /api/analysis，标签为 analysis
router = APIRouter(prefix="/api/analysis", tags=["analysis"])
_STORAGE = StorageService()


@router.post("/jobs", response_model=AnalysisJobSummary)
def create_analysis_job_route(
    payload: AnalysisJobCreate,
    background_tasks: BackgroundTasks,
) -> AnalysisJobSummary:
    """
    创建分析任务
    """
    return create_analysis_job(payload, background_tasks=background_tasks)


@router.get("/jobs/{job_id}", response_model=AnalysisJobSummary)
def read_analysis_job(job_id: str) -> AnalysisJobSummary:
    """
    读取分析任务详情
    """
    job = get_mock_job(job_id)

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
    artifact_name: Literal["tracking-overlay", "pose-overlay"],
) -> JSONResponse:
    """
    读取浏览器可消费的分析 overlay artifact
    """
    job = get_mock_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    path = (
        _STORAGE.tracking_overlay_json_path(job_id)
        if artifact_name == "tracking-overlay"
        else _STORAGE.pose_overlay_json_path(job_id)
    )
    if not path.exists():
        raise HTTPException(status_code=404, detail="Analysis artifact not found")
    return JSONResponse(_STORAGE.read_json(path))
