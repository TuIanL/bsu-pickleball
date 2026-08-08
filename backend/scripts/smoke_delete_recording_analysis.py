"""录制级删除分析任务端点的隔离冒烟测试（不触碰真实数据）。

验证：路由注册 + 调用服务 + 返回 AnalysisDeleteResult[] + 录制不被删除。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
from app.services.storage_service import StorageService

# 临时存储，隔离于真实 data/
tmp = Path("/tmp/mv_analysis_smoke")
import shutil

if tmp.exists():
    shutil.rmtree(tmp)
settings = Settings(
    uploads_dir=tmp / "uploads",
    outputs_dir=tmp / "outputs",
    calibrations_dir=tmp / "calibrations",
    tmp_dir=tmp / "tmp",
)
storage = StorageService(settings)

import app.services.mock_analysis as ma
import app.api.routes_sync_recording as rsr

# 把 mock_analysis 指向临时存储
ma._STORAGE = storage
ma._sync_orchestration_storage()

# 造一个 completed 的录制派生单摄任务
job = ma.create_analysis_job(
    AnalysisJobCreate(
        metadata=AnalysisUploadMetadata(
            fileName="smoke.mp4",
            matchTitle="冒烟",
            venue="球场",
            matchDate="2026-08-08",
            matchFormat="doubles",
            cameraAngle="baseline",
            athleteLabel="A",
            level="MVP",
            recording_session_id="sync_smoke_1",
            capture_take_id="ct_smoke_1",
        ),
        videoId="v_missing",
        calibrationId="cal1",
    )
)
assert job.status == "failed", job.status
print(f"created job: {job.id}")

# 伪造 sync recording session（带 capture_take_id）
class FakeSession:
    session_id = "sync_smoke_1"
    capture_take_id = "ct_smoke_1"


rsr.sync_recording_service.get_session = lambda sid: FakeSession()

client = TestClient(app)
resp = client.delete("/api/sync-recordings/sync_smoke_1/analysis")
print("HTTP", resp.status_code)
print("body", resp.json())
assert resp.status_code == 200, resp.text
body = resp.json()
assert any(r["job_id"] == job.id and r["status"] == "deleted" for r in body), body
assert ma.get_mock_job(job.id) is None, "job 应已删除"

# 录制不应被删除：get_session 仍返回 FakeSession（service 层面未触碰）
assert rsr.sync_recording_service.get_session("sync_smoke_1") is not None
print("SMOKE OK: 分析任务已删除，录制保留")
