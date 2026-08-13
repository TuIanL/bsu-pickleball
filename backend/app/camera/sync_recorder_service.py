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

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import cv2

from app.camera.camera_registry import camera_registry
from app.camera.models import (
    CameraSlotConfig,
    CameraSlotRole,
    SyncRecordingSession,
    SyncSegment,
    SyncSegmentFile,
    SyncStartRequest,
    SyncStopResponse,
    SyncTestRequest,
    SyncTestResult,
)
from app.services.capture_storage_service import (
    CaptureStorageError,
    capture_storage_is_available,
    capture_storage_plan_from_dir,
    create_capture_storage_plan,
    write_capture_metadata,
)

logger = logging.getLogger(__name__)

# 全局内存缓存：session_id -> SyncRecordingSession
SYNC_SESSIONS: dict[str, SyncRecordingSession] = {}
# 全局活跃同步会话 id
_ACTIVE_SYNC_SESSION_ID: str | None = None
# 活跃摄像头集合（被双摄录制占用的摄像头 id）
_ACTIVE_SYNC_CAMERAS: set[str] = set()
_INPUT_START_RE = re.compile(r"start:\s*([0-9]+(?:\.[0-9]+)?)")
_RECORDING_STOP_TIMEOUT_SEC = 120


def _duration_from_segments(segments: list[SyncSegment], fallback: float) -> float:
    """Use captured media duration, excluding the time spent stopping FFmpeg."""
    totals: dict[str, float] = {}
    for segment in segments:
        for media in segment.files:
            if media.media_duration_sec > 0:
                totals[media.camera_id] = totals.get(media.camera_id, 0.0) + media.media_duration_sec
    return min(totals.values()) if totals else fallback


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════


def check_ffmpeg_available() -> bool:
    """检查系统是否安装了 FFmpeg"""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
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


def _read_input_start_time(log_file: str) -> float | None:
    """Read FFmpeg's RTSP input timestamp before output timestamps are normalized."""
    try:
        text = Path(log_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _INPUT_START_RE.search(text)
    return float(match.group(1)) if match else None


def _extract_first_and_last_frames(video_file: str) -> tuple[str | None, str | None]:
    """输出视频的首帧、中间帧和尾帧，保持返回 (首帧路径, 尾帧路径) 兼容旧调用方。"""
    try:
        base_name = os.path.splitext(video_file)[0]
        first_frame_file = f"{base_name}_first_frame.jpg"
        middle_frame_file = f"{base_name}_middle_frame.jpg"
        last_frame_file = f"{base_name}_last_frame.jpg"

        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            return None, None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            cap.release()
            return None, None

        first_written = False
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, first_frame = cap.read()
        if ret:
            first_written = bool(cv2.imwrite(first_frame_file, first_frame))

        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, middle_frame = cap.read()
        if ret:
            cv2.imwrite(middle_frame_file, middle_frame)

        last_written = False
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
        ret, last_frame = cap.read()
        if ret:
            last_written = bool(cv2.imwrite(last_frame_file, last_frame))

        cap.release()
        return first_frame_file if first_written else None, last_frame_file if last_written else None
    except Exception as e:
        logger.warning("提取视频帧失败 %s: %s", video_file, e)
        return None, None


def _parse_ip_from_url(url: str) -> str:
    """从 RTSP URL 中提取 IP 地址"""
    try:
        return url.split("/")[2].split(":")[0]
    except Exception:
        return "unknown"


def _probe_media_diagnostics(video_file: str) -> tuple[int, float, float]:
    """返回视频包数、媒体时长和由两者推导出的实际帧率。"""
    if not os.path.exists(video_file):
        return 0, 0.0, 0.0
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_packets",
                "-show_entries",
                "stream=nb_read_packets:format=duration",
                "-of",
                "json",
                video_file,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return 0, 0.0, 0.0

        payload = json.loads(result.stdout or "{}")
        packet_count = int((payload.get("streams") or [{}])[0].get("nb_read_packets") or 0)
        duration_sec = float((payload.get("format") or {}).get("duration") or 0.0)
        effective_fps = packet_count / duration_sec if duration_sec > 0 else 0.0
        return packet_count, duration_sec, effective_fps
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        logger.warning("媒体诊断失败 %s: %s", video_file, exc)
        return 0, 0.0, 0.0


def _probe_media_start_time(video_file: str) -> float | None:
    """读取输出文件首个视频帧的时间戳。

    FFmpeg 的 RTSP input start 是网络到达时间，可能在两路之间产生偏移；
    合并同步应优先使用输出媒体自身的帧时间轴。
    """
    if not os.path.exists(video_file):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=best_effort_timestamp_time",
                "-of",
                "csv=p=0",
                video_file,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
        )
        value = (result.stdout or "").strip().splitlines()[0].split(",", 1)[0]
        return float(value)
    except (IndexError, OSError, ValueError, subprocess.SubprocessError):
        return None


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
        self._processes_lock = threading.Lock()
        self.is_recording = False
        self.main_recording_thread: threading.Thread | None = None
        self.segment_index = 1
        self.failure_event = threading.Event()
        self.stop_event = threading.Event()
        self.session_dir: str = ""
        self.recording_threads: list[threading.Thread] = []
        self.fps: int = 30
        self.resolution: str = "1920x1080"
        self._segment_callback: callable | None = None

    # ── 生命周期回调 ────────────────────────────────────────────────
    on_segment_start: callable | None = None
    on_segment_end: callable | None = None
    on_stream_error: callable | None = None
    on_all_complete: callable | None = None

    def _get_stream_output_name(self, url: str, camera_id: str, segment_idx: int) -> str:
        """生成分段输出文件名"""
        _parse_ip_from_url(url)
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

    @staticmethod
    def _sync_encoder() -> str:
        configured = os.environ.get("PICKLEBALL_SYNC_VIDEO_ENCODER")
        if configured:
            return configured
        return "h264_videotoolbox" if platform.system() == "Darwin" else "libx264"

    def _build_record_command(self, url: str, output_file: str, duration: int | None) -> list[str]:
        """构建保留摄像头原始帧序列的双摄录制命令。"""
        cmd = [
            _get_ffmpeg_path(),
            "-y",
            "-rtsp_transport",
            "udp",
            "-timeout",
            "5000000",
            "-fflags",
            "+genpts",
            "-i",
            url,
            "-map",
            "0:v:0",
            "-an",
            # Recording-time CFR conversion duplicates the previous image
            # whenever RTSP delivery is late, permanently encoding visible
            # freezes into the raw TS. Preserve the camera bitstream here
            # alignment and resampling belong in derived outputs.
            "-c:v",
            "copy",
            "-f",
            "mpegts",
        ]
        if duration:
            cmd.extend(["-t", str(duration)])
        cmd.append(output_file)
        return cmd

    def _record_segment_for_stream(
        self,
        url: str,
        camera_id: str,
        role: CameraSlotRole,
        duration: int | None,
        launch_barrier: threading.Barrier | None = None,
    ) -> SyncSegmentFile:
        """录制单个 RTSP 流的一个分段。"""
        output_filename = self._get_stream_output_name(url, camera_id, self.segment_index)
        output_file = os.path.join(self.session_dir, output_filename)
        log_file = f"{output_file}.ffmpeg.log"
        cmd = self._build_record_command(url, output_file, duration)

        logger.debug("[%s] FFmpeg cmd: %s", camera_id, " ".join(cmd))

        started_at = datetime.now(UTC)
        process = None
        error_msg: str | None = None

        try:
            with open(log_file, "wb") as ffmpeg_log:
                if launch_barrier is not None:
                    launch_barrier.wait()
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=ffmpeg_log,
                    stdin=subprocess.PIPE,
                    start_new_session=True,
                )
                with self._processes_lock:
                    self.processes.append(process)

                # 停止请求由控制线程终止进程；此处仍等待其退出，避免读取未落盘文件。
                while process.poll() is None:
                    time.sleep(0.2)

                return_code = process.returncode
                ended_at = datetime.now(UTC)

                is_failure = return_code is not None and return_code != 0 and not self.stop_event.is_set()

                if is_failure:
                    error_msg = f"FFmpeg exit code {return_code}; see {log_file}"
                    logger.error("🚨 [%s] 分段 %d 录制异常: %s", camera_id, self.segment_index, error_msg)
                    self.failure_event.set()
                else:
                    logger.info("✅ [%s] 分段 %d 录制完成", camera_id, self.segment_index)

        except Exception as e:
            logger.exception("🔥 [%s] 录制异常: %s", camera_id, e)
            error_msg = str(e)
            self.failure_event.set()
            ended_at = datetime.now(UTC)
        finally:
            if process is not None:
                with self._processes_lock:
                    if process in self.processes:
                        self.processes.remove(process)

        # 提取首帧尾帧
        if os.path.exists(output_file):
            _extract_first_and_last_frames(output_file)
        file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        if file_size == 0:
            error_msg = error_msg or "输出文件为空"
        packet_count, media_duration_sec, effective_fps = _probe_media_diagnostics(output_file)
        input_start_time = _read_input_start_time(log_file)
        media_start_time_sec = _probe_media_start_time(output_file)
        logger.info(
            "[%s] 分段 %d 诊断: packets=%d duration=%.3fs effective_fps=%.2f target_fps=%d",
            camera_id,
            self.segment_index,
            packet_count,
            media_duration_sec,
            effective_fps,
            self.fps,
        )

        return SyncSegmentFile(
            camera_id=camera_id,
            role=role,
            file_path=output_file,
            file_size=file_size,
            packet_count=packet_count,
            media_duration_sec=media_duration_sec,
            effective_fps=effective_fps,
            ffmpeg_log_path=log_file,
            started_at=started_at,
            ended_at=ended_at or datetime.now(UTC),
            error_message=error_msg,
            input_start_time=input_start_time,
            media_start_time_sec=media_start_time_sec,
        )

    def _terminate_all_processes(self) -> None:
        """同时终止所有 FFmpeg 进程，避免串行等待拉开尾帧。"""
        with self._processes_lock:
            processes = list(self.processes)
        if not processes:
            return
        logger.info("正在终止所有 FFmpeg 进程...")
        running = [process for process in processes if process.poll() is None]

        # Ask every FFmpeg process to finish its MPEG-TS trailer at the same
        # instant. SIGTERM can interrupt each encoder at a different packet,
        # which leaves the raw TS files with visibly different tail lengths.
        for process in running:
            try:
                stdin = getattr(process, "stdin", None)
                if stdin is None:
                    process.terminate()
                    continue
                stdin.write(b"q")
                stdin.flush()
            except (OSError, ValueError):
                pass

        for process in running:
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # A stuck process still must not block the stop request.
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            logger.warning("FFmpeg process %s did not exit after SIGKILL", process.pid)
        with self._processes_lock:
            self.processes = [process for process in self.processes if process.poll() is None]

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

            segment_started = datetime.now(UTC)
            logger.info("--- 🎬 开始同步录制 第 %d 段 (重启次数=%d) ---", self.segment_index, restart_count)

            if self.on_segment_start:
                self.on_segment_start(self.segment_index, restart_count)

            # 为每个流创建录制线程
            results: dict[str, SyncSegmentFile] = {}
            results_lock = threading.Lock()
            launch_barrier = threading.Barrier(len(stream_urls)) if len(stream_urls) > 1 else None

            for index, (camera_id, config) in enumerate(stream_urls.items()):
                stream_url, role = self._normalize_stream_config(camera_id, config, index)

                def _record_with_result(
                    cid: str,
                    surl: str,
                    slot_role: CameraSlotRole,
                    _barrier: threading.Barrier | None = launch_barrier,
                    _lock: threading.Lock = results_lock,
                    _results: dict[str, SyncSegmentFile] = results,
                ) -> None:
                    result = self._record_segment_for_stream(surl, cid, slot_role, duration, _barrier)
                    with _lock:
                        _results[cid] = result

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
                # External volumes can take longer to flush the TS muxer and
                # to run post-capture probing. Do not publish a segment until
                # both recorder threads have fully completed.
                thread.join(timeout=_RECORDING_STOP_TIMEOUT_SEC)

            # 收集分段文件
            segment = SyncSegment(
                segment_index=self.segment_index,
                status="completed",
                files=list(results.values()),
                started_at=segment_started,
                ended_at=datetime.now(UTC),
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
        launch_barrier = threading.Barrier(len(stream_configs)) if len(stream_configs) > 1 else None

        for index, (camera_id, config) in enumerate(stream_configs.items()):
            stream_url, role = self._normalize_stream_config(camera_id, config, index)

            def _record_with_result(cid: str, surl: str, slot_role: CameraSlotRole) -> None:
                result = self._record_segment_for_stream(surl, cid, slot_role, duration, launch_barrier)
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

        cam_1_result = results.get(
            cam_1_id,
            SyncSegmentFile(
                camera_id=cam_1_id,
                role="cam_1",
                file_path="",
            ),
        )
        cam_2_result = results.get(
            cam_2_id,
            SyncSegmentFile(
                camera_id=cam_2_id,
                role="cam_2",
                file_path="",
            ),
        )

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
            test_completed_at=datetime.now(UTC),
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
            self.main_recording_thread.join(timeout=_RECORDING_STOP_TIMEOUT_SEC)

        if self.main_recording_thread and self.main_recording_thread.is_alive():
            logger.error("双摄录制收尾超过 %ss，拒绝提前发布未完成会话", _RECORDING_STOP_TIMEOUT_SEC)
            raise RuntimeError("录制文件仍在外接存储中收尾，请稍后重试停止操作")

        self.segment_index = 1
        logger.info("双摄同步录制已停止")


# ═══════════════════════════════════════════════════════════════════════════
# SyncRecordingService —— 会话生命周期 + 业务逻辑
# ═══════════════════════════════════════════════════════════════════════════


class SyncRecordingService:
    """双摄同步录制服务，管理会话生命周期、持久化、摄像头占用。"""

    @staticmethod
    def _start_showcase_runtime(session: SyncRecordingSession) -> SyncRecordingSession:
        """Start the optional overlay after recording is already healthy."""
        if session.display_mode != "showcase":
            return session
        try:
            from app.services.showcase_runtime import showcase_runtime_manager

            runtime = showcase_runtime_manager.start_for_session(session)
            updated = session.model_copy(update={"showcase_runtime_id": runtime.runtime_id})
            SYNC_SESSIONS[session.session_id] = updated
            return updated
        except Exception as exc:
            logger.warning("展示旁路启动失败，双摄录制继续: %s", exc)
            return session.model_copy(update={"error_message": f"展示旁路不可用: {exc}"})

    @staticmethod
    def _stop_showcase_runtime(session: SyncRecordingSession) -> None:
        if session.display_mode != "showcase":
            return
        try:
            from app.services.showcase_runtime import showcase_runtime_manager

            if not showcase_runtime_manager.stop_for_session(session, timeout=3.0):
                logger.warning("展示旁路停止超时: %s", session.session_id)
        except Exception as exc:
            logger.warning("展示旁路停止失败，继续收尾原始录制: %s", exc)

    def __init__(
        self,
        sync_recorder_factory=None,
        lease_manager=None,
        coordinator=None,
        cleanup_service=None,
    ) -> None:
        self._sync_recorder_factory = sync_recorder_factory
        self._recorder = sync_recorder_factory() if sync_recorder_factory else SyncRecorder()
        self._lease_manager = lease_manager
        self._coordinator = coordinator
        self._cleanup_service = cleanup_service
        self._segments: list[SyncSegment] = []
        self._use_track_recorder = False
        self._active_coordinator = None
        self._storage_monitor_threads: dict[str, threading.Thread] = {}
        self._staging_dirs: dict[str, str] = {}
        # stop_session() and list_sessions() can observe the same completed
        # session concurrently. They must not share a .part.mp4 path.
        self._video_registration_lock = threading.Lock()
        self._merge_state_lock = threading.Lock()

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

    def _output_dir(self, session_id: str, storage_root: str | None = None, capture_take_id: str | None = None) -> Path:
        if storage_root:
            plan = create_capture_storage_plan(capture_take_id or f"take_{session_id}", storage_root)
            return plan.take_dir
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        return Path("data/sync-recordings") / date_str / session_id

    @staticmethod
    def _recording_staging_dir(session_id: str, output_dir: Path) -> Path | None:
        """Record removable-volume captures on the local disk first."""
        if platform.system() == "Darwin" and str(output_dir).startswith("/Volumes/"):
            return Path(tempfile.mkdtemp(prefix=f"pickleball-{session_id}-"))
        return None

    def _materialize_staged_media(self, session: SyncRecordingSession) -> SyncRecordingSession:
        staging = self._staging_dirs.pop(session.session_id, None)
        if not staging:
            return session

        output_dir = Path(session.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        updated_segments: list[SyncSegment] = []
        try:
            for segment in session.segments:
                updated_files: list[SyncSegmentFile] = []
                for item in segment.files:
                    source = Path(item.file_path)
                    if not source.exists():
                        raise RuntimeError(f"本地录制临时文件不存在: {source}")
                    target = output_dir / source.name
                    shutil.copy2(source, target)
                    log_path = item.ffmpeg_log_path
                    if log_path:
                        source_log = Path(log_path)
                        if source_log.exists():
                            target_log = output_dir / source_log.name
                            shutil.copy2(source_log, target_log)
                            log_path = str(target_log)
                    for suffix in ("_first_frame.jpg", "_middle_frame.jpg", "_last_frame.jpg"):
                        source_frame = source.with_name(f"{source.stem}{suffix}")
                        if source_frame.exists():
                            shutil.copy2(source_frame, output_dir / source_frame.name)
                    source_sidecar = Path(f"{source}.pts.jsonl")
                    if source_sidecar.exists():
                        shutil.copy2(source_sidecar, output_dir / source_sidecar.name)
                    updated_files.append(
                        item.model_copy(
                            update={
                                "file_path": str(target),
                                "file_size": target.stat().st_size,
                                "ffmpeg_log_path": log_path,
                            }
                        )
                    )
                updated_segments.append(segment.model_copy(update={"files": updated_files}))
        except Exception:
            # The staging files may be the only copy. Keep them for manual
            # recovery when an external disk disconnects or a copy fails.
            logger.exception("本地临时录制迁移失败，保留恢复目录: %s", staging)
            raise

        shutil.rmtree(staging, ignore_errors=True)
        return session.model_copy(update={"segments": updated_segments})

    def _generate_session_id(self) -> str:
        now = datetime.now(UTC)
        return f"sync_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

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

            with open(path, encoding="utf-8") as f:
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

        if getattr(self, "_use_track_recorder", False) and request.field_session_id:
            s, _ = self._start_with_track_recorder(request)
            return s

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
        display_mode = "standard"

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
                raw_display_mode = getattr(fs, "display_mode", "standard")
                display_mode = getattr(raw_display_mode, "value", raw_display_mode)
                if display_mode not in {"standard", "showcase"}:
                    display_mode = "standard"
                if display_mode == "showcase" and getattr(fs.camera_setup, "value", fs.camera_setup) != "dual":
                    raise ValueError("展示模式只能与双摄方案组合")
            finally:
                db.close()

        # 生成会话
        session_id = self._generate_session_id()
        try:
            plan = create_capture_storage_plan(f"take_{session_id}", request.storage_root)
        except CaptureStorageError as exc:
            raise RuntimeError(str(exc)) from exc
        output_dir = plan.take_dir
        recording_dir = self._recording_staging_dir(session_id, output_dir) or output_dir

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
            started_at=datetime.now(UTC),
            storage_root=str(plan.storage_root),
            session_dir=str(plan.take_dir),
            display_mode=display_mode,
        )

        # 活跃录制唯一性约束：全局最多一个 active CaptureTake
        try:
            from app.database import get_session_factory as _get_sf
            from app.services.capture_take_service import has_active_capture_take

            _check_db = _get_sf()()
            try:
                if has_active_capture_take(_check_db):
                    raise RuntimeError("系统已存在活跃录制，无法同时启动两个录制")
            finally:
                _check_db.close()
        except RuntimeError:
            raise
        except Exception as _exc:
            logger.warning("检查活跃录制失败（跳过约束）: %s", _exc)

        # 标记任务必须先于实际媒体录制创建，避免前端已进入录制态但没有
        # capture_take_id，导致关键事件只能停留在本地临时状态。
        if field_session_id:
            try:
                from app.database import get_session_factory
                from app.services import capture_take_service, capture_track_service

                db = get_session_factory()()
                try:
                    take = capture_take_service.create_capture_take(
                        db,
                        field_session_id=field_session_id,
                        capture_mode="dual",
                        source_session_type="sync_recording",
                        source_session_id=session_id,
                        storage_root=str(plan.storage_root),
                        session_dir=str(plan.take_dir),
                    )
                    capture_track_service.create_track(
                        db,
                        capture_take_id=take.id,
                        camera_id=request.cam_1_id,
                        role="primary",
                        slot="cam_1",
                        analysis_role="default",
                    )
                    capture_track_service.create_track(
                        db,
                        capture_take_id=take.id,
                        camera_id=request.cam_2_id,
                        role="secondary",
                        slot="cam_2",
                        analysis_role="supplementary",
                    )
                    db.commit()
                    session = session.model_copy(update={"capture_take_id": take.id})
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()
            except Exception as exc:
                import shutil

                shutil.rmtree(output_dir, ignore_errors=True)
                raise RuntimeError(f"创建双摄录制标记任务失败，未启动录制: {exc}") from exc

        # 记录活跃状态
        _ACTIVE_SYNC_SESSION_ID = session_id
        _ACTIVE_SYNC_CAMERAS = {request.cam_1_id, request.cam_2_id}

        # 重置分段累积 + 绑定录制器回调
        self._segments = []

        def on_segment_start(idx: int, restarts: int) -> None:
            logger.info("===== 分段 %d 开始 (重启 %d 次) =====", idx, restarts)

        def on_segment_end(segment: SyncSegment) -> None:
            self._segments.append(segment)
            # The recorder thread can finish just after stop_session() has
            # published a terminal session. Never persist the start-time
            # snapshot here, or it can resurrect a completed session as
            # "recording" (especially on slow external volumes).
            current = SYNC_SESSIONS.get(session_id)
            if current is None or current.status != "recording":
                return
            updated = current.model_copy(
                update={
                    "segments": list(self._segments),
                    "total_restarts": sum(s.restart_count for s in self._segments),
                }
            )
            SYNC_SESSIONS[session_id] = updated
            self._persist(updated)

        def on_stream_error(idx: int, restarts: int) -> None:
            logger.warning("⚠️ 分段 %d 失败，同步重启中 (重启计数=%d)", idx, restarts)

        def on_all_complete() -> None:
            # 录制器退出后完成会话
            s = SYNC_SESSIONS.get(session_id)
            if s and s.status == "recording":
                self._complete_session(session_id)

        self._recorder = self._sync_recorder_factory() if self._sync_recorder_factory else SyncRecorder()
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
            output_dir=str(recording_dir),
            duration=None,
            fps=request.fps,
            resolution=request.resolution,
        )

        SYNC_SESSIONS[session_id] = session
        if recording_dir != output_dir:
            self._staging_dirs[session_id] = str(recording_dir)
        self._persist(session)
        write_capture_metadata(
            plan,
            manifest={
                "schema_version": "capture_manifest.v1",
                "capture_take_id": session.capture_take_id or f"take_{session_id}",
                "source_session_id": session_id,
                "capture_mode": "dual",
                "status": "recording",
                "storage_root": str(plan.storage_root),
                "session_dir": str(plan.take_dir),
            },
            session=session.model_dump(mode="json"),
        )
        self._start_storage_monitor(session_id)

        session = self._start_showcase_runtime(session)
        self._persist(session)

        logger.info("双摄同步录制会话已开始: %s", session_id)
        return session

    def _start_storage_monitor(self, session_id: str) -> None:
        def monitor() -> None:
            while True:
                time.sleep(1)
                session = SYNC_SESSIONS.get(session_id)
                if not session or session.status != "recording":
                    return
                if not capture_storage_is_available(session.session_dir or session.output_dir):
                    self._handle_storage_failure(session_id, "录制存储位置不可访问，双摄录制已立即停止")
                    return

        thread = threading.Thread(target=monitor, daemon=True)
        self._storage_monitor_threads[session_id] = thread
        thread.start()

    def _handle_storage_failure(self, session_id: str, message: str) -> None:
        session = SYNC_SESSIONS.get(session_id)
        if session is None or session.status != "recording":
            return
        try:
            if self._active_coordinator is not None:
                self._active_coordinator.stop_tracks()
            else:
                self._recorder.stop_recording()
        except Exception as exc:
            logger.warning("存储故障停止双摄录制失败: %s", exc)
        self._stop_showcase_runtime(session)
        failed = session.model_copy(
            update={
                "status": "failed",
                "storage_status": "failed",
                "stopped_at": datetime.now(UTC),
                "duration_sec": (datetime.now(UTC) - session.started_at).total_seconds() if session.started_at else 0,
                "error_message": message,
            }
        )
        SYNC_SESSIONS[session_id] = failed
        self._persist(failed)
        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS
        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()
        self._finalize_capture_take(failed, "failed")

    def stop_session(self, session_id: str) -> SyncStopResponse:
        """停止双摄同步录制"""
        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS

        if self._active_coordinator is not None:
            coord = self._active_coordinator
            self._active_coordinator = None
            s = self._stop_with_track_recorder(session_id, coord)
            return SyncStopResponse(session=s, analysis_available=False)

        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"同步录制会话 {session_id} 不存在")

        if session.status != "recording":
            raise RuntimeError(f"会话 {session_id} 状态为 {session.status}，无法停止")

        # 停止录制器
        self._recorder.stop_recording()
        self._stop_showcase_runtime(session)
        stopped_at = datetime.now(UTC)
        wall_duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0
        duration = _duration_from_segments(self._segments, wall_duration)

        # 更新会话
        session = session.model_copy(
            update={
                "status": "completed",
                "stopped_at": stopped_at,
                "duration_sec": duration,
                "segments": self._segments,
                "total_restarts": sum(s.restart_count for s in self._segments),
            }
        )
        try:
            session = self._materialize_staged_media(session)
        except Exception as exc:
            logger.exception("移动存储归档失败: %s", exc)
            session = session.model_copy(
                update={
                    "status": "failed",
                    "storage_status": "failed",
                    "error_message": f"录制已完成但无法写入目标存储: {exc}",
                }
            )

        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        # 清除活跃状态
        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()

        # 先把采集生命周期标记为完成，让侧边栏和活跃录制探测立即停止；
        # 视频封装属于停止后的媒体后处理，不应继续占用“录制中”状态。
        self._finalize_capture_take(session, session.status)

        session = session.model_copy(
            update={
                "merge_status": "pending",
                "merge_error": None,
                "merge_started_at": None,
                "merge_completed_at": None,
                "merge_results": {},
                "default_analysis_video_id": None,
                "registered_video_ids": {},
            }
        )
        default_analysis_video_id = None
        analysis_available = False
        analysis_blocked_reason = "视频尚未合并，请在任务管理中手动合并"

        # MP4 注册完成后补写训练标注清单：标签始终以 CaptureTake 时间轴为准，
        # 同时记录每个机位的原始 TS 与派生视频 ID，便于后续按帧复现。
        if session.capture_take_id:
            try:
                from app.database import get_session_factory
                from app.services.capture_archive_service import snapshot_capture_timeline

                db = get_session_factory()()
                try:
                    sources = []
                    alignment = self._compute_sync_alignment(session)
                    for role in ("cam_1", "cam_2"):
                        slot = session.camera_slots.get(role)
                        if not slot:
                            continue
                        source_paths = [
                            item.file_path
                            for segment in session.segments
                            for item in segment.files
                            if item.camera_id == slot.camera_id and item.file_path
                        ]
                        timing_sidecars = [
                            f"{source_path}.pts.jsonl"
                            for source_path in source_paths
                            if os.path.exists(f"{source_path}.pts.jsonl")
                        ]
                        sources.append(
                            {
                                "slot": role,
                                "camera_id": slot.camera_id,
                                "video_id": session.registered_video_ids.get(role),
                                "source_media_paths": source_paths,
                                "timing_sidecar_paths": timing_sidecars,
                                "pts_scope": "per_file_local",
                                "pts_shared_epoch": False,
                                "derived_media_path": str(Path(session.output_dir) / f"{slot.camera_id}_merged.mp4"),
                                "raw_source_offset_ms": round(alignment.get(role, (0.0, None))[0] * 1000, 3),
                                "aligned_media_trim_start_ms": round(alignment.get(role, (0.0, None))[0] * 1000, 3),
                                # The current TS PTS spike proved local PTS is not
                                # a shared epoch; do not advertise a cross-camera
                                # drift estimate until explicit anchors are fitted.
                                "reference_camera": "174",
                                "drift_ppm": None,
                                "sync_quality": "unknown",
                                "mapping_artifact": None,
                                "sync_quality_reason": "cross-camera calibration anchors unavailable",
                            }
                        )
                    snapshot_capture_timeline(
                        db,
                        session.capture_take_id,
                        fps=session.fps,
                        video_sources=sources,
                    )
                finally:
                    db.close()
            except Exception as exc:
                logger.warning("补写训练标注清单失败: %s", exc)

        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        if session.session_dir:
            try:
                write_capture_metadata(
                    capture_storage_plan_from_dir(session.session_dir),
                    manifest={
                        "schema_version": "capture_manifest.v1",
                        "capture_take_id": session.capture_take_id,
                        "source_session_id": session.session_id,
                        "capture_mode": "dual",
                        "status": session.status,
                        "storage_root": session.storage_root,
                        "session_dir": session.session_dir,
                        "associated_video_paths": session.associated_video_paths,
                    },
                    session=session.model_dump(mode="json"),
                )
            except OSError as exc:
                logger.warning("更新双摄录制 manifest 失败: %s", exc)

        logger.info(
            "双摄同步录制已停止: %s (duration=%.1fs, analysis_available=%s)", session_id, duration, analysis_available
        )

        return SyncStopResponse(
            session=session,
            default_analysis_video_id=default_analysis_video_id,
            analysis_available=analysis_available,
            analysis_blocked_reason=analysis_blocked_reason,
        )

    def _finalize_capture_take(self, session, terminal_status: str) -> None:
        take_id = getattr(session, "capture_take_id", None)
        if not take_id:
            return
        try:
            from app.database import get_session_factory
            from app.services import capture_segment_service, capture_take_service

            db = get_session_factory()()
            try:
                duration_ms = int((session.duration_sec or 0) * 1000)
                ended = session.stopped_at or datetime.now(UTC)
                capture_take_service.finalize_capture_take(
                    db,
                    take_id,
                    terminal_status,
                    ended_at=ended,
                    duration_ms=duration_ms,
                )
                if duration_ms > 0:
                    capture_segment_service.close_all_open_for_take(db, take_id, duration_ms)
                from app.services.capture_archive_service import snapshot_capture_timeline

                snapshot_capture_timeline(db, take_id)
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("finalize 双摄 CaptureTake %s 失败: %s", take_id, exc)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("finalize 双摄 CaptureTake 连接失败: %s", exc)

    def _complete_session(self, session_id: str) -> None:
        """录制器自动退出后完成会话"""
        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS

        session = SYNC_SESSIONS.get(session_id)
        if not session or session.status != "recording":
            return

        stopped_at = datetime.now(UTC)
        wall_duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0
        duration = _duration_from_segments(self._segments, wall_duration)

        session = session.model_copy(
            update={
                "status": "failed",
                "stopped_at": stopped_at,
                "duration_sec": duration,
                "segments": self._segments,
                "error_message": "录制器异常退出",
                "total_restarts": sum(s.restart_count for s in self._segments),
            }
        )

        SYNC_SESSIONS[session_id] = session
        self._persist(session)
        self._stop_showcase_runtime(session)
        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()
        logger.warning("双摄同步录制会话自动结束(异常): %s", session_id)

        self._finalize_capture_take(session, "failed")

    def _register_session_videos(
        self,
        session: SyncRecordingSession,
    ) -> tuple[SyncRecordingSession, str | None, bool, str | None]:
        with self._video_registration_lock:
            return self._register_session_videos_unlocked(session)

    def request_merge(self, session_id: str) -> SyncRecordingSession:
        """提交一个已停止双摄任务的两路视频合并。"""
        with self._merge_state_lock:
            session = self._load(session_id) or SYNC_SESSIONS.get(session_id)
            if session is None:
                raise ValueError(f"同步录制会话 {session_id} 不存在")
            if session.status == "recording":
                raise RuntimeError("录制进行中，无法合并视频")
            if session.status == "canceled":
                raise RuntimeError("已取消的录制不能合并")
            if session.merge_status == "running":
                raise RuntimeError("该任务正在合并中")
            if (
                session.merge_status == "completed"
                and len(session.registered_video_ids) >= len(session.camera_slots)
                and self._registered_video_ids_are_available(session)
            ):
                return session
            if not self._session_has_ts(session):
                raise RuntimeError("没有找到可合并的 TS 分段")

            session = session.model_copy(
                update={
                    "merge_status": "running",
                    "merge_error": None,
                    "merge_started_at": datetime.now(UTC),
                    "merge_completed_at": None,
                }
            )
            SYNC_SESSIONS[session_id] = session
            self._persist(session)
            threading.Thread(
                target=self._merge_session_videos_background,
                args=(session_id,),
                name=f"merge-dual-{session_id}",
                daemon=True,
            ).start()
            return session

    def _session_has_ts(self, session: SyncRecordingSession) -> bool:
        if any(
            f.file_path and f.file_size > 0 and os.path.exists(f.file_path)
            for segment in session.segments
            for f in segment.files
        ):
            return True
        if not session.capture_take_id:
            return False
        try:
            from app.database import get_session_factory
            from app.models.media_fragment import MediaFragment

            db = get_session_factory()()
            try:
                return (
                    db.query(MediaFragment)
                    .filter(
                        MediaFragment.capture_take_id == session.capture_take_id,
                        MediaFragment.file_size > 0,
                    )
                    .count()
                    > 0
                )
            finally:
                db.close()
        except Exception:
            return False

    def _merge_session_videos_background(self, session_id: str) -> None:
        try:
            session = self._load(session_id) or SYNC_SESSIONS.get(session_id)
            if session is None:
                return
            track_results = self._finalize_capture_tracks(session)
            track_results_usable = bool(track_results) and all(
                self._video_id_is_available(track_results.get(role, {}).get("video_id"))
                for role in session.camera_slots
            )
            if track_results is None or not track_results_usable:
                session, _, _, _ = self._register_session_videos(session)
            else:
                registered = dict(session.registered_video_ids or {})
                results = dict(session.merge_results or {})
                for role, result in track_results.items():
                    results[role] = result
                    if result.get("video_id"):
                        registered[role] = result["video_id"]
                session = session.model_copy(
                    update={
                        "registered_video_ids": registered,
                        "default_analysis_video_id": registered.get("cam_1"),
                        "merge_results": results,
                    }
                )

            missing = [role for role in session.camera_slots if role not in session.registered_video_ids]
            now = datetime.now(UTC)
            if missing:
                session = session.model_copy(
                    update={
                        "merge_status": "failed",
                        "merge_error": f"机位 {', '.join(missing)} 合并失败，可重试",
                        "merge_completed_at": now,
                    }
                )
            else:
                session = session.model_copy(
                    update={
                        "merge_status": "completed",
                        "merge_error": None,
                        "merge_completed_at": now,
                        "default_analysis_video_id": session.registered_video_ids.get("cam_1"),
                    }
                )
            SYNC_SESSIONS[session_id] = session
            self._persist(session)
            self._persist_capture_manifest(session)
        except Exception as exc:
            logger.exception("双摄任务 %s 合并失败", session_id)
            session = self._load(session_id) or SYNC_SESSIONS.get(session_id)
            if session is not None:
                failed = session.model_copy(
                    update={
                        "merge_status": "failed",
                        "merge_error": str(exc),
                        "merge_completed_at": datetime.now(UTC),
                    }
                )
                SYNC_SESSIONS[session_id] = failed
                self._persist(failed)

    def _finalize_capture_tracks(self, session: SyncRecordingSession) -> dict[str, dict] | None:
        """Finalize coordinator-backed fragments; legacy sessions use the old path."""
        take_id = session.capture_take_id
        if not take_id:
            return None
        from app.camera.capture_finalizer import CaptureFinalizer
        from app.database import get_session_factory
        from app.models.capture_track import CaptureTrack
        from app.models.media_fragment import FragmentStatus, MediaFragment

        db = get_session_factory()()
        try:
            tracks = db.query(CaptureTrack).filter(CaptureTrack.capture_take_id == take_id).all()
            fragments = db.query(MediaFragment).filter(MediaFragment.capture_take_id == take_id).all()
            track_rows = [(track.id, track.slot.value) for track in tracks]
            fragment_rows = [
                {
                    "track_id": fragment.capture_track_id,
                    "file_path": fragment.file_path,
                    "fragment_index": fragment.fragment_index,
                    "take_start_offset_ms": fragment.take_start_offset_ms,
                    "status": fragment.status.value,
                }
                for fragment in fragments
            ]
        finally:
            db.close()
        if not track_rows or not fragment_rows:
            return None
        finalizer = CaptureFinalizer()
        results: dict[str, dict] = {}
        for track_id, slot in sorted(track_rows, key=lambda item: item[1]):
            infos = [
                {
                    "file_path": fragment["file_path"],
                    "fragment_index": fragment["fragment_index"],
                    "take_start_offset_ms": fragment["take_start_offset_ms"],
                    "status": fragment["status"],
                }
                for fragment in fragment_rows
                if fragment["track_id"] == track_id
                and fragment["status"] in (FragmentStatus.completed.value, FragmentStatus.interrupted.value)
            ]
            result = finalizer.finalize_track(track_id, infos)
            result_payload = {
                "status": result.status,
                "video_id": result.video_id,
                "output_path": result.output_path,
                "fragment_count": result.fragment_count,
                "error": "; ".join(result.warnings) if result.warnings else None,
            }
            if result.output_path:
                result_payload.update(self._materialize_registered_video_timing(result.output_path))
            results[slot] = result_payload
        self._persist_capture_track_timing(session.capture_take_id, results)
        return results

    @staticmethod
    def _materialize_registered_video_timing(media_path: str | os.PathLike[str]) -> dict[str, object]:
        """Materialize/validate PTS for the final registered media.

        Timing is an analysis capability attached to the video, not a
        prerequisite for preserving a completed capture.  Callers therefore
        receive a structured unavailable result instead of an exception.
        """
        from app.services.dual_camera_sync import (
            summarize_frame_timing_sidecar,
            write_frame_timing_sidecar,
        )

        media = Path(media_path)
        sidecar = Path(f"{media}.pts.jsonl")
        try:
            if sidecar.exists():
                return summarize_frame_timing_sidecar(sidecar, media_path=media)
            return write_frame_timing_sidecar(media, sidecar)
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成 registered video PTS sidecar 失败 %s: %s", media, exc)
            return {
                "status": "unavailable",
                "timing_authority": "missing",
                "provenance": "registered_video_pts_materialization",
                "media_path": str(media),
                "sidecar_path": str(sidecar),
                "frame_count": 0,
                "fps": None,
                "first_pts_seconds": None,
                "last_pts_seconds": None,
                "timing_failure_reason": str(exc),
            }

    @staticmethod
    def _persist_capture_track_timing(
        capture_take_id: str | None,
        timing_results: dict[str, dict[str, object]],
    ) -> None:
        """Mirror sidecar readiness onto CaptureTrack without affecting media state."""
        if not capture_take_id or not timing_results:
            return
        try:
            from app.database import get_session_factory
            from app.models.capture_track import CaptureTrack

            db = get_session_factory()()
            try:
                tracks = db.query(CaptureTrack).filter(CaptureTrack.capture_take_id == capture_take_id).all()
                for track in tracks:
                    timing = timing_results.get(track.slot.value)
                    if not timing:
                        continue
                    track.timing_authority = str(timing.get("timing_authority", "missing"))
                    track.timing_sidecar_path = (
                        str(timing["sidecar_path"]) if timing.get("sidecar_path") else None
                    )
                    track.timing_failure_reason = (
                        str(timing["timing_failure_reason"])
                        if timing.get("timing_failure_reason")
                        else None
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("回写 CaptureTrack timing authority 失败: %s", exc)

    def _persist_capture_manifest(self, session: SyncRecordingSession) -> None:
        if not session.session_dir:
            return
        try:
            write_capture_metadata(
                capture_storage_plan_from_dir(session.session_dir),
                manifest={
                    "schema_version": "capture_manifest.v1",
                    "capture_take_id": session.capture_take_id,
                    "source_session_id": session.session_id,
                    "capture_mode": "dual",
                    "status": session.status,
                    "merge_status": session.merge_status,
                    "storage_root": session.storage_root,
                    "session_dir": session.session_dir,
                    "associated_video_paths": session.associated_video_paths,
                },
                session=session.model_dump(mode="json"),
            )
        except OSError as exc:
            logger.warning("更新双摄录制 manifest 失败: %s", exc)

    def _register_session_videos_unlocked(
        self,
        session: SyncRecordingSession,
    ) -> tuple[SyncRecordingSession, str | None, bool, str | None]:
        """把已完成双摄会话的两路分段登记为可 HTTP 播放的视频。"""
        analysis_available = False
        analysis_blocked_reason: str | None = None
        default_analysis_video_id = session.default_analysis_video_id
        registered_video_ids: dict[CameraSlotRole, str] = dict(session.registered_video_ids or {})
        video_availability = dict(session.video_availability or {})
        associated_video_paths: list[str] = []
        merge_results = dict(session.merge_results or {})
        alignment = self._compute_sync_alignment(session)

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

            existing_video_id = registered_video_ids.get(role)
            if self._video_id_is_available(existing_video_id):
                try:
                    from app.services.video_service import video_service

                    registered_media = video_service.get_available_video(existing_video_id)
                    registered_path = getattr(registered_media, "path", None)
                    if registered_path:
                        merge_results[role] = {
                            **dict(merge_results.get(role) or {}),
                            "video_id": existing_video_id,
                            "output_path": str(registered_path),
                            **self._materialize_registered_video_timing(registered_path),
                        }
                except Exception as exc:  # noqa: BLE001
                    logger.warning("补写已登记视频 timing sidecar 失败 %s/%s: %s", session.session_id, role, exc)
                video_availability[role] = "available"
                if role == "cam_1":
                    default_analysis_video_id = existing_video_id
                    analysis_available = True
                continue

            # 会话 JSON 可能比 VideoService 元数据更持久。优先从已经合并的
            # MP4 重建元数据，避免重启后重复执行长时间的 TS 合并。
            merged_path = self._existing_merged_media_path(session, role, slot)
            if merged_path is not None:
                try:
                    restored_id = self._register_media_path(merged_path, existing_video_id)
                except (OSError, ValueError) as exc:
                    logger.warning("恢复双摄视频失败 %s/%s: %s", session.session_id, role, exc)
                else:
                    registered_video_ids[role] = restored_id
                    merge_results[role] = {
                        **dict(merge_results.get(role) or {}),
                        "video_id": restored_id,
                        "output_path": str(merged_path),
                        **self._materialize_registered_video_timing(merged_path),
                    }
                    video_availability[role] = "available"
                    if role == "cam_1":
                        default_analysis_video_id = restored_id
                        analysis_available = True
                    continue

            if role == "cam_1":
                analysis_available = False

            if files:
                trim_start, target_frames = alignment.get(role, (0.0, None))
                video_id = self._register_recorded_slot_video(
                    session,
                    files,
                    slot,
                    trim_start=trim_start,
                    target_frames=target_frames,
                    preferred_video_id=existing_video_id,
                )
                if video_id:
                    registered_video_ids[role] = video_id
                    merge_results.setdefault(role, {})["video_id"] = video_id
                    video_availability[role] = "available"
                    if role == "cam_1":
                        default_analysis_video_id = video_id
                        analysis_available = True
                elif role == "cam_1":
                    video_availability[role] = "unavailable"
                    analysis_blocked_reason = "默认分析视频注册失败，请检查文件完整性"
                else:
                    video_availability[role] = "unavailable"
            else:
                video_availability[role] = "pending" if existing_video_id is None else "unavailable"
                if role == "cam_1":
                    analysis_blocked_reason = "底线机位 A 无有效分段文件"

        session = session.model_copy(
            update={
                "default_analysis_video_id": default_analysis_video_id,
                "registered_video_ids": registered_video_ids,
                "video_availability": video_availability,
                "associated_video_paths": associated_video_paths,
                "merge_results": merge_results,
            }
        )
        # 将派生视频 ID 回写到 CaptureTrack，保证数据库、会话快照和训练清单一致。
        if session.capture_take_id and registered_video_ids:
            try:
                from app.database import get_session_factory
                from app.models.capture_track import CaptureTrack

                db = get_session_factory()()
                try:
                    tracks = (
                        db.query(CaptureTrack).filter(CaptureTrack.capture_take_id == session.capture_take_id).all()
                    )
                    for track in tracks:
                        video_id = registered_video_ids.get(track.slot.value)
                        if video_id:
                            track.video_id = video_id
                        timing = merge_results.get(track.slot.value) or {}
                        if timing:
                            track.timing_authority = str(timing.get("timing_authority", "missing"))
                            track.timing_sidecar_path = (
                                str(timing["sidecar_path"]) if timing.get("sidecar_path") else None
                            )
                            track.timing_failure_reason = (
                                str(timing["timing_failure_reason"])
                                if timing.get("timing_failure_reason")
                                else None
                            )
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()
            except Exception as exc:
                logger.warning("回写 CaptureTrack 视频 ID 失败: %s", exc)
        SYNC_SESSIONS[session.session_id] = session
        self._persist(session)
        return session, default_analysis_video_id, analysis_available, analysis_blocked_reason

    @staticmethod
    def _compute_sync_alignment(session: SyncRecordingSession) -> dict[str, tuple[float, int | None]]:
        """Find the common overlap across all synchronized segments.

        For each segment pair (cam_1 + cam_2), compute the input-time
        overlap independently and sum the resulting frame counts.  The
        first segment determines *trim_start*; subsequent segments add to
        *target_frames* but do not affect the start offset.

        Gap/overlap between segments is diagnosed via logging so that
        callers (annotation manifest, merge pipeline) can decide whether
        the recording is suitable for frame-accurate alignment.
        """
        observations: dict[int, dict[str, tuple[float, float]]] = {}
        for segment in sorted(session.segments, key=lambda s: s.segment_index):
            seg_obs: dict[str, tuple[float, float]] = {}
            for role in ("cam_1", "cam_2"):
                slot = session.camera_slots.get(role)
                if not slot:
                    continue
                item = next((f for f in segment.files if f.camera_id == slot.camera_id), None)
                if item and item.input_start_time is not None and item.media_duration_sec > 0:
                    alignment_start = item.input_start_time
                    if alignment_start is None:
                        alignment_start = item.media_start_time_sec
                    if alignment_start is not None:
                        seg_obs[role] = (alignment_start, item.media_duration_sec)
            if len(seg_obs) >= 2:
                observations[segment.segment_index] = seg_obs

        if not observations:
            return {}

        fps = max(session.fps, 1)
        total_frames = 0
        first_start: dict[str, float] = {}
        diagnostics: dict[int, dict[str, object]] = {}

        sorted_indices = sorted(observations.keys())
        for i, seg_idx in enumerate(sorted_indices):
            seg_obs = observations[seg_idx]
            common_start = max(start for start, _ in seg_obs.values())
            common_end = min(start + duration for start, duration in seg_obs.values())
            common_duration = common_end - common_start

            if common_duration <= 0:
                logger.warning("分段 %d 无共同时间区间: %s", seg_idx, seg_obs)
                continue

            segment_frames = max(1, int(common_duration * fps))
            total_frames += segment_frames

            for role, (start, _) in seg_obs.items():
                if role not in first_start:
                    first_start[role] = start

            # Gap/overlap diagnostic between this segment and the previous one
            if i > 0:
                prev_obs = observations[sorted_indices[i - 1]]
                gap_info: dict[str, object] = {}
                for role in ("cam_1", "cam_2"):
                    if role in prev_obs and role in seg_obs:
                        prev_end = prev_obs[role][0] + prev_obs[role][1]
                        curr_start = seg_obs[role][0]
                        gap = curr_start - prev_end
                        label = "gap" if gap > 0.001 else ("overlap" if gap < -0.001 else "contiguous")
                        gap_info[role] = {
                            "gap_seconds": round(gap, 6),
                            "label": label,
                        }
                if gap_info:
                    diagnostics[seg_idx] = gap_info

        if not first_start:
            return {}

        if diagnostics:
            logger.info(
                "双摄分段间隙诊断: %s segments, %s gaps/overlaps detected",
                len(observations),
                len(diagnostics),
            )
            for seg_idx, info in diagnostics.items():
                logger.info("  分段 %d: %s", seg_idx, info)

        return {
            role: (
                round(max(0.0, common_first_start - start) * fps) / fps,
                total_frames,
            )
            for role, start in first_start.items()
            for common_first_start in [max(first_start.values())]
        }

    @staticmethod
    def _align_ts_tail(file_paths: list[str], target_frames: int) -> None:
        """Deprecated guard: raw TS files must never be overwritten."""
        logger.warning(
            "忽略原始 TS 尾帧裁剪请求（保留源文件）；请在派生 MP4 上执行裁剪: files=%s frames=%s",
            file_paths,
            target_frames,
        )

    def _register_recorded_slot_video(
        self,
        session: SyncRecordingSession,
        file_paths: list[str],
        slot: CameraSlotConfig,
        *,
        trim_start: float = 0.0,
        target_frames: int | None = None,
        preferred_video_id: str | None = None,
    ) -> str | None:
        """登记一个机位的视频到 VideoService"""
        from app.camera.capture_finalizer import set_merge_status

        take_id = getattr(session, "capture_take_id", None)

        try:
            from app.services.video_service import SUPPORTED_VIDEO_SUFFIXES, video_service

            if take_id:
                set_merge_status(take_id, "merging", f"合并 {slot.camera_id}…")

            # 转码/合并 .ts 分段为单个 MP4
            merged_path = self._merge_segments(
                file_paths,
                os.path.join(session.output_dir, f"{slot.camera_id}_merged.mp4"),
                trim_start=trim_start,
                target_frames=target_frames,
                fps=session.fps,
            )

            file_path = Path(merged_path) if merged_path else Path(file_paths[0])
            if not file_path.exists():
                if take_id:
                    set_merge_status(take_id, "failed", f"{slot.camera_id} 合并失败：输出文件不存在")
                return None

            _extract_first_and_last_frames(str(file_path))

            file_size = file_path.stat().st_size
            suffix = file_path.suffix.lower()
            if suffix not in SUPPORTED_VIDEO_SUFFIXES:
                suffix = ".mp4"

            video_id = video_service.register_recording(
                file_path=file_path,
                original_filename=file_path.name,
                file_size=file_size,
                video_id=preferred_video_id,
            )
            session.merge_results[slot.role] = {
                **dict(session.merge_results.get(slot.role) or {}),
                "video_id": video_id,
                "output_path": str(file_path),
                **self._materialize_registered_video_timing(file_path),
            }

            if take_id:
                is_merged = merged_path is not None and merged_path.endswith(".mp4")
                if is_merged:
                    set_merge_status(take_id, "completed", f"{slot.camera_id} 合并完成")
                else:
                    set_merge_status(take_id, "failed", f"{slot.camera_id} 合并失败，已降级为 .ts")
            return video_id
        except Exception as exc:
            logger.error("登记主机位视频失败: %s", exc)
            if take_id:
                set_merge_status(take_id, "failed", f"{slot.camera_id} 异常: {exc}")
            return None

    @staticmethod
    def _video_id_is_available(video_id: str | None) -> bool:
        if not video_id:
            return False
        from app.services.video_service import video_service

        return video_service.get_available_video(video_id) is not None

    @staticmethod
    def _existing_merged_media_path(
        session: SyncRecordingSession,
        role: CameraSlotRole,
        slot: CameraSlotConfig,
    ) -> Path | None:
        """Find an already-created MP4 without rerunning the expensive merge."""
        candidates: list[Path] = []
        result = (session.merge_results or {}).get(role)
        if result and result.get("output_path"):
            candidates.append(Path(str(result["output_path"])))
        for directory in (session.output_dir, session.session_dir):
            if directory:
                candidates.append(Path(directory) / f"{slot.camera_id}_merged.mp4")

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return candidate
            except OSError:
                continue
        return None

    @staticmethod
    def _register_media_path(path: Path, preferred_video_id: str | None = None) -> str:
        from app.services.video_service import video_service

        return video_service.register_recording(
            file_path=path,
            original_filename=path.name,
            file_size=path.stat().st_size,
            video_id=preferred_video_id,
        )

    def _repair_registered_video_metadata(self, session: SyncRecordingSession) -> SyncRecordingSession:
        """Rehydrate stale metadata without destroying historical video references.

        A recording ID is durable session history, not a cache entry.  In particular,
        an unavailable external volume must not cause a read-only list/get call to
        remove that ID from the session.  We only refresh the derived availability
        state and restore metadata when the media becomes visible again.
        """
        if session.status == "recording" or not session.camera_slots:
            return session

        with self._video_registration_lock:
            registered = dict(session.registered_video_ids or {})
            availability = dict(session.video_availability or {})
            changed = False
            for role in ("cam_1", "cam_2"):
                slot = session.camera_slots.get(role)
                if not slot:
                    continue
                video_id = registered.get(role)
                if self._video_id_is_available(video_id):
                    if availability.get(role) != "available":
                        availability[role] = "available"
                        changed = True
                    continue

                merged_path = self._existing_merged_media_path(session, role, slot)
                if merged_path is not None:
                    try:
                        restored_id = self._register_media_path(merged_path, video_id)
                    except (OSError, ValueError) as exc:
                        logger.warning("恢复双摄视频元数据失败 %s/%s: %s", session.session_id, role, exc)
                    else:
                        registered[role] = restored_id
                        availability[role] = "available"
                        changed = True
                        continue

                next_status = "unavailable" if video_id else "pending"
                if availability.get(role) != next_status:
                    availability[role] = next_status
                    changed = True

            if not changed:
                return session

            updated = session.model_copy(
                update={
                    "registered_video_ids": registered,
                    "default_analysis_video_id": registered.get("cam_1"),
                    "video_availability": availability,
                }
            )
            SYNC_SESSIONS[session.session_id] = updated
            self._persist(updated)
            return updated

    def _registered_video_ids_are_available(self, session: SyncRecordingSession) -> bool:
        return all(
            self._video_id_is_available(session.registered_video_ids.get(role))
            for role in session.camera_slots
        )

    def _find_keyframe_after(self, file_path: str, time_sec: float) -> float:
        """查找指定时间之后最近的关键帧时间位置"""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v",
                    "-read_intervals",
                    f"{time_sec}%+#1",
                    "-show_entries",
                    "frame=key_frame,pts_time",
                    "-of",
                    "csv=p=0",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            for line in (result.stdout or "").strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(",")
                if len(parts) >= 2 and parts[0].strip() == "1" and parts[1].strip():
                    return float(parts[1].strip())
            return time_sec
        except Exception:
            return time_sec

    def _find_keyframe_before(self, file_path: str, time_sec: float) -> float:
        """查找指定时间之前最近的关键帧时间位置"""
        if time_sec <= 0:
            return 0.0
        try:
            # 向前找 5 秒范围内的关键帧
            start = max(0.0, time_sec - 5.0)
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v",
                    "-read_intervals",
                    f"{start}%{time_sec + 0.1}",
                    "-show_entries",
                    "frame=key_frame,pts_time",
                    "-of",
                    "csv=p=0",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            last_kf = 0.0
            for line in (result.stdout or "").strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(",")
                if (
                    len(parts) >= 2
                    and parts[0].strip() == "1"
                    and parts[1].strip()
                    and float(parts[1].strip()) <= time_sec
                ):
                    last_kf = max(last_kf, float(parts[1].strip()))
            return last_kf
        except Exception:
            return 0.0

    def _merge_segments(
        self,
        file_paths: list[str],
        output_path: str,
        *,
        trim_start: float = 0.0,
        target_frames: int | None = None,
        fps: int = 60,
    ) -> str | None:
        """合并 .ts 分段为单个 MP4 文件

        精度策略：
        - 无 trim 需求时：-c copy 秒级
        - 有 trim 需求时：从共同起点重编码指定帧数，保证双摄时间范围一致
        """
        if not file_paths:
            return None

        mp4_path = output_path.replace(".mp4", "") + ".mp4"
        merge_timeout = max(
            60,
            int(os.environ.get("PICKLEBALL_MERGE_TIMEOUT_SECONDS", "3600")),
        )

        def is_decodable(path: str) -> bool:
            """Reject MP4 files whose container exists but whose H.264 is damaged."""
            try:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-fflags",
                        "+discardcorrupt",
                        "-err_detect",
                        "ignore_err",
                        "-i",
                        path,
                        "-map",
                        "0:v:0",
                        "-f",
                        "null",
                        "-",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=merge_timeout,
                )
                if result.returncode != 0:
                    logger.warning("合并输出解码校验失败: %s\n%s", path, (result.stderr or "")[-1200:])
                    return False
                return True
            except (OSError, subprocess.SubprocessError) as exc:
                logger.warning("合并输出解码校验异常: %s", exc)
                return False

        def run_ffmpeg(cmd: list[str], step: str) -> None:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=merge_timeout,
            )
            if result.returncode == 0:
                return
            detail = (result.stderr or result.stdout or "").strip()
            detail = detail[-2000:] if detail else "无 FFmpeg 错误输出"
            logger.error("双摄视频合并失败 [%s]: returncode=%s\n%s", step, result.returncode, detail)
            raise RuntimeError(f"{step}失败: {detail}")

        # 先解决多文件输入：concat 所有 TS 片段为一个临时文件
        input_file = file_paths[0]
        temp_concat = None
        if len(file_paths) > 1:
            temp_concat = output_path + ".merged.ts"
            concat_file = output_path + ".concat.txt"
            try:
                with open(concat_file, "w", encoding="utf-8") as f:
                    for fp in file_paths:
                        f.write(f"file '{os.path.abspath(fp)}'\n")
                run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        concat_file,
                        "-c",
                        "copy",
                        temp_concat,
                    ],
                    "TS 分段预合并",
                )
                if not os.path.exists(temp_concat):
                    raise RuntimeError("TS 分段预合并没有生成输出文件")
                input_file = temp_concat
            finally:
                if os.path.exists(concat_file):
                    os.remove(concat_file)

        need_trim = trim_start > 0.001 or target_frames is not None

        if not need_trim:
            # 先尝试无损封装，但必须校验解码结果；部分摄像头 TS 的 NAL
            # 边界在 MP4 中并不总是可靠，不能只用 ffprobe 的时长判断成功。
            temp_mp4 = f"{mp4_path}.{uuid.uuid4().hex}.part.mp4"
            try:
                run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        input_file,
                        "-map",
                        "0:v:0",
                        "-an",
                        "-c",
                        "copy",
                        "-movflags",
                        "+frag_keyframe+empty_moov+default_base_moof",
                        temp_mp4,
                    ],
                    "TS 转 MP4",
                )
                if not (os.path.exists(temp_mp4) and os.path.getsize(temp_mp4) > 0 and is_decodable(temp_mp4)):
                    logger.warning("TS 无损封装输出不可解码，回退到 H.264 重编码: %s", input_file)
                    Path(temp_mp4).unlink(missing_ok=True)
                    run_ffmpeg(
                        [
                            "ffmpeg",
                            "-y",
                            "-fflags",
                            "+discardcorrupt",
                            "-err_detect",
                            "ignore_err",
                            "-i",
                            input_file,
                            "-map",
                            "0:v:0",
                            "-an",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "veryfast",
                            "-pix_fmt",
                            "yuv420p",
                            "-fps_mode",
                            "cfr",
                            "-r",
                            str(max(fps, 1)),
                            "-movflags",
                            "+frag_keyframe+empty_moov+default_base_moof",
                            temp_mp4,
                        ],
                        "TS 重编码并转 MP4",
                    )
                if not (os.path.exists(temp_mp4) and os.path.getsize(temp_mp4) > 0 and is_decodable(temp_mp4)):
                    raise RuntimeError("TS 转 MP4 输出无法解码")
                os.replace(temp_mp4, mp4_path)
                return mp4_path
            finally:
                if os.path.exists(temp_mp4):
                    os.remove(temp_mp4)
                if temp_concat and os.path.exists(temp_concat):
                    try:
                        os.remove(temp_concat)
                    except OSError:
                        pass

        # 有同步裁剪需求时，一次性从共同起点输出目标帧数。
        # 旧逻辑会把完整 TS 和尾部 MP4 放进同一个 concat 清单，导致
        # FFmpeg 输入格式不一致并稳定失败；这里不再拼接混合格式片段。
        encoder = (
            self._recorder._sync_encoder()
            if hasattr(self, "_recorder")
            else ("h264_videotoolbox" if platform.system() == "Darwin" else "libx264")
        )
        encoder_opts = (
            [
                "-preset",
                "veryfast",
                # 将摄像头常见的 full-range yuvj420p 转为 Finder/Quick Look
                # 和浏览器都更稳定支持的标准 limited-range yuv420p。
                "-vf",
                "scale=in_range=full:out_range=tv,format=yuv420p",
                "-pix_fmt",
                "yuv420p",
                "-color_range",
                "tv",
                "-profile:v",
                "main",
                "-level",
                "4.2",
                "-fps_mode",
                "cfr",
                "-video_track_timescale",
                "90000",
            ]
            if encoder == "libx264"
            else []
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-fflags",
            "+discardcorrupt",
            "-err_detect",
            "ignore_err",
            "-i",
            input_file,
        ]
        # 放在 -i 之后进行精确解码剪切。输入前的快速 seek 会跳到关键帧，
        # 在 TS 片段中可能额外丢掉数帧，反而放大双摄首帧误差。
        if trim_start > 0.001:
            cmd.extend(["-ss", f"{trim_start:.6f}"])
        cmd.extend(["-map", "0:v:0", "-an"])
        if target_frames is not None:
            cmd.extend(["-frames:v", str(max(1, target_frames))])
        temp_mp4 = f"{mp4_path}.{uuid.uuid4().hex}.part.mp4"
        cmd.extend(
            [
                "-c:v",
                encoder,
                *encoder_opts,
                "-r",
                str(max(fps, 1)),
                "-avoid_negative_ts",
                "make_zero",
                "-fflags",
                "+genpts",
                # Fragmented MP4 writes its moov metadata incrementally and avoids
                # faststart's second pass, which can fail on damaged tail packets.
                "-movflags",
                "+frag_keyframe+empty_moov+default_base_moof",
                temp_mp4,
            ]
        )
        try:
            run_ffmpeg(cmd, "同步裁剪并转 MP4")
            if not (os.path.exists(temp_mp4) and os.path.getsize(temp_mp4) > 0 and is_decodable(temp_mp4)):
                raise RuntimeError("同步裁剪并转 MP4 输出无法解码")
            os.replace(temp_mp4, mp4_path)
            return mp4_path
        finally:
            if os.path.exists(temp_mp4):
                os.remove(temp_mp4)
            if temp_concat and os.path.exists(temp_concat):
                try:
                    os.remove(temp_concat)
                except OSError:
                    pass

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
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
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

        # TrackRecorder 和旧版 SyncRecorder 都必须先完全停止，才可以删除片段。
        coordinator = self._active_coordinator
        self._active_coordinator = None
        if coordinator is not None:
            coordinator.stop_tracks()
        else:
            self._recorder.stop_recording()
        self._stop_showcase_runtime(session)
        stopped_at = datetime.now(UTC)
        duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0

        session = session.model_copy(
            update={
                "status": "canceled",
                "stopped_at": stopped_at,
                "duration_sec": duration,
                "segments": self._segments,
            }
        )

        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()

        self._finalize_capture_take(session, "canceled")

        # “取消”表示放弃这次录制：所有双摄片段、合并视频和临时文件均不保留。
        import shutil

        shutil.rmtree(Path(session.output_dir), ignore_errors=True)

        logger.info("双摄同步录制已取消: %s", session_id)
        return session

    # ── TrackRecorder v2 集成 ─────────────────────────────────────

    def _start_with_track_recorder(self, request: SyncStartRequest):
        """使用 TrackRecorder × 2 + StrictSyncPolicy 启动双摄。"""
        from app.camera.capture_runtime_coordinator import CaptureRuntimeCoordinator, TrackRuntimeInfo
        from app.camera.recording_policy import StrictSyncPolicy
        from app.services.capture_start_coordinator import CaptureTrackSpec

        cam_1 = camera_registry.get(request.cam_1_id)
        cam_2 = camera_registry.get(request.cam_2_id)
        if not cam_1 or not cam_2:
            raise ValueError("摄像头不存在")

        field_session_id = request.field_session_id
        if not field_session_id:
            raise ValueError("field_session_id 不可为空")
        court_name = request.court_name or ""
        match_format = request.match_format or "doubles"
        display_mode = "standard"
        if field_session_id:
            from app.database import get_session_factory
            from app.services.field_session_service import get_field_session

            db = get_session_factory()()
            try:
                fs = get_field_session(db, field_session_id)
                if fs:
                    if not court_name:
                        court_name = fs.court_name
                    if request.match_format is None:
                        match_format = fs.match_format.value
                    raw_display_mode = getattr(fs, "display_mode", "standard")
                    display_mode = getattr(raw_display_mode, "value", raw_display_mode)
                    if display_mode not in {"standard", "showcase"}:
                        display_mode = "standard"
                    if display_mode == "showcase" and getattr(fs.camera_setup, "value", fs.camera_setup) != "dual":
                        raise ValueError("展示模式只能与双摄方案组合")
            finally:
                db.close()

        session_id = self._generate_session_id()
        try:
            plan = create_capture_storage_plan(f"take_{session_id}", request.storage_root)
        except CaptureStorageError as exc:
            raise RuntimeError(str(exc)) from exc
        output_dir = plan.take_dir

        prep = self._coordinator.prepare_start(
            source_session_type="sync_recording",
            source_session_id=session_id,
            field_session_id=field_session_id,
            capture_mode="dual",
            tracks=[
                CaptureTrackSpec(slot="cam_1", camera_id=request.cam_1_id, analysis_role="default"),
                CaptureTrackSpec(slot="cam_2", camera_id=request.cam_2_id, analysis_role="supplementary"),
            ],
        )

        coord = CaptureRuntimeCoordinator()
        coord.start_tracks(
            take_id=prep.capture_take_id,
            tracks_info=[
                TrackRuntimeInfo(
                    track_id=prep.tracks[0].capture_track_id,
                    slot="cam_1",
                    camera_id=request.cam_1_id,
                    analysis_role="default",
                    stream_url=cam_1.stream_url,
                    output_dir=str(output_dir),
                    fps=request.fps,
                    sync_to_host_clock=True,
                ),
                TrackRuntimeInfo(
                    track_id=prep.tracks[1].capture_track_id,
                    slot="cam_2",
                    camera_id=request.cam_2_id,
                    analysis_role="supplementary",
                    stream_url=cam_2.stream_url,
                    output_dir=str(output_dir),
                    fps=request.fps,
                    sync_to_host_clock=True,
                ),
            ],
            policy=StrictSyncPolicy(),
        )

        session = SyncRecordingSession(
            session_id=session_id,
            field_session_id=field_session_id,
            status="recording",
            capture_take_id=prep.capture_take_id,
            camera_slots={
                "cam_1": CameraSlotConfig(
                    role="cam_1",
                    camera_id=request.cam_1_id,
                    camera_angle=request.cam_1_angle or "baseline_high",
                    stream_url_snapshot=cam_1.stream_url,
                ),
                "cam_2": CameraSlotConfig(
                    role="cam_2",
                    camera_id=request.cam_2_id,
                    camera_angle=request.cam_2_angle or "baseline_high",
                    stream_url_snapshot=cam_2.stream_url,
                ),
            },
            output_dir=str(output_dir),
            court_name=court_name,
            match_format=match_format,
            fps=request.fps,
            resolution=request.resolution,
            auto_analyze_after_stop=request.auto_analyze_after_stop,
            started_at=datetime.now(UTC),
            storage_root=str(plan.storage_root),
            session_dir=str(plan.take_dir),
            display_mode=display_mode,
        )

        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS
        _ACTIVE_SYNC_SESSION_ID = session_id
        _ACTIVE_SYNC_CAMERAS = {request.cam_1_id, request.cam_2_id}

        SYNC_SESSIONS[session_id] = session
        self._persist(session)
        self._active_coordinator = coord
        self._coordinator.activate(prep.capture_take_id)

        session = self._start_showcase_runtime(session)
        self._persist(session)
        return session, prep

    def _stop_with_track_recorder(self, session_id: str, coordinator):
        session = SYNC_SESSIONS.get(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        _, outcome = coordinator.stop_tracks()
        self._stop_showcase_runtime(session)

        stopped_at = datetime.now(UTC)
        duration = (stopped_at - session.started_at).total_seconds() if session.started_at else 0
        terminal_status = "failed" if getattr(outcome, "primary_track_lost", False) else "completed"
        session = session.model_copy(
            update={
                "status": terminal_status,
                "stopped_at": stopped_at,
                "duration_sec": duration,
                "default_analysis_video_id": None,
                "registered_video_ids": {},
                "merge_status": "pending",
                "merge_error": None,
                "merge_results": {},
            }
        )
        SYNC_SESSIONS[session_id] = session
        self._persist(session)

        global _ACTIVE_SYNC_SESSION_ID, _ACTIVE_SYNC_CAMERAS
        _ACTIVE_SYNC_SESSION_ID = None
        _ACTIVE_SYNC_CAMERAS.clear()

        self._finalize_capture_take(session, terminal_status)

        return session

    # ── 删除 ──────────────────────────────────────────────────────

    def delete_session(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        if session is None:
            return {"session_id": session_id, "status": "not_found", "detail": "同步录制会话不存在"}
        if session.status == "recording":
            return {"session_id": session_id, "status": "blocked", "detail": "录制进行中，无法删除"}
        if session.merge_status == "running":
            return {"session_id": session_id, "status": "blocked", "detail": "视频合并进行中，无法删除"}

        # 优先使用 CleanupService
        take_id = getattr(session, "capture_take_id", None)
        if take_id and getattr(self, "_cleanup_service", None):
            json_path = str(self._session_path(session_id))
            output_dir = str(Path(session.output_dir) if session.output_dir else self._output_dir(session_id))
            result = self._cleanup_service.delete_take(
                take_id,
                delete_media=True,
                session_json_path=json_path,
                output_dir=output_dir,
            )
            SYNC_SESSIONS.pop(session_id, None)
            for slot in ("cam_1", "cam_2"):
                slot_info = (
                    session.camera_slots.get(slot)
                    if hasattr(session, "camera_slots") and session.camera_slots
                    else None
                )
                cam_id = getattr(slot_info, "camera_id", None) if slot_info else None
                if cam_id:
                    global _ACTIVE_SYNC_CAMERAS
                    _ACTIVE_SYNC_CAMERAS.discard(cam_id)
            return {"session_id": session_id, **result}

        # Fallback: 原有内联清理逻辑

        # 清理视频文件/输出目录
        output_dir = Path(session.output_dir) if session.output_dir else self._output_dir(session_id)
        if output_dir.exists():
            import shutil

            shutil.rmtree(output_dir)

        # 清理与会话关联的其他视频路径
        for path_str in session.associated_video_paths:
            p = Path(path_str)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        # 清理 DB 记录（按 recording_session_id）
        try:
            from app.database import get_session_factory
            from app.models.timeline_event import SessionTimelineEvent

            db = get_session_factory()()
            try:
                db.query(SessionTimelineEvent).filter(SessionTimelineEvent.recording_session_id == session_id).delete()
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("级联删除同步录制 DB 记录失败: %s", exc)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("连接数据库级联删除失败: %s", exc)

        # 删除会话 JSON
        path = self._session_path(session_id)
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

        # 从内存缓存移除
        SYNC_SESSIONS.pop(session_id, None)
        for slot in ("cam_1", "cam_2"):
            cam_id = session.camera_slots.get(slot, "").camera_id if session.camera_slots.get(slot) else None
            if cam_id:
                _ACTIVE_SYNC_CAMERAS.discard(cam_id)

        logger.info("同步录制会话已删除: %s", session_id)
        return {"session_id": session_id, "status": "deleted", "detail": "同步录制会话已删除"}

    # ── 查询接口 ──────────────────────────────────────────────────

    def get_session(self, session_id: str) -> SyncRecordingSession | None:
        cached = SYNC_SESSIONS.get(session_id)
        if cached:
            return self._repair_registered_video_metadata(cached)
        loaded = self._load(session_id)
        return self._repair_registered_video_metadata(loaded) if loaded else None

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

                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    session = SyncRecordingSession.model_validate(data)
                    if session.status == "recording" and not self.is_recording():
                        session = session.model_copy(
                            update={
                                "status": "failed",
                                "stopped_at": datetime.now(UTC),
                                "error_message": "服务中没有对应的活动录制进程，会话已恢复为失败状态",
                            }
                        )
                        self._persist(session)
                        if getattr(session, "capture_take_id", None):
                            try:
                                from app.database import get_session_factory
                                from app.services.capture_take_service import finalize_capture_take

                                db = get_session_factory()()
                                try:
                                    finalize_capture_take(db, session.capture_take_id, "failed")
                                    db.commit()
                                finally:
                                    db.close()
                            except Exception:
                                pass
                    session = self._repair_registered_video_metadata(session)
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
