from fastapi import APIRouter, HTTPException

from app.schemas.analysis import AnalysisJobCreate, AnalysisJobSummary, AnalysisReport
from app.services.mock_analysis import create_mock_job, get_mock_job, get_mock_report

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/jobs", response_model=AnalysisJobSummary)
def create_analysis_job(payload: AnalysisJobCreate) -> AnalysisJobSummary:
    return create_mock_job(payload.metadata)


@router.get("/jobs/{job_id}", response_model=AnalysisJobSummary)
def read_analysis_job(job_id: str) -> AnalysisJobSummary:
    job = get_mock_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    return job


@router.get("/jobs/{job_id}/report", response_model=AnalysisReport)
def read_analysis_report(job_id: str) -> AnalysisReport:
    report = get_mock_report(job_id)

    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    return report
