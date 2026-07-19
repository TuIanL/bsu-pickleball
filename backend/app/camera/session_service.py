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
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.camera.camera_registry import camera_registry
from app.camera.models import RecordingSession, RecordingStartRequest
from app.camera.recorder import Recorder
from app.camera.ffmpeg_utils import check_ffmpeg_available
from app.services.storage_service import StorageService
from app.services.capture_storage_service import (
    CaptureStorageError,
    create_capture_storage_plan,
    capture_storage_plan_from_dir,
    capture_storage_is_available,
    write_capture_metadata,
)

logger = logging.getLogger(__name__)

# 内存缓存：session_id -> RecordingSession
SESSIONS: dict[str, RecordingSession] = {}
# 当前正在录制的摄像头 id 与会话 id（全局变量，保证"一个摄像头同时只录一路"）
_ACTIVE_CAMERA: str | None = None
_ACTIVE_SESSION_ID: str | None = None


def _default_recorder_factory():
    return Recorder()


class SessionService:
    def __init__(
        self,
        storage: StorageService | None = None,
        recorder_factory=None,
        lease_manager=None,
        coordinator=None,
        cleanup_service=None,
    ) -> None:
        self._storage = storage or StorageService()
        self._recorder_factory = recorder_factory or _default_recorder_factory
        self._lease_manager = lease_manager
        self._coordinator = coordinator
        self._cleanup_service = cleanup_service
        self._recorder = self._recorder_factory()
        self._heartbeat_threads: dict[str, threading.Thread] = {}
        self._use_track_recorder = False
        self._active_coordinator = None

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
        return f"rec_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def _output_path(self, session_id: str, camera_id: str, session: RecordingSession | None = None) -> Path:
        # 输出路径：data/recordings/{日期}/{摄像头id}/{会话id}.mp4
        if session and session.session_dir:
            return Path(session.session_dir) / "media" / f"{session_id}.mp4"
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

        if getattr(self, "_use_track_recorder", False) and request.field_session_id:
            session, _ = self.start_with_track_recorder(request)
            return session

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
        try:
            plan = create_capture_storage_plan(f"take_{session_id}", request.storage_root)
        except CaptureStorageError as exc:
            raise RuntimeError(str(exc)) from exc
        output_path = plan.media_dir / f"{session_id}.mp4"

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
            storage_root=str(plan.storage_root),
            session_dir=str(plan.take_dir),
        )

        # 启动 FFmpeg 录制；on_exit 回调在进程退出时触发（用于标记失败）
        self._recorder.start(
            stream_url=camera.stream_url,
            output_path=output_path,
            username=camera.username,
            password=camera.password,
            fps=request.fps,
            resolution=request.resolution,
            on_exit=lambda exit_info: self._on_recorder_exit(session_id, exit_info),
        )

        # 记录当前活跃会话，并写入缓存与磁盘
        _ACTIVE_CAMERA = request.camera_id
        _ACTIVE_SESSION_ID = session_id
        SESSIONS[session_id] = session
        self._persist(session)
        write_capture_metadata(
            plan,
            manifest={
                "schema_version": "capture_manifest.v1",
                "capture_take_id": session.capture_take_id or f"take_{session_id}",
                "source_session_id": session_id,
                "capture_mode": "single",
                "status": "recording",
                "storage_root": str(plan.storage_root),
                "session_dir": str(plan.take_dir),
                "tracks": [{"slot": "cam_1", "camera_id": request.camera_id, "file": str(output_path)}],
            },
            session=session.model_dump(mode="json"),
        )

        # 启动心跳线程 + ffmpeg_registry 登记
        self._start_heartbeat(session_id)
        if hasattr(self._recorder, '_insert_ffmpeg_registry'):
            self._recorder._insert_ffmpeg_registry(
                capture_take_id=getattr(session, "capture_take_id", "") or "",
                track_id=session_id,
            )

        # 使用 Coordinator 或 fallback 创建 CaptureTake
        if field_session_id:
            self._create_or_link_capture_take(
                session_id=session_id,
                field_session_id=field_session_id,
                camera_id=request.camera_id,
                capture_mode="single",
                source_session_type="recording",
                storage_root=session.storage_root,
                session_dir=session.session_dir,
            )

        # _create_or_link_capture_take 更新了 SESSIONS 缓存中的 capture_take_id，
        # 使用缓存中的最新对象（含 capture_take_id）返回并持久化
        updated = SESSIONS[session_id]
        if updated is not session:
            self._persist(updated)
        if updated.session_dir:
            try:
                plan = capture_storage_plan_from_dir(updated.session_dir)
                write_capture_metadata(
                    plan,
                    manifest={
                        "schema_version": "capture_manifest.v1",
                        "capture_take_id": updated.capture_take_id,
                        "source_session_id": updated.session_id,
                        "capture_mode": "single",
                        "status": "recording",
                        "storage_root": updated.storage_root,
                        "session_dir": updated.session_dir,
                        "tracks": [{"slot": "cam_1", "camera_id": updated.camera_id, "file": str(plan.media_dir / f"{updated.session_id}.mp4")}],
                    },
                    session=updated.model_dump(mode="json"),
                )
            except OSError as exc:
                logger.warning("更新单摄录制 manifest 失败: %s", exc)

        logger.info("录制会话已开始: %s (camera=%s)", session_id, request.camera_id)
        return updated

    def _create_or_link_capture_take(
        self,
        session_id: str,
        field_session_id: str,
        camera_id: str,
        capture_mode: str,
        source_session_type: str,
        storage_root: str | None = None,
        session_dir: str | None = None,
    ) -> None:
        """使用 Coordinator 或 fallback 创建 CaptureTake。"""

        # 活跃录制唯一性约束：全局最多一个 active CaptureTake
        from app.services.capture_take_service import has_active_capture_take
        try:
            from app.database import get_session_factory
            check_db = get_session_factory()()
            try:
                if has_active_capture_take(check_db):
                    raise RuntimeError("系统已存在活跃录制，无法同时启动两个录制")
            finally:
                check_db.close()
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning("检查活跃录制失败（跳过约束）: %s", exc)
        if self._coordinator:
            from app.services.capture_start_coordinator import CaptureTrackSpec
            spec = CaptureTrackSpec(slot="cam_1", camera_id=camera_id, analysis_role="default")
            try:
                prepared = self._coordinator.prepare_start(
                    source_session_type=source_session_type,
                    source_session_id=session_id,
                    field_session_id=field_session_id,
                    capture_mode=capture_mode,
                    tracks=[spec],
                    storage_root=storage_root,
                    session_dir=session_dir,
                )
                session = SESSIONS.get(session_id)
                if session:
                    SESSIONS[session_id] = session.model_copy(
                        update={"capture_take_id": prepared.capture_take_id}
                    )
                self._coordinator.activate(prepared.capture_take_id)
            except Exception as exc:
                logger.error("CaptureStartCoordinator 创建 CaptureTake 失败: %s", exc)
                raise RuntimeError(f"创建 CaptureTake 失败: {exc}")
        else:
            # Fallback: 原有直连数据库逻辑
            try:
                from app.database import get_session_factory
                from app.services import capture_take_service, capture_track_service
                db = get_session_factory()()
                try:
                    take = capture_take_service.create_capture_take(
                        db,
                        field_session_id=field_session_id,
                        capture_mode=capture_mode,
                        source_session_type=source_session_type,
                        storage_root=storage_root,
                        session_dir=session_dir,
                        source_session_id=session_id,
                    )
                    capture_track_service.create_track(
                        db,
                        capture_take_id=take.id,
                        camera_id=camera_id,
                        role="primary",
                        offset_ms=0,
                        offset_source="measured",
                        sync_quality="good",
                    )
                    db.commit()
                    session = SESSIONS.get(session_id)
                    if session:
                        SESSIONS[session_id] = session.model_copy(
                            update={"capture_take_id": take.id}
                        )
                except Exception as exc:
                    db.rollback()
                    logger.warning("创建 CaptureTake 失败（录制不受影响）: %s", exc)
                finally:
                    db.close()
            except Exception as exc:
                logger.warning("连接数据库创建 CaptureTake 失败: %s", exc)

    def _start_heartbeat(self, session_id: str) -> None:
        def _beat():
            while True:
                time.sleep(1)
                s = SESSIONS.get(session_id)
                if not s or s.status != "recording":
                    break
                if not capture_storage_is_available(s.session_dir):
                    self._handle_storage_failure(session_id, "录制存储位置不可访问，录制已立即停止")
                    break
                try:
                    tid = s.capture_take_id
                    if tid and self._lease_manager:
                        self._lease_manager.heartbeat(tid)
                except Exception:
                    pass
        t = threading.Thread(target=_beat, daemon=True)
        self._heartbeat_threads[session_id] = t
        t.start()

    def _handle_storage_failure(self, session_id: str, message: str) -> None:
        session = SESSIONS.get(session_id)
        if session is None or session.status != "recording":
            return
        try:
            self._recorder.cancel()
        except Exception as exc:
            logger.warning("存储故障停止单摄 FFmpeg 失败: %s", exc)
        failed = session.model_copy(update={
            "status": "failed",
            "storage_status": "failed",
            "stopped_at": datetime.now(timezone.utc),
            "duration_sec": (datetime.now(timezone.utc) - session.started_at).total_seconds(),
            "error_message": message,
        })
        SESSIONS[session_id] = failed
        self._persist(failed)
        self._clear_active(failed.camera_id)
        self._try_close_capture_take(failed, "failed")

    def stop_session(self, session_id: str) -> RecordingSession:
        if self._active_coordinator is not None:
            coord = self._active_coordinator
            self._active_coordinator = None
            return self.stop_with_track_recorder(session_id, coord)

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
        self._recorder.stop()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds()

        output_path = self._output_path(session_id, session.camera_id, session)

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
        if session.session_dir:
            try:
                write_capture_metadata(
                    capture_storage_plan_from_dir(session.session_dir),
                    manifest={"schema_version": "capture_manifest.v1", "capture_take_id": session.capture_take_id, "source_session_id": session.session_id, "capture_mode": "single", "status": session.status, "storage_root": session.storage_root, "session_dir": session.session_dir, "video_path": session.video_path, "video_id": session.video_id},
                    session=session.model_dump(mode="json"),
                )
            except OSError as exc:
                logger.warning("写入单摄录制 manifest 失败: %s", exc)
        self._clear_active(session.camera_id)

        self._finalize_capture_take_on_stop(session, "completed")

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
        self._recorder.cancel()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds()

        output_path = self._output_path(session_id, session.camera_id, session)
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

        # 补偿流程：关闭 CaptureTake 和 open segments
        self._try_close_capture_take(session, "canceled")

        logger.info("录制会话已取消: %s", session_id)
        return session

    def delete_session(self, session_id: str) -> dict:
        from app.camera.models import RecordingDeleteResult

        session = self.get_session(session_id)
        if session is None:
            return {"session_id": session_id, "status": "not_found", "detail": "录制会话不存在"}

        if session.status == "recording":
            return {"session_id": session_id, "status": "blocked", "detail": "录制进行中，无法删除"}

        # 优先使用 CleanupService
        take_id = getattr(session, "capture_take_id", None)
        if take_id and getattr(self, "_cleanup_service", None):
            json_path = str(self._session_path(session_id))
            result = self._cleanup_service.delete_take(
                take_id,
                delete_media=True,
                session_json_path=json_path,
                video_path=getattr(session, "video_path", None),
            )
            SESSIONS.pop(session_id, None)
            self._clear_active(session.camera_id)
            return {"session_id": session_id, **result}

        # Fallback: 原有内联清理逻辑

        # 级联删除关联的 DB 记录
        take_id = session.capture_take_id
        if take_id:
            try:
                from app.database import get_session_factory
                from app.models.timeline_event import SessionTimelineEvent
                from app.models.capture_track import CaptureTrack
                from app.models.capture_coding_action import CaptureCodingAction
                from app.models.capture_segment import CaptureSegment
                from app.models.capture_take import CaptureTake

                db = get_session_factory()()
                try:
                    # 按外键依赖顺序：先删引用方，再删被引用方
                    db.query(SessionTimelineEvent).filter(
                        SessionTimelineEvent.capture_take_id == take_id
                    ).delete()
                    db.query(SessionTimelineEvent).filter(
                        SessionTimelineEvent.recording_session_id == session_id
                    ).delete()
                    db.query(CaptureTrack).filter(
                        CaptureTrack.capture_take_id == take_id
                    ).delete()
                    db.query(CaptureCodingAction).filter(
                        CaptureCodingAction.capture_take_id == take_id
                    ).delete()
                    db.query(CaptureSegment).filter(
                        CaptureSegment.capture_take_id == take_id
                    ).delete()
                    db.query(CaptureTake).filter(
                        CaptureTake.id == take_id
                    ).delete()
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    logger.warning("级联删除录制 DB 记录失败: %s", exc)
                finally:
                    db.close()
            except Exception as exc:
                logger.warning("连接数据库级联删除失败: %s", exc)

        # 从内存缓存清除
        SESSIONS.pop(session_id, None)

        # 删除会话 JSON 文件
        session_path = self.sessions_dir / f"{session_id}.json"
        if session_path.exists():
            try:
                session_path.unlink()
            except Exception as exc:
                logger.warning("删除录制会话文件失败: %s", exc)

        # 删除录制的视频文件
        if session.video_path:
            video = Path(session.video_path)
            if video.exists():
                try:
                    video.unlink()
                    logger.info("已删除录制视频文件: %s", video)
                except Exception as exc:
                    logger.warning("删除录制视频文件失败: %s", exc)

        # 兜底：对 failed 录制（video_path 可能为空），尝试按 output_path 清理
        output_path = self._output_path(session_id, session.camera_id, session)
        if output_path.exists():
            try:
                output_path.unlink()
                logger.info("已删除录制输出文件: %s", output_path)
            except Exception as exc:
                logger.warning("删除录制输出文件失败: %s", exc)

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

                    # 自愈：session JSON 为 recording 但内存中无活跃进程 → 标记 failed
                    if session.status == "recording" and self.find_active_session(session.camera_id) is None:
                        session = session.model_copy(update={
                            "status": "failed",
                            "stopped_at": datetime.now(timezone.utc),
                            "error_message": "服务中没有对应的活动录制进程，会话已恢复为失败状态",
                        })
                        self._persist(session)
                        SESSIONS[session.session_id] = session
                        if session.capture_take_id:
                            try:
                                from app.database import get_session_factory
                                from app.services.capture_take_service import finalize_capture_take
                                db = get_session_factory()()
                                try:
                                    finalize_capture_take(db, session.capture_take_id, "failed")
                                    db.commit()
                                    logger.info("自愈：单路 session %s CaptureTake %s 终态化为 failed",
                                                session.session_id, session.capture_take_id)
                                finally:
                                    db.close()
                            except Exception as exc:
                                logger.warning("自愈：单路 CaptureTake %s 终态化失败: %s", session.capture_take_id, exc)
                        else:
                            logger.info("自愈：单路 session %s 已标记 failed（无 capture_take_id）", session.session_id)

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

    def _on_recorder_exit(self, session_id: str, exit_info) -> None:
        from app.camera.recorder_exit import RecorderExit
        session = SESSIONS.get(session_id)
        if session is None or session.status != "recording":
            return

        if isinstance(exit_info, RecorderExit):
            if exit_info.stop_requested or exit_info.cancel_requested:
                logger.info("录制会话 %s FFmpeg 已由用户请求退出, returncode=%d",
                            session_id, exit_info.returncode)
                return
            logger.error("录制会话 %s FFmpeg 意外退出, returncode=%d",
                          session_id, exit_info.returncode)
            session = session.model_copy(update={
                "status": "failed",
                "stopped_at": datetime.now(timezone.utc),
                "duration_sec": (datetime.now(timezone.utc) - session.started_at).total_seconds(),
                "error_message": f"FFmpeg 意外退出, returncode={exit_info.returncode}",
            })
        else:
            returncode = exit_info
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

        self._try_close_capture_take(session, "failed")

    def _clear_active(self, camera_id: str) -> None:
        # 清空该摄像头的"活跃会话"记录（允许它再次开始录制）
        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID
        if _ACTIVE_CAMERA == camera_id:
            _ACTIVE_CAMERA = None
            _ACTIVE_SESSION_ID = None

    def _finalize_capture_take_on_stop(self, session, terminal_status: str) -> None:
        """停止/取消时显式 finalize CaptureTake。"""
        take_id = session.capture_take_id
        if not take_id:
            return
        duration_ms = int((session.duration_sec or 0) * 1000)
        self._try_close_capture_take(session, terminal_status, duration_ms)

    def _try_close_capture_take(self, session, terminal_status: str = "completed",
                                 duration_ms: int = 0) -> None:
        """关闭关联的 CaptureTake 和 open segments（幂等）。"""
        take_id = session.capture_take_id
        if not take_id:
            return
        try:
            from app.database import get_session_factory
            from app.services import capture_take_service, capture_segment_service
            db = get_session_factory()()
            try:
                ended = session.stopped_at or datetime.now(timezone.utc)
                capture_take_service.finalize_capture_take(
                    db, take_id, terminal_status,
                    ended_at=ended, duration_ms=duration_ms,
                )
                if duration_ms > 0:
                    capture_segment_service.close_all_open_for_take(db, take_id, duration_ms)
                from app.services.capture_archive_service import snapshot_capture_timeline
                snapshot_capture_timeline(db, take_id, fps=getattr(session, "fps", None))
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("finalize CaptureTake %s 失败: %s", take_id, exc)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("finalize CaptureTake 数据库连接失败: %s", exc)

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
            capture_take_id=session.capture_take_id,
            session_dir=session.session_dir,
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

    # ── TrackRecorder 集成扩展点（渐进迁移，不替换现有代码）──

    def start_with_track_recorder(self, request: RecordingStartRequest):
        """使用 TrackRecorder + Coordinator + Finalizer 启动单摄录制。"""
        from app.services.capture_start_coordinator import CaptureTrackSpec
        from app.camera.recording_policy import SingleTrackRestartPolicy
        from app.camera.capture_runtime_coordinator import CaptureRuntimeCoordinator, TrackRuntimeInfo

        # 复用现有校验和上下文继承
        if not check_ffmpeg_available():
            raise RuntimeError("FFmpeg 不可用")
        camera = camera_registry.get(request.camera_id)
        if camera is None:
            raise ValueError(f"摄像头 {request.camera_id} 不存在")

        field_session_id = request.field_session_id
        if not field_session_id:
            raise ValueError("field_session_id 不可为空")

        session_id = self._generate_session_id()
        prep = self._coordinator.prepare_start(
            source_session_type="recording",
            source_session_id=session_id,
            field_session_id=field_session_id,
            capture_mode="single",
            tracks=[CaptureTrackSpec(slot="cam_1", camera_id=request.camera_id, analysis_role="default")],
        )

        coord = CaptureRuntimeCoordinator()
        plan = create_capture_storage_plan(prep.capture_take_id, request.storage_root)
        output_dir = str(plan.fragments_dir)
        coord.start_tracks(
            take_id=prep.capture_take_id,
            tracks_info=[TrackRuntimeInfo(
                track_id=prep.tracks[0].capture_track_id,
                slot="cam_1", camera_id=request.camera_id,
                analysis_role="default",
                stream_url=camera.stream_url,
                output_dir=output_dir,
                fps=request.fps,
            )],
            policy=SingleTrackRestartPolicy(),
        )

        session = RecordingSession(
            session_id=session_id, camera_id=request.camera_id,
            field_session_id=field_session_id,
            capture_take_id=prep.capture_take_id,
            court_name=request.court_name or "",
            match_format=request.match_format or "doubles",
            camera_angle=request.camera_angle or "baseline_high",
            fps=request.fps, resolution=request.resolution,
            auto_analyze_after_stop=request.auto_analyze_after_stop,
            status="recording", started_at=datetime.now(timezone.utc),
            storage_root=str(plan.storage_root), session_dir=str(plan.take_dir),
        )
        try:
            from app.database import get_session_factory
            from app.services.capture_take_service import set_capture_take_storage
            db = get_session_factory()()
            try:
                set_capture_take_storage(db, prep.capture_take_id, storage_root=str(plan.storage_root), session_dir=str(plan.take_dir))
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("写入单摄存储位置索引失败: %s", exc)

        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID
        _ACTIVE_CAMERA = request.camera_id
        _ACTIVE_SESSION_ID = session_id
        SESSIONS[session_id] = session
        self._persist(session)
        self._coordinator.activate(prep.capture_take_id)

        self._active_coordinator = coord
        return session, coord

    def stop_with_track_recorder(self, session_id: str, coordinator):
        """使用 TrackRecorder + Finalizer 停止单摄录制。"""
        from app.camera.capture_finalizer import CaptureFinalizer
        from app.camera.capture_completion_service import CaptureCompletionService

        session = SESSIONS.get(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        frags, outcome = coordinator.stop_tracks()
        fin = CaptureFinalizer()
        comp = CaptureCompletionService()

        by_track: dict[str, list[dict]] = {}
        for f in frags:
            tid = f["track_id"]
            by_track.setdefault(tid, []).append(f)

        take_id = getattr(session, "capture_take_id", "") or ""
        decision = comp.finalize_and_decide(
            capture_take_id=take_id,
            outcome=outcome, finalizer=fin, fragment_infos_by_track=by_track)

        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0
        session = session.model_copy(update={
            "status": decision.terminal_status,
            "stopped_at": stopped_at,
            "duration_sec": duration,
            "video_id": decision.default_analysis_video_id,
        })
        SESSIONS[session_id] = session
        self._persist(session)
        self._clear_active(session.camera_id)

        return session


# 全局单例：整个程序共用一个会话服务
session_service = SessionService()
