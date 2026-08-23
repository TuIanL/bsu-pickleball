from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisJobSummary, AnalysisStage
from app.services.job_orchestration import normalize_job


def _legacy_joint_job() -> AnalysisJobSummary:
    return AnalysisJobSummary(
        id="job-api-joint",
        status="processing",
        canonicalStatus="running",
        stage="multiview-joint",
        progress=65,
        createdAt="2026-08-23T00:00:00Z",
        updatedAt="2026-08-23T00:00:00Z",
        analysisKind="multiview",
        executionMode="joint_tracking_v2",
        viewRuns={},
        metadata={
            "fileName": "joint.mp4",
            "matchTitle": "API joint",
            "venue": "Test court",
            "matchDate": "2026-08-23",
            "matchFormat": "doubles",
            "cameraAngle": "baseline",
            "athleteLabel": "Test",
            "level": "MVP",
        },
        stages=[
            AnalysisStage(id="video-read", label="读取视频", status="done", detail="done", progress=100),
            AnalysisStage(id="multiview-joint", label="双摄协同跟踪", status="active", detail="running", progress=95),
            AnalysisStage(id="report", label="报告生成", status="pending", detail="pending", progress=0),
        ],
    )


def test_job_status_api_returns_normalized_joint_order_and_hides_empty_view_runs(monkeypatch):
    import app.api.routes_analysis as routes

    job = normalize_job(_legacy_joint_job())
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: job)

    response = TestClient(app).get("/api/analysis/jobs/job-api-joint")

    assert response.status_code == 200
    body = response.json()
    assert [stage["id"] for stage in body["stages"]] == [
        "multiview-input-check",
        "multiview-joint",
        "multiview-ball-analysis",
        "multiview-metrics",
        "multiview-visualization",
        "multiview-report",
    ]
    assert body["stages"][1]["status"] == "active"
    assert body["stages"][-1]["status"] == "pending"
    assert body["viewRuns"] is None
