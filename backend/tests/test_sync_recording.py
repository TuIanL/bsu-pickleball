"""
双摄同步录制测试（SyncRecorder + API）

注意：以下测试需要 FFmpeg + 真实 RTSP 流才能完整运行。
本地 CI 环境无硬件时，这些测试会被标记为 skip。
"""

import os
import sys
import pytest
from pathlib import Path
from pydantic import ValidationError


# ── FFmpeg 可用性检查 ──
def _check_ffmpeg():
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# SyncRecorder 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncRecorderUnit:
    """SyncRecorder 初始化与状态管理测试（不需要 FFmpeg/摄像头）"""

    def test_sync_recorder_initial_state(self):
        """验证初始状态为未录制"""
        from app.camera.sync_recorder_service import SyncRecorder
        recorder = SyncRecorder()
        assert recorder.is_recording is False
        assert recorder.processes == []
        assert recorder.segment_index == 1

    def test_sync_recorder_cannot_start_twice(self):
        """验证不能重复启动录制（模拟状态检查）"""
        from app.camera.sync_recorder_service import SyncRecorder
        recorder = SyncRecorder()
        recorder.is_recording = True  # 模拟已录制
        with pytest.raises(RuntimeError, match="已在运行"):
            recorder.start_recording(
                stream_configs={},
                output_dir="/tmp/test",
            )

    def test_sync_recorder_stop_when_not_recording(self):
        """验证未录制时停止不报错"""
        from app.camera.sync_recorder_service import SyncRecorder
        recorder = SyncRecorder()
        # 不应抛异常
        recorder.stop_recording()

    def test_parse_ip_from_url(self):
        """验证从 RTSP URL 提取 IP"""
        from app.camera.sync_recorder_service import _parse_ip_from_url
        assert _parse_ip_from_url("rtsp://192.168.1.160:8554/0") == "192.168.1.160"
        assert _parse_ip_from_url("rtsp://10.0.0.1:554/stream") == "10.0.0.1"

    def test_get_stream_output_name(self):
        """验证分段输出文件名生成"""
        from app.camera.sync_recorder_service import SyncRecorder
        recorder = SyncRecorder()
        recorder.segment_index = 3
        name = recorder._get_stream_output_name(
            "rtsp://192.168.1.160:8554/0",
            "cam_main",
            3,
        )
        assert name == "cam_main_s3.ts"

    def test_terminate_all_processes_empty(self):
        """验证无进程时 terminate 不报错"""
        from app.camera.sync_recorder_service import SyncRecorder
        recorder = SyncRecorder()
        recorder._terminate_all_processes()  # 不应抛异常


# ═══════════════════════════════════════════════════════════════════════════
# SyncRecordingService 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncRecordingService:
    """SyncRecordingService 业务逻辑测试（不需要 FFmpeg/摄像头）"""

    def test_service_initial_state(self):
        """验证服务初始状态"""
        from app.camera.sync_recorder_service import sync_recording_service
        assert sync_recording_service.is_recording() is False
        assert sync_recording_service.get_active_session() is None

    def test_generate_session_id_format(self):
        """验证会话 ID 格式"""
        from app.camera.sync_recorder_service import sync_recording_service
        sid = sync_recording_service._generate_session_id()
        assert sid.startswith("sync_")
        assert len(sid) > 10

    def test_output_dir_path(self):
        """验证输出目录路径格式"""
        from app.camera.sync_recorder_service import sync_recording_service
        path = sync_recording_service._output_dir("sync_20260708_120000")
        assert "sync-recordings" in str(path)
        assert "sync_20260708_120000" in str(path)

    def test_get_nonexistent_session(self):
        """验证查询不存在会话返回 None"""
        from app.camera.sync_recorder_service import sync_recording_service
        result = sync_recording_service.get_session("nonexistent_id")
        assert result is None

    def test_list_empty_sessions(self):
        """验证空列表返回"""
        from app.camera.sync_recorder_service import sync_recording_service
        # 清理状态后查询
        result = sync_recording_service.list_sessions()
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════
# SyncRecording 模型测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncModels:
    """Pydantic 模型验证测试"""

    def test_sync_start_request_validation(self):
        """验证 SyncStartRequest 模型"""
        from app.camera.models import SyncStartRequest
        req = SyncStartRequest(
            cam_1_id="cam_a",
            cam_2_id="cam_b",
        )
        assert req.cam_1_id == "cam_a"
        assert req.cam_2_id == "cam_b"
        assert req.cam_1_angle == "baseline_high"  # 默认值
        assert req.fps == 60  # 默认值

    def test_recording_start_request_fps_cap(self):
        """验证单摄录制 FPS 默认值和上限"""
        from app.camera.models import RecordingStartRequest
        req = RecordingStartRequest(camera_id="cam_a")
        assert req.fps == 60

        explicit = RecordingStartRequest(camera_id="cam_a", fps=60)
        assert explicit.fps == 60

        with pytest.raises(ValidationError):
            RecordingStartRequest(camera_id="cam_a", fps=61)

    def test_sync_start_request_fps_cap(self):
        """验证双摄录制 FPS 默认值和上限"""
        from app.camera.models import SyncStartRequest
        req = SyncStartRequest(cam_1_id="cam_a", cam_2_id="cam_b")
        assert req.fps == 60

        explicit = SyncStartRequest(cam_1_id="cam_a", cam_2_id="cam_b", fps=60)
        assert explicit.fps == 60

        with pytest.raises(ValidationError):
            SyncStartRequest(cam_1_id="cam_a", cam_2_id="cam_b", fps=61)

    def test_sync_test_request_validation(self):
        """验证 SyncTestRequest 模型"""
        from app.camera.models import SyncTestRequest
        req = SyncTestRequest(
            cam_1_id="cam_a",
            cam_2_id="cam_b",
            duration=5,
        )
        assert req.duration == 5

    def test_sync_recording_session_model(self):
        """验证 SyncRecordingSession 模型字段"""
        from app.camera.models import SyncRecordingSession
        session = SyncRecordingSession(
            session_id="sync_test",
            status="recording",
            camera_slots={},
            output_dir="/tmp/test",
        )
        assert session.session_id == "sync_test"
        assert session.status == "recording"
        assert session.total_restarts == 0

    def test_sync_test_result_all_online(self):
        """验证测试结果模型"""
        from app.camera.models import SyncTestResult
        from datetime import datetime, timezone
        result = SyncTestResult(
            success=True,
            cam_1_id="cam_a",
            cam_2_id="cam_b",
            duration_sec=5.0,
            cam_1_online=True,
            cam_2_online=True,
            cam_1_file_size=1024,
            cam_2_file_size=2048,
            test_completed_at=datetime.now(timezone.utc),
        )
        assert result.success is True
        assert result.cam_1_file_size == 1024

    def test_sync_segment_model(self):
        """验证 SyncSegment 模型"""
        from app.camera.models import SyncSegment, SyncSegmentFile
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        segment = SyncSegment(
            segment_index=1,
            status="completed",
            files=[
                SyncSegmentFile(
                    camera_id="cam_a",
                    role="cam_1",
                    file_path="/tmp/test.ts",
                    file_size=5000,
                    started_at=now,
                    ended_at=now,
                ),
            ],
            started_at=now,
            ended_at=now,
            restart_count=0,
        )
        assert segment.segment_index == 1
        assert len(segment.files) == 1
        assert segment.files[0].camera_id == "cam_a"


# ═══════════════════════════════════════════════════════════════════════════
# 集成测试（需要 FFmpeg + 真实 RTSP 流 — 本地硬件验证用）
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not _check_ffmpeg(),
    reason="需要 FFmpeg 才能进行集成测试",
)
class TestSyncRecorderIntegration:
    """需要 FFmpeg 的集成测试"""

    def test_ffmpeg_available(self):
        """验证 FFmpeg 可用"""
        from app.camera.sync_recorder_service import check_ffmpeg_available
        assert check_ffmpeg_available() is True

    def test_sync_recorder_with_invalid_url(self):
        """验证无效 RTSP 地址的处理——不应抛出异常"""
        from app.camera.sync_recorder_service import SyncRecorder
        import tempfile
        recorder = SyncRecorder()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = recorder.start_test(
                stream_configs={
                    "cam_fake": "rtsp://192.168.1.250:8554/nonexistent",
                },
                output_dir=tmpdir,
                duration=1,
            )
            # 不应抛出异常，即使 URL 无效也应正常返回结果
            assert result.cam_1_id == "cam_fake"
            assert result.duration_sec == 1.0
            # 无效 URL 通常导致文件大小为 0
            assert result.cam_1_file_size == 0
