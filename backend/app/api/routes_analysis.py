from __future__ import annotations

from typing import Union

from fastapi import APIRouter, HTTPException

# 导入分析相关的模式（Schemas）
from app.schemas.analysis import AnalysisJobCreate, AnalysisJobSummary, AnalysisReport
from app.schemas.pipeline import AnalysisPipelineResult
# 导入模拟分析服务
from app.services.mock_analysis import create_analysis_job, get_mock_job, get_mock_report, get_pipeline_result

# 定义 API 路由，前缀为 /api/analysis，标签为 analysis
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/jobs", response_model=AnalysisJobSummary)
def create_analysis_job_route(payload: AnalysisJobCreate) -> AnalysisJobSummary:
    """
    创建分析任务
    """
    return create_analysis_job(payload)


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
