from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os as _os

# 导入各个模块的路由
from app.api.routes_analysis import router as analysis_router
from app.api.routes_calibration import manual_router as manual_calibration_router
from app.api.routes_calibration import router as calibration_router
from app.api.routes_camera import router as camera_router
from app.api.routes_field_sessions import router as field_sessions_router
from app.api.routes_recording import router as recording_router
from app.api.routes_sync_recording import router as sync_recording_router
from app.api.routes_timeline_events import router as timeline_events_router
from app.api.routes_coding_actions import router as coding_actions_router
from app.api.routes_segment_editing import router as segment_editing_router
from app.api.routes_segment_editing import router2 as analysis_batch_router
from app.api.routes_video import router as video_router
# 导入配置和日志设置
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database import init_db
from app.services.mock_analysis import start_analysis_worker, stop_analysis_worker, recover_zombie_jobs

# 配置日志系统
configure_logging()
# 获取应用设置
settings = get_settings()

# 初始化 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="匹克球视频上传、标定及运动分析的 MVP 后端基础框架。",
)

# 添加跨域资源共享 (CORS) 中间件
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
    allow_origins=settings.cors_origins,
)

# 注册各个功能模块的路由
app.include_router(video_router)
app.include_router(calibration_router)
app.include_router(manual_calibration_router)
app.include_router(camera_router)
app.include_router(recording_router)
app.include_router(sync_recording_router)
app.include_router(analysis_router)
app.include_router(field_sessions_router)
app.include_router(timeline_events_router)
app.include_router(coding_actions_router)
app.include_router(segment_editing_router)
app.include_router(analysis_batch_router)

# 挂载双摄短录测试首帧静态目录
_TEST_FRAMES_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "data", "sync-recordings", "tests")
_os.makedirs(_TEST_FRAMES_DIR, exist_ok=True)
app.mount("/api/sync-recordings/test-frames", StaticFiles(directory=_TEST_FRAMES_DIR), name="test_frames")


@app.on_event("startup")
def startup_workers() -> None:
    init_db()
    start_analysis_worker()
    recover_zombie_jobs()
    _cleanup_stale_leases()


def _cleanup_stale_leases() -> None:
    try:
        from app.database import get_session_factory
        from app.camera.camera_lease_service import CameraLeaseManager
        mgr = CameraLeaseManager(get_session_factory)
        mgr.cleanup_stale_leases()
    except Exception:
        pass


@app.on_event("shutdown")
def shutdown_workers() -> None:
    stop_analysis_worker()


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    健康检查接口，用于确认服务是否正常运行
    """
    return {"status": "ok"}
