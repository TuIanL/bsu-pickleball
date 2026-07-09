"""
双摄同步录制服务 —— 核心录制引擎 + 会话生命周期管理。

从师哥的独立脚本 ShouDong.py 提炼而来，适配 FastAPI 后端架构。
核心控制模型：
- 每一路摄像头由独立 FFmpeg 进程录制为 .ts 分段
- 主控制线程同时启动所有进程
- 任一路异常退出或达到分段时长后，控制线程终止所有路并同步进入下一段
- 用户停止时优雅终止所有进程并生成 completed 会话
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import cv2

from app.camera.camera_registry import camera_registry
from app.camera.models import (
    CameraSlotConfig,
    CameraSlotRole,
    SyncRecordingSession,
    SyncRecordingStatus,
    SyncSegment,
    SyncSegmentFile,
    SyncSegmentStatus,
    SyncStartRequest,
    SyncStopResponse,
    SyncTestRequest,
    SyncTestResult,
)

logger = logging.getLogger(__name__)

# 全局内存缓存：session_id -> SyncRecordingSession
SYNC_SESSIONS: dict[str, SyncRecordingSession] = {}
# 全局活跃同步会话 id
_ACTIVE_SYNC_SESSION_ID: str | None = None
# 活跃摄像头集合（被双摄录制占用的摄像头 id）
_ACTIVE_SYNC_CAMERAS: set[str] = set()


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def check_ffmpeg_available() -> bool:
    """检查系统是否安装了 FFmpeg"""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
        )
        return True
    except Exception:
        return False


def _get_ffmpeg_path() -> str:
    """获取 FFmpeg 路径"""
    if os.name == "nt":
        for path in os.environ.get("PATH", "").split(os.pathsep):
            ff_path = os.path.join(path, "ffmpeg.exe")
            if os.path.exists(ff_path):
                return ff_path
    return "ffmpeg"


def _extract_first_and_last_frames(video_file: str) -> tuple[str | None, str | None]:
    """提取视频的第一帧和最后一帧，返回 (首帧路径, 尾帧路径)"""
    try:
        base_name = os.path.splitext(video_file)[0]
        first_frame_file = f"{base_name}_first_frame.jpg"
        last_frame_file = f"{base_name}_last_frame.jpg"

        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            return None, None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            cap.release()
            return None, None

        # 提取第一帧
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, first_frame = cap.read()
        if ret:
            cv2.imwrite(first_frame_file, first_frame)

        # 提取最后一帧
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
        ret, last_frame = cap.read()
        if ret:
            cv2.imwrite(last_frame_file, last_frame)

        cap.release()
        return first_frame_file if ret else None, last_frame_file if ret else None
    except Exception as e:
        logger.warning("提取视频帧失败 %s: %s", video_file, e)
        return None, None


def _parse_ip_from_url(url: str) -> str:
    """从 RTSP URL 中提取 IP 地址"""
    try:
        return url.split("/")[2].split(":")[0]
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# SyncRecorder —— 双摄同步录制引擎
# ═══════════════════════════════════════════════════════════════════════════

class SyncRecorder:
    """
    双摄同步录制引擎。

    核心逻辑来自 ShouDong.py:
    - _record_multiple_streams_sync: 主控制循环
    - _record_segment_for_stream: 单路分段录制（FFmpeg 子进程管理）
    - 同时启动两路 FFmpeg 进程，任一路异常退出后同步重启下一分段
    """

    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[bytes]] = []
        self.is_recording = False
        self.main_recording_thread: threading.Thread | None = None
        self.segment_index = 1
        self.failure_event = threading.Event()
        self.stop_event = threading.Event()
        self.session_dir: str = ""
        self.recording_threads: list[threading.Thread] = []
        self.fps: int = 30
        self.resolution: str = "1920x1080"
        self._segment_callback: Optional[callable] = None

    # ── 生命周期回调 ────────────────────────────────────────────────
    on_segment_start: Optional[callable] = None
    on_segment_end: Optional[callable] = None
    on_stream_error: Optional[callable] = None
    on_all_complete: Optional[callable] = None

    def _get_stream_output_name(self, url: str, camera_id: str, segment_idx: int) -> str:
        """生成分段输出文件名"""
        ip = _parse_ip_from_url(url)
        return f"{camera_id}_s{segment_idx}.ts"

    def _normalize_stream_config(
        self,
        camera_id: str,
        config: str | tuple[str, CameraSlotRole],
        index: int,
    ) -> tuple[str, CameraSlotRole]:
        if isinstance(config, tuple):
            return config
        return config, "cam_1" if index == 0 else "cam_2"

    def _record_segment_for_stream(
        self, url: str, camera_id: str, role: CameraSlotRole, duration: int | None,
    ) -> SyncSegmentFile:
        """录制单个 RTSP 流的一个分段。"""
        ffmpeg_path = _get_ffmpeg_path()
        output_filename = self._get_stream_output_name(url, camera_id, self.segment_index)
        output_file = os.path.join(self.session_dir, output_filename)

        cmd = [
            ffmpeg_path,
            "-y",
            "-rtsp_transport", "tcp",
            "-i", url,
            "-c", "copy",
            "-f", "mpegts",
        ]
        if duration:
            cmd.extend(["-t", str(duration)])
        cmd.append(output_file)

        logger.debug("[%s] FFmpeg cmd: %s", camera_id, " ".join(cmd))

        started_at = datetime.now(timezone.utc)
        process = None
        error_msg: str | None = None

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self.processes.append(process)

            # 监控进程直到退出或停止信号
            while process.poll() is None and not self.stop_event.is_set():
                time.sleep(0.5)

            return_code = process.poll()
            ended_at = datetime.now(timezone.utc)

            is_failure = return_code is not None and return_code != 0

            if is_failure:
                _, stderr_data = process.communicate()
                error_msg = f"FFmpeg exit code {return_code}"
                if stderr_data:
                    error_msg += ": " + stderr_data.decode("utf-8", errors="ignore")[-200:]
                logger.error("🚨 [%s] 分段 %d 录制异常: %s", camera_id, self.segment_index, error_msg)
                self.failure_event.set()
            else:
                logger.info("✅ [%s] 分段 %d 录制完成", camera_id, self.segment_index)

        except Exception as e:
            logger.exception("🔥 [%s] 录制异常: %s", camera_id, e)
            error_msg = str(e)
            self.failure_event.set()
            ended_at = datetime.now(timezone.utc)
        finally:
            if process is not None and process in self.processes:
                self.processes.remove(process)

        # 提取首帧尾帧
        if os.path.exists(output_file):
            _extract_first_and_last_frames(output_file)

        file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        if file_size == 0:
            error_msg = error_msg or "输出文件为空"

        return SyncSegmentFile(
            camera_id=camera_id,
            role=role,
            file_path=output_file,
            file_size=file_size,
            started_at=started_at,
            ended_at=ended_at or datetime.now(timezone.utc),
            error_message=error_msg,
        )

    def _terminate_all_processes(self) -> None:
        """强制终止所有 FFmpeg 进程"""
        if not self.processes:
            return
        logger.info("正在终止所有 FFmpeg 进程...")
        for process in list(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        self.processes = []

    def _record_multiple_streams_sync(
        self,
        stream_urls: dict[str, tuple[str, CameraSlotRole]],  # camera_id -> (stream_url, role)
        duration: int | None = None,
    ) -> None:
        """同步录制多个视频流的主控制循环（ShouDong.py 核心逻辑）"""
        restart_count = 0

        while self.is_recording:
            self.stop_event.clear()
            self.failure_event.clear()
            self.recording_threads = []

            segment_started = datetime.now(timezone.utc)
            logger.info("--- 🎬 开始同步录制 第 %d 段 (重启次数=%d) ---", self.segment_index, restart_count)

            if self.on_segment_start:
                self.on_segment_start(self.segment_index, restart_count)

            # 为每个流创建录制线程
            results: dict[str, SyncSegmentFile] = {}
            results_lock = threading.Lock()

            for index, (camera_id, config) in enumerate(stream_urls.items()):
                stream_url, role = self._normalize_stream_config(camera_id, config, index)
                def _record_with_result(cid: str, surl: str, slot_role: CameraSlotRole) -> None:
                    result = self._record_segment_for_stream(surl, cid, slot_role, duration)
                    with results_lock:
                        results[cid] = result

                thread = threading.Thread(
                    target=_record_with_result,
                    args=(camera_id, stream_url, role),
                )
                thread.daemon = True
                self.recording_threads.append(thread)
                thread.start()

            logger.info("   %d 个流已启动", len(self.recording_threads))

            # 等待失败信号或段结束
            try:
                self.failure_event.wait(timeout=duration + 2 if duration else None)
            except KeyboardInterrupt:
                pass

            # 停止所有进程
            self.stop_event.set()
            self._terminate_all_processes()

            # 等待所有线程退出
            for thread in self.recording_threads:
                thread.join(timeout=10)

            # 收集分段文件
            segment = SyncSegment(
                segment_index=self.segment_index,
                status="completed",
                files=list(results.values()),
                started_at=segment_started,
                ended_at=datetime.now(timezone.utc),
                restart_count=restart_count,
            )

            # 检查是否有失败
            has_failure = any(f.error_message for f in results.values())
            if has_failure:
                segment.status = "failed"
                errors = [f"{f.camera_id}: {f.error_message}" for f in results.values() if f.error_message]
                segment.error_message = "; ".join(errors)

            if self.on_segment_end:
                self.on_segment_end(segment)

            if not self.is_recording:
                logger.info("   [同步控制] 用户已停止录制。会话结束。")
                break

            if self.failure_event.is_set():
                restart_count += 1
                logger.info("   🚨 检测到流中断，同步重启进入第 %d 段", self.segment_index + 1)
                if self.on_stream_error:
                    self.on_stream_error(self.segment_index, restart_count)

            self.segment_index += 1
            time.sleep(1)

        self.is_recording = False
        logger.info("所有视频流录制会话已结束。")

        if self.on_all_complete:
            self.on_all_complete()

    def start_recording(
        self,
        stream_configs: dict[str, tuple[str, CameraSlotRole]],  # camera_id -> (stream_url, role)
        output_dir: str,
        duration: int | None = None,
        fps: int = 30,
        resolution: str = "1920x1080",
    ) -> None:
        """开始同步录制"""
        if self.is_recording:
            raise RuntimeError("同步录制已在运行中")

        self.is_recording = True
        self.segment_index = 1
        self.processes = []
        self.recording_threads = []
        self.session_dir = output_dir
        self.fps = fps
        self.resolution = resolution

        os.makedirs(self.session_dir, exist_ok=True)
        logger.info("创建录制会话目录: %s", self.session_dir)

        self.main_recording_thread = threading.Thread(
            target=self._record_multiple_streams_sync,
            args=(stream_configs, duration),
        )
        self.main_recording_thread.daemon = True
        self.main_recording_thread.start()
        logger.info("双摄同步录制主控制线程已启动。")

    def start_test(
        self,
        stream_configs: dict[str, tuple[str, CameraSlotRole]],
        output_dir: str,
        duration: int = 5,
    ) -> SyncTestResult:
        """执行短录测试（同步阻塞，不创建正式会话）"""
        os.makedirs(output_dir, exist_ok=True)

        self.segment_index = 1
        self.processes = []
        self.recording_threads = []
        self.session_dir = output_dir
        self.stop_event.clear()
        self.failure_event.clear()

        results: dict[str, SyncSegmentFile] = {}
        results_lock = threading.Lock()

        for index, (camera_id, config) in enumerate(stream_configs.items()):
            stream_url, role = self._normalize_stream_config(camera_id, config, index)
            def _record_with_result(cid: str, surl: str, slot_role: CameraSlotRole) -> None:
                result = self._record_segment_for_stream(surl, cid, slot_role, duration)
                with results_lock:
                    results[cid] = result

            thread = threading.Thread(target=_record_with_result, args=(camera_id, stream_url, role))
            thread.daemon = True
            self.recording_threads.append(thread)
            thread.start()

        # 等待测试完成
        for thread in self.recording_threads:
            thread.join(timeout=duration + 10)

        self.stop_event.set()
        self._terminate_all_processes()

        # 提取测试结果
        cam_1_id = list(stream_configs.keys())[0] if stream_configs else "cam_1"
        cam_2_id = list(stream_configs.keys())[1] if len(stream_configs) > 1 else "cam_2"

        cam_1_result = results.get(cam_1_id, SyncSegmentFile(
            camera_id=cam_1_id, role="cam_1", file_path="",
        ))
        cam_2_result = results.get(cam_2_id, SyncSegmentFile(
            camera_id=cam_2_id, role="cam_2", file_path="",
        ))

        # 提取首尾帧
        p_first, p_last = None, None
        s_first, s_last = None, None
        if cam_1_result.file_path and os.path.exists(cam_1_result.file_path):
            p_first, p_last = _extract_first_and_last_frames(cam_1_result.file_path)
        if cam_2_result.file_path and os.path.exists(cam_2_result.file_path):
            s_first, s_last = _extract_first_and_last_frames(cam_2_result.file_path)

        # 构造首帧 URL（通过 static serve 提供 HTTP 访问）
        def _build_first_frame_url(file_path: str | None) -> tuple[str | None, bool]:
            if file_path and os.path.exists(file_path):
                rel = os.path.relpath(file_path, os.path.join(os.getcwd(), "data", "sync-recordings", "tests"))
                return f"/api/sync-recordings/test-frames/{rel}", True
            return None, False

        cam_1_url, cam_1_exists = _build_first_frame_url(p_first)
        cam_2_url, cam_2_exists = _build_first_frame_url(s_first)

        return SyncTestResult(
            success=(not cam_1_result.error_message and not cam_2_result.error_message),
            cam_1_id=cam_1_id,
            cam_2_id=cam_2_id,
            duration_sec=float(duration),
            cam_1_online=(cam_1_result.file_size > 0),
            cam_2_online=(cam_2_result.file_size > 0),
            cam_1_first_frame_url=cam_1_url,
            cam_2_first_frame_url=cam_2_url,
            cam_1_first_frame_exists=cam_1_exists,
            cam_2_first_frame_exists=cam_2_exists,
            cam_1_file_size=cam_1_result.file_size,
            cam_2_file_size=cam_2_result.file_size,
            cam_1_error=cam_1_result.error_message,
            cam_2_error=cam_2_result.error_message,
            test_completed_at=datetime.now(timezone.utc),
        )

    def stop_recording(self) -> None:
        """停止录制"""
        if not self.is_recording:
            return

        logger.info("正在停止双摄同步录制...")
        self.is_recording = False
        self.stop_event.set()
        self.failure_event.set()
        self._terminate_all_processes()

        if self.main_recording_thread and self.main_recording_thread.is_alive():
            self.main_recording_thread.join(timeout=10)

        self.segment_index = 1
        logger.info("双摄同步录制已停止")


# ═══════════════════════════════════════════════════════════════════════════
# SyncRecordingService —— 会话生命周期 + 业务逻辑
# ═══════════════════════════════════════════════════════════════════════════

class SyncRecordingService:
    """双摄同步录制服务，管理会话生命周期、持久化、摄像头占用。"""

    def __init__(self) -> None:
        self._recorder = SyncRecorder()
        self._segments: list[SyncSegment] = []  # 累积分段信息

    # ── 摄像头占用检查 ────────────────────────────────────────────

    def _check_camera_available(self, camera_id: str) -> None:
        """检查摄像头是否可用（不被单摄或双摄占用）"""
        # 检查双摄占用
        global _ACTIVE_SYNC_CAMERAS
        if camera_id in _ACTIVE_SYNC_CAMERAS:
            raise RuntimeError(f"摄像头 {camera_id} 正在参与双摄同步录制")

        # 检查单摄占用
        from app.camera.session_service import session_service
        active = session_service.find_active_session(camera_id)
        if active is not None:
            raise RuntimeError(f"摄像头 {camera_id} 正在单摄录制中")

    def is_camera_in_sync_recording(self, camera_id: str) -> bool:
        """查询摄像头是否正在参与双摄录制"""
        global _ACTIVE_SYNC_CAMERAS
        return camera_id in _ACTIVE_SYNC_CAMERAS

    # ── 会话持久化 ────────────────────────────────────────────────

    @property
    def sessions_dir(self) -> Path:
        return Path("data/sync-recordings/sessions")

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _output_dir(self, session_id: str) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return Path("data/sync-recordings") / date_str / session_id

    def _generate_session_id(self) -> str:
        now = datetime.now(timezone.utc)
        return f"sync_{now.strftime('%Y%m%d_%H%M%S')}"

    def _persist(self, session: SyncRecordingSession) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self._session_path(session.session_id)
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.model_dump(mode="json"), f, indent=2, default=str)

    def _load(self, session_id: str) -> SyncRecordingSession | None:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 旧 JSON 兼容映射：primary → cam_1, secondary → cam_2
            if "camera_slots" in data and isinstance(data["camera_slots"], dict):
                slots = data["camera_slots"]
                if "primary" in slots and "cam_1" not in slots:
                    slots["cam_1"] = slots.pop("primary")
                    if "role" in slots["cam_1"] and slots["cam_1"]["role"] == "primary":
                        slots["cam_1"]["role"] = "cam_1"
                if "secondary" in slots and "cam_2" not in slots:
                    slots["cam_2"] = slots.pop("secondary")
                    if "role" in slots["cam_2"] and slots["cam_2"]["role"] == "secondary":
                        slots["cam_2"]["role"] = "cam_2"
            # primary_video_id → default_analysis_video_id
            if "primary_video_id" in data and "default_analysis_video_id" not in data:
                data["default_analysis_video_id"] = data.pop("primary_video_id")

            return SyncRecordingSession.model_validate(data)
        except Exception as e:
            logger.warning("加载同步会话失败 %s: %s", session_id, e)
            return None

    # ── 录制生命周期 ──────────────────────────────────────────────

    def start_session(self, request: SyncStartRequest) -> SyncRecordingSession:
        """开始双摄同步录制"""
        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS

        # 检查 FFmpeg
        if not check_ffmpeg_available():
            raise RuntimeError("FFmpeg 不可用，无法开始同步录制")

        # 检查两个摄像头不同
        if request.cam_1_id == request.cam_2_id:
            raise ValueError("两个机位不能是同一个摄像头")

        # 检查摄像头存在
        cam_1 = camera_registry.get(request.cam_1_id)
        cam_2 = camera_registry.get(request.cam_2_id)
        if cam_1 is None:
            raise ValueError(f"底线机位 A 摄像头 {request.cam_1_id} 不存在")
        if cam_2 is None:
            raise ValueError(f"底线机位 B 摄像头 {request.cam_2_id} 不存在")

        # 检查摄像头占用
        self._check_camera_available(request.cam_1_id)
        self._check_camera_available(request.cam_2_id)

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
                if not court_name:
                    court_name = fs.court_name
                if request.match_format is None:
                    match_format = fs.match_format.value
            finally:
                db.close()

        # 生成会话
        session_id = self._generate_session_id()
        output_dir = self._output_dir(session_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        session = SyncRecordingSession(
            session_id=session_id,
            field_session_id=field_session_id,
            status="recording",
            camera_slots={
                "cam_1": CameraSlotConfig(
                    role="cam_1",
                    camera_id=request.cam_1_id,
                    camera_angle=request.cam_1_angle,
                    stream_url_snapshot=cam_1.stream_url,
                ),
                "cam_2": CameraSlotConfig(
                    role="cam_2",
                    camera_id=request.cam_2_id,
                    camera_angle=request.cam_2_angle,
                    stream_url_snapshot=cam_2.stream_url,
                ),
            },
            output_dir=str(output_dir),
            court_name=court_name,
            match_format=match_format,
            fps=request.fps,
            resolution=request.resolution,
            auto_analyze_after_stop=request.auto_analyze_after_stop,
            started_at=datetime.now(timezone.utc),
        )

        # 记录活跃状态
        _ACTIVE_SYNC_SESSION_ID = session_id
        _ACTIVE_SYNC_CAMERAS = {request.cam_1_id, request.cam_2_id}

        # 重置分段累积 + 绑定录制器回调
        self._segments = []

        def on_segment_start(idx: int, restarts: int) -> None:
            logger.info("===== 分段 %d 开始 (重启 %d 次) =====", idx, restarts)

        def on_segment_end(segment: SyncSegment) -> None:
            self._segments.append(segment)
            session.segments = self._segments
            session.total_restarts = sum(s.restart_count for s in self._segments)
            self._persist(session)

        def on_stream_error(idx: int, restarts: int) -> None:
            logger.warning("⚠️ 分段 %d 失败，同步重启中 (重启计数=%d)", idx, restarts)

        def on_all_complete() -> None:
            # 录制器退出后完成会话
            s = SYNC_SESSIONS.get(session_id)
            if s and s.status == "recording":
                self._complete_session(session_id)

        self._recorder = SyncRecorder()
        self._recorder.on_segment_start = on_segment_start
        self._recorder.on_segment_end = on_segment_end
        self._recorder.on_stream_error = on_stream_error
        self._recorder.on_all_complete = on_all_complete

        # 启动录制
        stream_configs = {
            request.cam_1_id: (cam_1.stream_url, "cam_1"),
            request.cam_2_id: (cam_2.stream_url, "cam_2"),
        }

        self._recorder.start_recording(
            stream_configs=stream_configs,
            output_dir=str(output_dir),
            duration=None,
            fps=request.fps,
            resolution=request.resolution,
        )

        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        logger.info("双摄同步录制会话已开始: %s", session_id)
        return session

    def stop_session(self, session_id: str) -> SyncStopResponse:
        """停止双摄同步录制"""
        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS

        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"同步录制会话 {session_id} 不存在")

        if session.status != "recording":
            raise RuntimeError(f"会话 {session_id} 状态为 {session.status}，无法停止")

        # 停止录制器
        self._recorder.stop_recording()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0

        # 更新会话
        session = session.model_copy(update={
            "status": "completed",
            "stopped_at": stopped_at,
            "duration_sec": duration,
            "segments": self._segments,
            "total_restarts": sum(s.restart_count for s in self._segments),
        })

        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        # 清除活跃状态
        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()

        session, default_analysis_video_id, analysis_available, analysis_blocked_reason = self._register_session_videos(session)

        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        logger.info("双摄同步录制已停止: %s (duration=%.1fs, analysis_available=%s)",
                     session_id, duration, analysis_available)

        return SyncStopResponse(
            session=session,
            default_analysis_video_id=default_analysis_video_id,
            analysis_available=analysis_available,
            analysis_blocked_reason=analysis_blocked_reason,
        )

    def _complete_session(self, session_id: str) -> None:
        """录制器自动退出后完成会话"""
        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS

        session = SYNC_SESSIONS.get(session_id)
        if not session or session.status != "recording":
            return

        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0

        session = session.model_copy(update={
            "status": "failed",
            "stopped_at": stopped_at,
            "duration_sec": duration,
            "segments": self._segments,
            "error_message": "录制器异常退出",
            "total_restarts": sum(s.restart_count for s in self._segments),
        })

        SYNC_SESSIONS[session_id] = session
        self._persist(session)
        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()
        logger.warning("双摄同步录制会话自动结束(异常): %s", session_id)

    def _register_session_videos(
        self,
        session: SyncRecordingSession,
    ) -> tuple[SyncRecordingSession, str | None, bool, str | None]:
        """把已完成双摄会话的两路分段登记为可 HTTP 播放的视频。"""
        analysis_available = False
        analysis_blocked_reason: str | None = None
        default_analysis_video_id = session.default_analysis_video_id
        registered_video_ids: dict[CameraSlotRole, str] = dict(session.registered_video_ids or {})
        associated_video_paths: list[str] = []

        for role in ("cam_1", "cam_2"):
            slot = session.camera_slots.get(role)
            if not slot:
                continue

            files: list[str] = []
            for seg in session.segments:
                for f in seg.files:
                    if f.camera_id == slot.camera_id and f.file_path:
                        associated_video_paths.append(f.file_path)
                        if f.file_size > 0 and os.path.exists(f.file_path):
                            files.append(f.file_path)

            if role in registered_video_ids:
                if role == "cam_1":
                    default_analysis_video_id = registered_video_ids[role]
                    analysis_available = True
                continue

            if files:
                video_id = self._register_recorded_slot_video(session, files, slot)
                if video_id:
                    registered_video_ids[role] = video_id
                    if role == "cam_1":
                        default_analysis_video_id = video_id
                        analysis_available = True
                elif role == "cam_1":
                    analysis_blocked_reason = "默认分析视频注册失败，请检查文件完整性"
            elif role == "cam_1":
                analysis_blocked_reason = "底线机位 A 无有效分段文件"

        session = session.model_copy(update={
            "default_analysis_video_id": default_analysis_video_id,
            "registered_video_ids": registered_video_ids,
            "associated_video_paths": associated_video_paths,
        })
        SYNC_SESSIONS[session.session_id] = session
        self._persist(session)
        return session, default_analysis_video_id, analysis_available, analysis_blocked_reason

    def _register_recorded_slot_video(
        self, session: SyncRecordingSession, file_paths: list[str], slot: CameraSlotConfig,
    ) -> str | None:
        """登记一个机位的视频到 VideoService"""
        try:
            from app.services.video_service import video_service, SUPPORTED_VIDEO_SUFFIXES

            # 转码/合并 .ts 分段为单个 MP4
            merged_path = self._merge_segments(
                file_paths,
                os.path.join(session.output_dir, f"{slot.camera_id}_merged.mp4"),
            )

            file_path = Path(merged_path) if merged_path else Path(file_paths[0])
            if not file_path.exists():
                return None

            file_size = file_path.stat().st_size
            suffix = file_path.suffix.lower()
            if suffix not in SUPPORTED_VIDEO_SUFFIXES:
                suffix = ".mp4"

            video_id = video_service.register_recording(
                file_path=file_path,
                original_filename=file_path.name,
                file_size=file_size,
            )
            return video_id
        except Exception as exc:
            logger.error("登记主机位视频失败: %s", exc)
            return None

    def _merge_segments(self, file_paths: list[str], output_path: str) -> str | None:
        """合并 .ts 分段为单个 MP4 文件"""
        if not file_paths:
            return None

        if len(file_paths) == 1:
            # 单文件直接转码为 MP4
            mp4_path = output_path.replace(".mp4", "") + ".mp4"
            cmd = [
                "ffmpeg", "-y",
                "-i", file_paths[0],
                "-c", "copy",
                "-movflags", "+faststart",
                mp4_path,
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
                if os.path.exists(mp4_path):
                    return mp4_path
            except Exception as e:
                logger.warning("单文件转码MP4失败: %s", e)
            return file_paths[0]

        # 多文件合并
        concat_file = output_path + ".concat.txt"
        try:
            with open(concat_file, "w", encoding="utf-8") as f:
                for fp in file_paths:
                    f.write(f"file '{os.path.abspath(fp)}'\n")

            mp4_path = output_path.replace(".mp4", "") + ".mp4"
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                "-movflags", "+faststart",
                mp4_path,
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)

            if os.path.exists(mp4_path):
                return mp4_path
        except Exception as e:
            logger.warning("合并.ts分段失败: %s", e)
        finally:
            if os.path.exists(concat_file):
                try:
                    os.remove(concat_file)
                except Exception:
                    pass

        return None

    def run_test(self, request: SyncTestRequest) -> SyncTestResult:
        """执行双摄短录测试"""
        # 检查摄像头存在
        cam_1 = camera_registry.get(request.cam_1_id)
        cam_2 = camera_registry.get(request.cam_2_id)
        if cam_1 is None:
            raise ValueError(f"摄像头 {request.cam_1_id} 不存在")
        if cam_2 is None:
            raise ValueError(f"摄像头 {request.cam_2_id} 不存在")
        if request.cam_1_id == request.cam_2_id:
            raise ValueError("两个摄像头不能相同")

        # 测试输出目录（使用临时目录，不创建正式会话）
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        test_dir = str(Path("data/sync-recordings/tests") / timestamp)

        stream_configs = {
            request.cam_1_id: (cam_1.stream_url, "cam_1"),
            request.cam_2_id: (cam_2.stream_url, "cam_2"),
        }

        # 使用独立的临时录制器
        test_recorder = SyncRecorder()
        result = test_recorder.start_test(
            stream_configs=stream_configs,
            output_dir=test_dir,
            duration=request.duration,
        )

        return result

    def cancel_session(self, session_id: str) -> SyncRecordingSession:
        """取消双摄同步录制"""
        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS

        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"同步录制会话 {session_id} 不存在")

        if session.status != "recording":
            raise RuntimeError(f"会话 {session_id} 状态为 {session.status}，无法取消")

        self._recorder.stop_recording()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0

        session = session.model_copy(update={
            "status": "canceled",
            "stopped_at": stopped_at,
            "duration_sec": duration,
            "segments": self._segments,
        })

        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()

        logger.info("双摄同步录制已取消: %s", session_id)
        return session

    # ── 查询接口 ──────────────────────────────────────────────────

    def get_session(self, session_id: str) -> SyncRecordingSession | None:
        cached = SYNC_SESSIONS.get(session_id)
        if cached:
            if cached.status == "completed" and not cached.registered_video_ids and cached.segments:
                cached, _, _, _ = self._register_session_videos(cached)
            return cached
        loaded = self._load(session_id)
        if loaded and loaded.status == "completed" and not loaded.registered_video_ids and loaded.segments:
            loaded, _, _, _ = self._register_session_videos(loaded)
        return loaded

    def list_sessions(
        self,
        status: str | None = None,
        field_session_id: str | None = None,
    ) -> list[SyncRecordingSession]:
        result: list[SyncRecordingSession] = []

        if self.sessions_dir.exists():
            for path in sorted(self.sessions_dir.glob("*.json"), reverse=True):
                try:
                    import json
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session = SyncRecordingSession.model_validate(data)
                    if session.status == "completed" and not session.registered_video_ids and session.segments:
                        session, _, _, _ = self._register_session_videos(session)
                    SYNC_SESSIONS[session.session_id] = session
                    if status and session.status != status:
                        continue
                    if field_session_id and session.field_session_id != field_session_id:
                        continue
                    result.append(session)
                except Exception:
                    pass

        return result

    def is_recording(self) -> bool:
        global _ACTIVE_SYNC_SESSION_ID
        return _ACTIVE_SYNC_SESSION_ID is not None

    def get_active_session(self) -> SyncRecordingSession | None:
        global _ACTIVE_SYNC_SESSION_ID
        if _ACTIVE_SYNC_SESSION_ID:
            return self.get_session(_ACTIVE_SYNC_SESSION_ID)
        return None


# 全局单例
sync_recording_service = SyncRecordingService()
