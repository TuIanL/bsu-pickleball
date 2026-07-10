"""
录制会话生命周期管理 —— 开始 / 停止 / 取消录制，并持久化会话元数据。

"录制会话"代表一次完整的录制过程。本模块负责：
- 开始：校验摄像头、生成会话、启动 FFmpeg 录制
- 停止：优雅结束、登记视频、可选自动创建分析任务
- 取消：直接终止并删除半成品文件
- 查询：列出 / 读取会话

会话信息持久化到 data/recordings/sessions/{session_id}.json，内存也有缓存。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.camera.camera_registry import camera_registry
from app.camera.models import RecordingSession, RecordingStartRequest
from app.camera.recorder import Recorder, check_ffmpeg_available
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# 内存缓存：session_id -> RecordingSession
SESSIONS: dict[str, RecordingSession] = {}
# 全局唯一的录制器对象（同一时刻只录一路）
_RECORDER = Recorder()
# 当前正在录制的摄像头 id 与会话 id（全局变量，保证"一个摄像头同时只录一路"）
_ACTIVE_CAMERA: str | None = None
_ACTIVE_SESSION_ID: str | None = None


class SessionService:
    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or StorageService()

    @property
    def sessions_dir(self) -> Path:
        # 会话元数据存放目录
        return Path("data/recordings/sessions")

    @property
    def recordings_dir(self) -> Path:
        # 录制视频文件存放目录
        return Path("data/recordings")

    def _session_path(self, session_id: str) -> Path:
        # 拼出某个会话的 JSON 路径
        return self.sessions_dir / f"{session_id}.json"

    def _generate_session_id(self) -> str:
        # 用当前时间生成形如 rec_20260706_210000 的会话 id
        now = datetime.now(timezone.utc)
        return f"rec_{now.strftime('%Y%m%d_%H%M%S')}"

    def _output_path(self, session_id: str, camera_id: str) -> Path:
        # 输出路径：data/recordings/{日期}/{摄像头id}/{会话id}.mp4
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.recordings_dir / date_str / camera_id / f"{session_id}.mp4"

    def find_active_session(self, camera_id: str) -> RecordingSession | None:
        # 查找该摄像头是否有正在进行的录制会话
        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID
        if _ACTIVE_CAMERA == camera_id and _ACTIVE_SESSION_ID:
            return SESSIONS.get(_ACTIVE_SESSION_ID)
        return None

    def start_session(self, request: RecordingStartRequest) -> RecordingSession:
        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID

        # 前置检查：FFmpeg 是否可用
        if not check_ffmpeg_available():
            raise RuntimeError("FFmpeg 不可用，无法开始录制")

        # 摄像头必须存在
        camera = camera_registry.get(request.camera_id)
        if camera is None:
            raise ValueError(f"摄像头 {request.camera_id} 不存在")

        # 检查是否被双摄同步录制占用
        from app.camera.sync_recorder_service import sync_recording_service
        if sync_recording_service.is_camera_in_sync_recording(request.camera_id):
            raise RuntimeError(f"摄像头 {request.camera_id} 正在参与双摄同步录制，无法单独开始录制")

        # 同一摄像头不能同时录两路
        if self.find_active_session(request.camera_id) is not None:
            raise RuntimeError(f"摄像头 {request.camera_id} 正在录制中")

        # Field Session 校验与上下文继承
        field_session_id = request.field_session_id
        court_name = request.court_name
        match_format = request.match_format or "doubles"

        if field_session_id:
            from app.database import get_session_factory
            from app.services.field_session_service import get_field_session
            db = get_session_factory()()
            try:
                fs = get_field_session(db, field_session_id)
                if fs is None:
                    raise ValueError(f"Field Session {field_session_id} 不存在")
                # 继承：未提供时使用 Field Session 的值
                if not court_name:
                    court_name = fs.court_name
                if request.match_format is None:
                    match_format = fs.match_format.value
            finally:
                db.close()

        # 生成会话 id 与输出路径
        session_id = self._generate_session_id()
        output_path = self._output_path(session_id, request.camera_id)

        # 构造会话对象（初始状态 recording）
        session = RecordingSession(
            session_id=session_id,
            camera_id=request.camera_id,
            field_session_id=field_session_id,
            court_name=court_name,
            match_format=match_format,
            camera_angle=request.camera_angle,
            fps=request.fps,
            resolution=request.resolution,
            auto_analyze_after_stop=request.auto_analyze_after_stop,
            status="recording",
            started_at=datetime.now(timezone.utc),
        )

        # 启动 FFmpeg 录制；on_exit 回调在进程退出时触发（用于标记失败）
        _RECORDER.start(
            stream_url=camera.stream_url,
            output_path=output_path,
            username=camera.username,
            password=camera.password,
            fps=request.fps,
            resolution=request.resolution,
            on_exit=lambda code: self._on_recorder_exit(session_id, code),
        )

        # 记录当前活跃会话，并写入缓存与磁盘
        _ACTIVE_CAMERA = request.camera_id
        _ACTIVE_SESSION_ID = session_id
        SESSIONS[session_id] = session
        self._persist(session)

        logger.info("录制会话已开始: %s (camera=%s)", session_id, request.camera_id)
        return session

    def stop_session(self, session_id: str) -> RecordingSession:
        # 先从缓存取，缓存没有再从磁盘加载
        session = SESSIONS.get(session_id)
        if session is None:
            session = self._load(session_id)
            if session is None:
                raise ValueError(f"录制会话 {session_id} 不存在")

        # FFmpeg 可能已经异常退出并把会话标记为 failed；此时停止操作返回
        # 当前终态，避免前端停留在过期的 recording 状态。
        if session.status == "failed":
            self._clear_active(session.camera_id)
            return session

        # 只有 recording 状态才能停止
        if session.status != "recording":
            raise RuntimeError(f"录制会话 {session_id} 状态为 {session.status}，无法停止")

        # 优雅停止 FFmpeg
        _RECORDER.stop()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds()

        output_path = self._output_path(session_id, session.camera_id)

        # 尝试把生成的视频注册进视频系统（拿到 video_id，方便后续分析 / 播放）
        video_id = None
        if output_path.exists():
            try:
                from app.services.video_service import video_service, SUPPORTED_VIDEO_SUFFIXES
                from app.schemas.video import VideoMetadata

                file_size = output_path.stat().st_size
                suffix = output_path.suffix.lower()
                if suffix in SUPPORTED_VIDEO_SUFFIXES:
                    suffix = suffix
                else:
                    suffix = ".mp4"

                video_id = video_service.register_recording(
                    file_path=output_path,
                    original_filename=output_path.name,
                    file_size=file_size,
                )
            except Exception as exc:
                logger.error("注册录制视频到 VideoService 失败: %s", exc)

        # 如果开启了"停止后自动分析"且视频注册成功，则创建分析任务
        job_id = None
        if session.auto_analyze_after_stop and video_id:
            try:
                job_id = self._trigger_analysis(session, video_id)
            except Exception as exc:
                logger.error("自动创建分析任务失败: %s", exc)

        # 更新会话为 completed，并保存
        session = session.model_copy(update={
            "status": "completed",
            "stopped_at": stopped_at,
            "duration_sec": duration,
            "video_path": str(output_path) if output_path.exists() else None,
            "video_id": video_id,
            "auto_analysis_job_id": job_id,
        })

        SESSIONS[session_id] = session
        self._persist(session)
        self._clear_active(session.camera_id)

        logger.info("录制会话已停止: %s (duration=%.1fs)", session_id, duration)
        return session

    def cancel_session(self, session_id: str) -> RecordingSession:
        # 先从缓存取，缓存没有再从磁盘加载
        session = SESSIONS.get(session_id)
        if session is None:
            session = self._load(session_id)
            if session is None:
                raise ValueError(f"录制会话 {session_id} 不存在")

        # 已失败的录制已经是终态；返回当前会话让客户端刷新并解除录制锁。
        if session.status == "failed":
            self._clear_active(session.camera_id)
            return session

        # 只有 recording 状态才能取消
        if session.status != "recording":
            raise RuntimeError(f"录制会话 {session_id} 状态为 {session.status}，无法取消")

        # 直接杀掉 FFmpeg（取消 = 放弃本次录制）
        _RECORDER.cancel()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds()

        output_path = self._output_path(session_id, session.camera_id)
        # 删除半成品视频文件
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception as exc:
                logger.warning("删除部分录制文件失败: %s", exc)

        session = session.model_copy(update={
            "status": "canceled",
            "stopped_at": stopped_at,
            "duration_sec": duration,
        })

        SESSIONS[session_id] = session
        self._persist(session)
        self._clear_active(session.camera_id)

        logger.info("录制会话已取消: %s", session_id)
        return session

    def delete_session(self, session_id: str) -> dict:
        from app.camera.models import RecordingDeleteResult

        session = self.get_session(session_id)
        if session is None:
            return {"session_id": session_id, "status": "not_found", "detail": "录制会话不存在"}

        # 正在录制中的不允许删除
        if session.status == "recording":
            return {"session_id": session_id, "status": "blocked", "detail": "录制进行中，无法删除"}

        # 从内存缓存清除
        SESSIONS.pop(session_id, None)

        # 删除会话 JSON 文件
        session_path = self.sessions_dir / f"{session_id}.json"
        if session_path.exists():
            try:
                session_path.unlink()
            except Exception as exc:
                logger.warning("删除录制会话文件失败: %s", exc)

        # 清除活跃录制锁（如果是当前活跃的）
        self._clear_active(session.camera_id)

        logger.info("录制会话已删除: %s", session_id)
        return {"session_id": session_id, "status": "deleted", "detail": "录制会话已删除"}

    def get_session(self, session_id: str) -> RecordingSession | None:
        # 先缓存后磁盘
        cached = SESSIONS.get(session_id)
        if cached is not None:
            return cached
        return self._load(session_id)

    def list_sessions(self, camera_id: str | None = None, status: str | None = None, field_session_id: str | None = None) -> list[RecordingSession]:
        result: list[RecordingSession] = []

        # 遍历所有会话 JSON（按文件名倒序，新的在前）
        if self.sessions_dir.exists():
            for path in sorted(self.sessions_dir.glob("*.json"), reverse=True):
                try:
                    session = RecordingSession.model_validate(self._storage.read_json(path))
                    SESSIONS[session.session_id] = session
                    # 按过滤条件跳过不匹配的
                    if camera_id and session.camera_id != camera_id:
                        continue
                    if status and session.status != status:
                        continue
                    if field_session_id and session.field_session_id != field_session_id:
                        continue
                    result.append(session)
                except Exception:
                    pass

        return result

    def _on_recorder_exit(self, session_id: str, returncode: int) -> None:
        # FFmpeg 进程退出回调：只有仍在 recording 且异常退出（非 0）才标记为 failed
        session = SESSIONS.get(session_id)
        if session is None or session.status != "recording":
            return

        if returncode != 0:
            logger.error("录制会话 %s FFmpeg 异常退出, returncode=%d", session_id, returncode)
            session = session.model_copy(update={
                "status": "failed",
                "stopped_at": datetime.now(timezone.utc),
                "duration_sec": (datetime.now(timezone.utc) - session.started_at).total_seconds(),
                "error_message": f"FFmpeg 进程异常退出, returncode={returncode}",
            })
            SESSIONS[session_id] = session
            self._persist(session)
            self._clear_active(session.camera_id)

    def _clear_active(self, camera_id: str) -> None:
        # 清空该摄像头的"活跃会话"记录（允许它再次开始录制）
        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID
        if _ACTIVE_CAMERA == camera_id:
            _ACTIVE_CAMERA = None
            _ACTIVE_SESSION_ID = None

    def _persist(self, session: RecordingSession) -> None:
        # 把会话写入磁盘 JSON
        self._storage.write_json(self._session_path(session.session_id), session.model_dump(mode="json"))

    def _load(self, session_id: str) -> RecordingSession | None:
        # 从磁盘读取会话
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return RecordingSession.model_validate(self._storage.read_json(path))
        except Exception:
            return None

    def _trigger_analysis(self, session: RecordingSession, video_id: str) -> str | None:
        # 停止录制后，自动创建一个分析任务（复用分析模块的逻辑）
        from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
        from app.services.mock_analysis import create_analysis_job

        # 组装分析任务需要的元数据
        metadata = AnalysisUploadMetadata(
            fileName=session.session_id + ".mp4",
            sourceFps=float(session.fps),
            matchTitle=f"{session.court_name} {session.started_at.strftime('%Y-%m-%d %H:%M')}",
            venue=session.court_name,
            matchDate=session.started_at.strftime("%Y-%m-%d"),
            matchFormat=session.match_format,
            cameraAngle=_map_camera_angle(session.camera_angle),
            athleteLabel="",
            level="",
        )

        # 调用分析模块创建任务
        job = create_analysis_job(AnalysisJobCreate(
            metadata=metadata,
            videoId=video_id,
            sourceFps=float(session.fps),
            frameStride=1,
        ))

        return job.id


# 把系统内部的机位角度标识映射成分析模块认识的枚举值
def _map_camera_angle(angle: str) -> str:
    mapping = {
        "baseline_high": "elevated",
        "baseline": "baseline",
        "sideline": "sideline",
        "elevated": "elevated",
        "overhead": "elevated",
        "side": "sideline",
    }
    return mapping.get(angle, "unknown")


# 全局单例：整个程序共用一个会话服务
session_service = SessionService()
