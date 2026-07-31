"""
双摄同步录制测试（SyncRecorder + API）

注意：以下测试需要 FFmpeg + 真实 RTSP 流才能完整运行。
本地 CI 环境无硬件时，这些测试会被标记为 skip。
"""

import os
import sys
import json
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
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

    def test_extracts_first_middle_and_last_frame(self, tmp_path):
        from app.camera.sync_recorder_service import _extract_first_and_last_frames

        video_path = tmp_path / "camera_s1.ts"
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.return_value = 101
        capture.read.side_effect = [(True, "first"), (True, "middle"), (True, "last")]

        with (
            patch("app.camera.sync_recorder_service.cv2.VideoCapture", return_value=capture),
            patch("app.camera.sync_recorder_service.cv2.imwrite", return_value=True) as imwrite,
        ):
            first, last = _extract_first_and_last_frames(str(video_path))

        assert first == str(tmp_path / "camera_s1_first_frame.jpg")
        assert last == str(tmp_path / "camera_s1_last_frame.jpg")
        assert capture.set.call_args_list == [
            call(1, 0),
            call(1, 50),
            call(1, 100),
        ]
        assert [Path(args.args[0]).name for args in imwrite.call_args_list] == [
            "camera_s1_first_frame.jpg",
            "camera_s1_middle_frame.jpg",
            "camera_s1_last_frame.jpg",
        ]

    def test_external_volume_uses_local_staging_on_macos(self, tmp_path):
        from app.camera.sync_recorder_service import SyncRecordingService

        staging = tmp_path / "pickleball-sync_test-abc123"
        with (
            patch("app.camera.sync_recorder_service.platform.system", return_value="Darwin"),
            patch("app.camera.sync_recorder_service.tempfile.mkdtemp", return_value=str(staging)) as mkdtemp,
        ):
            result = SyncRecordingService._recording_staging_dir(
                "sync_test", Path("/Volumes/Elements/captures/take_sync_test")
            )

        assert result == staging
        mkdtemp.assert_called_once_with(prefix="pickleball-sync_test-")

    def test_internal_volume_does_not_use_staging(self):
        from app.camera.sync_recorder_service import SyncRecordingService

        with patch("app.camera.sync_recorder_service.platform.system", return_value="Darwin"):
            result = SyncRecordingService._recording_staging_dir(
                "sync_test", Path("/Users/tuian/captures/take_sync_test")
            )

        assert result is None

    def test_common_overlap_alignment_uses_same_frame_count(self):
        from app.camera.models import CameraSlotConfig, SyncRecordingSession, SyncSegment, SyncSegmentFile
        from app.camera.sync_recorder_service import SyncRecordingService

        session = SyncRecordingSession(
            session_id="sync_alignment",
            camera_slots={
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="174"),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="175"),
            },
            segments=[SyncSegment(segment_index=1, files=[
                SyncSegmentFile(camera_id="174", role="cam_1", file_path="174.ts", media_duration_sec=28.633333, input_start_time=100.118133),
                SyncSegmentFile(camera_id="175", role="cam_2", file_path="175.ts", media_duration_sec=28.616667, input_start_time=100.0),
            ])],
            fps=60,
        )

        alignment = SyncRecordingService._compute_sync_alignment(session)

        assert alignment["cam_1"] == (0.0, 1709)
        assert alignment["cam_2"] == pytest.approx((7 / 60, 1709))

    def test_multi_segment_alignment_sums_frames_across_segments(self):
        from app.camera.models import CameraSlotConfig, SyncRecordingSession, SyncSegment, SyncSegmentFile
        from app.camera.sync_recorder_service import SyncRecordingService

        session = SyncRecordingSession(
            session_id="multi_segment_alignment",
            camera_slots={
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="174"),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="175"),
            },
            segments=[
                SyncSegment(segment_index=1, files=[
                    SyncSegmentFile(camera_id="174", role="cam_1", file_path="174_s1.ts",
                                    media_duration_sec=10.0, input_start_time=100.0),
                    SyncSegmentFile(camera_id="175", role="cam_2", file_path="175_s1.ts",
                                    media_duration_sec=9.5, input_start_time=100.5),
                ]),
                SyncSegment(segment_index=2, files=[
                    SyncSegmentFile(camera_id="174", role="cam_1", file_path="174_s2.ts",
                                    media_duration_sec=10.0, input_start_time=150.0),
                    SyncSegmentFile(camera_id="175", role="cam_2", file_path="175_s2.ts",
                                    media_duration_sec=10.0, input_start_time=151.0),
                ]),
            ],
            fps=60,
        )

        alignment = SyncRecordingService._compute_sync_alignment(session)

        assert "cam_1" in alignment
        assert "cam_2" in alignment
        trim_1, frames_1 = alignment["cam_1"]
        trim_2, frames_2 = alignment["cam_2"]
        # Segment 1 overlap: max(100.0, 100.5)=100.5, min(110.0, 110.0)=110.0 → 9.5s * 60 = 570 frames
        # Segment 2 overlap: max(150.0, 151.0)=151.0, min(160.0, 161.0)=160.0 → 9.0s * 60 = 540 frames
        # Total: 570 + 540 = 1110 frames
        assert frames_1 == 1110
        assert frames_2 == 1110
        # Trim for cam_1: common_first_start(100.5) - cam_1_first(100.0) = 0.5s
        assert trim_1 == pytest.approx(0.5)
        # Trim for cam_2: common_first_start(100.5) - cam_2_first(100.5) = 0.0
        assert trim_2 == pytest.approx(0.0)

    def test_multi_segment_alignment_skips_segment_without_overlap(self):
        from app.camera.models import CameraSlotConfig, SyncRecordingSession, SyncSegment, SyncSegmentFile
        from app.camera.sync_recorder_service import SyncRecordingService

        session = SyncRecordingSession(
            session_id="multi_segment_no_overlap",
            camera_slots={
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="174"),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="175"),
            },
            segments=[
                SyncSegment(segment_index=1, files=[
                    SyncSegmentFile(camera_id="174", role="cam_1", file_path="174_s1.ts",
                                    media_duration_sec=10.0, input_start_time=100.0),
                    SyncSegmentFile(camera_id="175", role="cam_2", file_path="175_s1.ts",
                                    media_duration_sec=10.0, input_start_time=100.0),
                ]),
                SyncSegment(segment_index=2, files=[
                    SyncSegmentFile(camera_id="174", role="cam_1", file_path="174_s2.ts",
                                    media_duration_sec=5.0, input_start_time=200.0),
                    SyncSegmentFile(camera_id="175", role="cam_2", file_path="175_s2.ts",
                                    media_duration_sec=5.0, input_start_time=300.0),
                ]),
            ],
            fps=60,
        )

        alignment = SyncRecordingService._compute_sync_alignment(session)

        assert "cam_1" in alignment
        assert "cam_2" in alignment
        # Segment 2 has no overlap (200.0+5.0=205.0 < 300.0), so only segment 1 counts
        trim_1, frames = alignment["cam_1"]
        assert frames == 600  # 10s * 60fps

    def test_multi_segment_alignment_single_segment_fallback(self):
        from app.camera.models import CameraSlotConfig, SyncRecordingSession, SyncSegment, SyncSegmentFile
        from app.camera.sync_recorder_service import SyncRecordingService

        session = SyncRecordingSession(
            session_id="single_segment",
            camera_slots={
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="174"),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="175"),
            },
            segments=[SyncSegment(segment_index=1, files=[
                SyncSegmentFile(camera_id="174", role="cam_1", file_path="174.ts",
                                media_duration_sec=20.0, input_start_time=100.0),
                SyncSegmentFile(camera_id="175", role="cam_2", file_path="175.ts",
                                media_duration_sec=20.0, input_start_time=99.5),
            ])],
            fps=30,
        )

        alignment = SyncRecordingService._compute_sync_alignment(session)

        trim_1, frames = alignment["cam_1"]
        assert trim_1 == 0.0
        # common_start = max(100.0, 99.5) = 100.0
        # common_end = min(120.0, 119.5) = 119.5
        # duration = 19.5s → 19.5 * 30 = 585 frames
        assert frames == 585

    def test_merge_with_frame_alignment_does_not_concat_full_ts_with_tail_mp4(self, tmp_path):
        from app.camera.sync_recorder_service import SyncRecordingService

        source = tmp_path / "cam_1.ts"
        output = tmp_path / "cam_1_merged.mp4"
        source.write_bytes(b"ts")
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            if cmd[-1] != "-":
                Path(cmd[-1]).write_bytes(b"mp4")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("app.camera.sync_recorder_service.subprocess.run", side_effect=fake_run):
            result = SyncRecordingService()._merge_segments(
                [str(source)], str(output), trim_start=0.0, target_frames=120, fps=60,
            )

        assert result == str(output)
        assert len(commands) == 2
        assert commands[0][-1].startswith(str(output) + ".")
        assert commands[0][-1].endswith(".part.mp4")
        assert commands[0][commands[0].index("-frames:v") + 1] == "120"
        assert "-f" not in commands[0]
        assert commands[1][-1] == "-"

    def test_merge_places_trim_after_input_for_frame_accurate_seek(self, tmp_path):
        from app.camera.sync_recorder_service import SyncRecordingService

        source = tmp_path / "cam_2.ts"
        output = tmp_path / "cam_2_merged.mp4"
        source.write_bytes(b"ts")
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            if cmd[-1] != "-":
                Path(cmd[-1]).write_bytes(b"mp4")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("app.camera.sync_recorder_service.subprocess.run", side_effect=fake_run):
            SyncRecordingService()._merge_segments(
                [str(source)], str(output), trim_start=5 / 60, target_frames=120, fps=60,
            )

        cmd = commands[0]
        assert cmd.index("-i") < cmd.index("-ss")

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

    def test_common_overlap_quantizes_network_alignment_to_source_frames(self):
        from app.camera.models import CameraSlotConfig, SyncRecordingSession, SyncSegment, SyncSegmentFile
        from app.camera.sync_recorder_service import SyncRecordingService

        session = SyncRecordingSession(
            session_id="sync_media_alignment",
            camera_slots={
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="174"),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="175"),
            },
            segments=[SyncSegment(segment_index=1, files=[
                SyncSegmentFile(camera_id="174", role="cam_1", file_path="174.ts", media_duration_sec=18.65,
                                input_start_time=100.035, media_start_time_sec=1.4),
                SyncSegmentFile(camera_id="175", role="cam_2", file_path="175.ts", media_duration_sec=18.75,
                                input_start_time=100.0, media_start_time_sec=1.4),
            ])],
            fps=60,
        )

        alignment = SyncRecordingService._compute_sync_alignment(session)

        assert alignment["cam_1"] == (0.0, 1119)
        assert alignment["cam_2"] == pytest.approx((2 / 60, 1119))

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

    def test_terminate_all_processes_signals_every_track_before_waiting(self):
        """尾帧同步要求不能等待第一路退出后才终止第二路。"""
        from app.camera.sync_recorder_service import SyncRecorder

        order: list[str] = []
        first_wait = True

        class FakeProcess:
            def __init__(self, name: str):
                self.name = name
                self.pid = 1
                self.running = True

            def poll(self):
                return None if self.running else 0

            def terminate(self):
                order.append(f"terminate:{self.name}")

            def wait(self, timeout=None):
                nonlocal first_wait
                if first_wait:
                    assert order == ["terminate:cam_1", "terminate:cam_2"]
                    first_wait = False
                order.append(f"wait:{self.name}")
                self.running = False
                return 0

            def kill(self):
                self.running = False

        recorder = SyncRecorder()
        recorder.processes = [FakeProcess("cam_1"), FakeProcess("cam_2")]
        recorder._terminate_all_processes()

        assert order[:2] == ["terminate:cam_1", "terminate:cam_2"]

    def test_extract_first_and_last_frames_empty_video_returns_none(self, tmp_path):
        from app.camera.sync_recorder_service import _extract_first_and_last_frames

        video_path = tmp_path / "empty.ts"
        video_path.write_bytes(b"")
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.return_value = 0

        with patch("app.camera.sync_recorder_service.cv2.VideoCapture", return_value=capture):
            first, last = _extract_first_and_last_frames(str(video_path))

        assert first is None
        assert last is None

    def test_extract_first_and_last_frames_unopenable_returns_none(self, tmp_path):
        from app.camera.sync_recorder_service import _extract_first_and_last_frames

        video_path = tmp_path / "missing.ts"
        with patch("app.camera.sync_recorder_service.cv2.VideoCapture", return_value=MagicMock(isOpened=lambda: False)):
            first, last = _extract_first_and_last_frames(str(video_path))

        assert first is None
        assert last is None

    def test_pts_sidecar_round_trip_matches_frame_timing(self, tmp_path):
        from app.services.dual_camera_sync import (
            write_frame_timing_sidecar,
            read_frame_timing_sidecar,
        )

        sidecar = tmp_path / "frames.jsonl"
        fake = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"frames": [
                {"best_effort_timestamp_time": "1.400000", "pkt_dts_time": "1.400000", "key_frame": 1},
                {"best_effort_timestamp_time": "1.416667", "pkt_dts_time": "1.416667", "key_frame": 0},
                {"best_effort_timestamp_time": "1.433333", "pkt_dts_time": "1.433333", "key_frame": 0},
            ]}),
            stderr="",
        )
        with patch("app.services.dual_camera_sync.subprocess.run", return_value=fake):
            summary = write_frame_timing_sidecar("source.ts", sidecar)

        assert summary["frame_count"] == 3
        assert summary["first_pts_seconds"] == 1.4
        assert summary["last_pts_seconds"] == pytest.approx(1.433333)

        frames = read_frame_timing_sidecar(sidecar)
        assert len(frames) == 3
        assert frames[0].frame_index == 0
        assert frames[0].keyframe is True
        assert frames[2].keyframe is False

    def test_pts_sidecar_frames_are_monotonic(self, tmp_path):
        from app.services.dual_camera_sync import write_frame_timing_sidecar

        sidecar = tmp_path / "frames.jsonl"
        fake = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"frames": [
                {"best_effort_timestamp_time": "1.400", "pkt_dts_time": "1.400", "key_frame": 1},
                {"best_effort_timestamp_time": "1.417", "pkt_dts_time": "1.416", "key_frame": 0},
                {"best_effort_timestamp_time": "1.433", "pkt_dts_time": "1.433", "key_frame": 0},
            ]}),
            stderr="",
        )
        with patch("app.services.dual_camera_sync.subprocess.run", return_value=fake):
            summary = write_frame_timing_sidecar("source.ts", sidecar)

        assert summary["frame_count"] == 3
        lines = sidecar.read_text().splitlines()
        pts_values = [json.loads(line)["pts_seconds"] for line in lines]
        assert pts_values == sorted(pts_values)

    def test_dual_command_preserves_source_frames(self, monkeypatch):
        from app.camera.sync_recorder_service import SyncRecorder

        monkeypatch.setenv("PICKLEBALL_SYNC_VIDEO_ENCODER", "libx264")
        recorder = SyncRecorder()
        recorder.fps = 60
        cmd = recorder._build_record_command("rtsp://camera/live", "/tmp/cam.ts", duration=5)

        assert ["-rtsp_transport", "udp"] == cmd[cmd.index("-rtsp_transport"):cmd.index("-rtsp_transport") + 2]
        assert ["-timeout", "5000000"] == cmd[cmd.index("-timeout"):cmd.index("-timeout") + 2]
        assert ["-fflags", "+genpts"] == cmd[cmd.index("-fflags"):cmd.index("-fflags") + 2]
        assert ["-map", "0:v:0"] == cmd[cmd.index("-map"):cmd.index("-map") + 2]
        assert ["-c:v", "copy"] == cmd[cmd.index("-c:v"):cmd.index("-c:v") + 2]
        assert "-use_wallclock_as_timestamps" not in cmd
        assert "-vf" not in cmd
        assert "-fps_mode" not in cmd
        assert "-r" not in cmd

    def test_probe_media_diagnostics_calculates_effective_fps(self, tmp_path):
        """诊断必须以实际包数/媒体时长衡量帧率，不能相信 TS 声明帧率。"""
        from app.camera.sync_recorder_service import _probe_media_diagnostics

        video = tmp_path / "sample.ts"
        video.write_bytes(b"media")
        payload = {"streams": [{"nb_read_packets": "300"}], "format": {"duration": "10.0"}}
        with patch("app.camera.sync_recorder_service.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(payload))
            packets, duration, effective_fps = _probe_media_diagnostics(str(video))

        assert (packets, duration, effective_fps) == (300, 10.0, 30.0)


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

    def test_custom_dual_capture_directories_are_unique(self, tmp_path):
        from app.camera.sync_recorder_service import sync_recording_service

        first = sync_recording_service._output_dir("sync_first", str(tmp_path), "take_first")
        second = sync_recording_service._output_dir("sync_second", str(tmp_path), "take_second")
        assert first != second
        assert first.parent.parent.name == "captures"
        assert second.parent.parent.name == "captures"
        assert first.exists() and second.exists()

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

    def test_cancel_session_removes_recording_output(self, tmp_path):
        """取消双摄录制必须丢弃所有已写入的媒体片段。"""
        from app.camera import sync_recorder_service as module
        from app.camera.models import SyncRecordingSession

        class FakeRecorder:
            stopped = False

            def stop_recording(self):
                self.stopped = True

        recorder = FakeRecorder()
        service = module.SyncRecordingService(sync_recorder_factory=lambda: recorder)
        output_dir = tmp_path / "sync_cancelled"
        output_dir.mkdir()
        (output_dir / "cam_1_s1.ts").write_bytes(b"partial-media")
        session = SyncRecordingSession(
            session_id="sync_cancel_cleanup",
            status="recording",
            camera_slots={},
            output_dir=str(output_dir),
        )
        module.SYNC_SESSIONS[session.session_id] = session

        try:
            with patch.object(service, "_persist"), patch.object(service, "_finalize_capture_take"):
                cancelled = service.cancel_session(session.session_id)

            assert cancelled.status == "canceled"
            assert recorder.stopped is True
            assert not output_dir.exists()
        finally:
            module.SYNC_SESSIONS.pop(session.session_id, None)

    def test_storage_failure_stops_dual_recording_and_preserves_session(self, tmp_path):
        from app.camera import sync_recorder_service as module
        from app.camera.models import SyncRecordingSession

        class FakeRecorder:
            stopped = False

            def stop_recording(self):
                self.stopped = True

        recorder = FakeRecorder()
        service = module.SyncRecordingService(sync_recorder_factory=lambda: recorder)
        output_dir = tmp_path / "dual_failure"
        output_dir.mkdir()
        session = SyncRecordingSession(
            session_id="sync_storage_failure",
            status="recording",
            camera_slots={},
            output_dir=str(output_dir),
            session_dir=str(output_dir),
        )
        module.SYNC_SESSIONS[session.session_id] = session
        try:
            with patch.object(module, "capture_storage_is_available", return_value=False), \
                 patch.object(service, "_persist"), \
                 patch.object(service, "_finalize_capture_take"):
                service._recorder = recorder
                service._handle_storage_failure(session.session_id, "介质不可访问")

            failed = module.SYNC_SESSIONS[session.session_id]
            assert recorder.stopped is True
            assert failed.status == "failed"
            assert failed.storage_status == "failed"
            assert "介质不可访问" in (failed.error_message or "")
        finally:
            module.SYNC_SESSIONS.pop(session.session_id, None)

    def test_stop_does_not_register_or_merge_videos(self, tmp_path):
        from datetime import datetime, timezone
        from app.camera import sync_recorder_service as module
        from app.camera.models import SyncRecordingSession

        class FakeRecorder:
            def stop_recording(self):
                return None

        service = module.SyncRecordingService(sync_recorder_factory=lambda: FakeRecorder())
        session = SyncRecordingSession(
            session_id="sync_stop_without_merge",
            status="recording",
            camera_slots={},
            output_dir=str(tmp_path),
            started_at=datetime.now(timezone.utc),
        )
        module.SYNC_SESSIONS[session.session_id] = session
        try:
            with patch.object(service, "_persist"), \
                 patch.object(service, "_finalize_capture_take"), \
                 patch.object(service, "_materialize_staged_media", return_value=session), \
                 patch.object(service, "_register_session_videos") as register:
                stopped = service.stop_session(session.session_id)

            assert stopped.session.merge_status == "pending"
            assert stopped.analysis_available is False
            register.assert_not_called()
        finally:
            module.SYNC_SESSIONS.pop(session.session_id, None)

    def test_merge_request_is_persisted_and_rejects_duplicate(self, tmp_path):
        from app.camera import sync_recorder_service as module
        from app.camera.models import CameraSlotConfig, SyncRecordingSession, SyncSegment, SyncSegmentFile

        ts_path = tmp_path / "cam_1.ts"
        ts_path.write_bytes(b"ts")
        session = SyncRecordingSession(
            session_id="sync_merge_request",
            status="completed",
            camera_slots={
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="cam_a"),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="cam_b"),
            },
            segments=[SyncSegment(
                segment_index=1,
                status="completed",
                files=[SyncSegmentFile(camera_id="cam_a", role="cam_1", file_path=str(ts_path), file_size=2)],
            )],
            output_dir=str(tmp_path),
        )
        service = module.SyncRecordingService(sync_recorder_factory=lambda: object())
        module.SYNC_SESSIONS[session.session_id] = session
        try:
            with patch.object(service, "_persist"), patch.object(module.threading, "Thread") as thread:
                submitted = service.request_merge(session.session_id)
                assert submitted.merge_status == "running"
                thread.return_value.start.assert_called_once()
                with pytest.raises(RuntimeError, match="合并中"):
                    service.request_merge(session.session_id)
        finally:
            module.SYNC_SESSIONS.pop(session.session_id, None)

    def test_background_merge_requires_both_camera_videos(self, tmp_path):
        from app.camera import sync_recorder_service as module
        from app.camera.models import CameraSlotConfig, SyncRecordingSession

        session = SyncRecordingSession(
            session_id="sync_background_merge",
            status="completed",
            camera_slots={
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="cam_a"),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="cam_b"),
            },
            output_dir=str(tmp_path),
            merge_status="running",
        )
        service = module.SyncRecordingService(sync_recorder_factory=lambda: object())
        module.SYNC_SESSIONS[session.session_id] = session
        merged = session.model_copy(update={
            "registered_video_ids": {"cam_1": "video-a", "cam_2": "video-b"},
            "merge_results": {
                "cam_1": {"status": "succeeded", "video_id": "video-a"},
                "cam_2": {"status": "succeeded", "video_id": "video-b"},
            },
        })
        try:
            with patch.object(service, "_persist"), \
                 patch.object(service, "_persist_capture_manifest"), \
                 patch.object(service, "_register_session_videos", return_value=(merged, None, False, None)):
                service._merge_session_videos_background(session.session_id)

            completed = module.SYNC_SESSIONS[session.session_id]
            assert completed.merge_status == "completed"
            assert completed.default_analysis_video_id == "video-a"
        finally:
            module.SYNC_SESSIONS.pop(session.session_id, None)


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
        assert session.merge_status == "pending"

    def test_legacy_session_merge_status_is_derived(self):
        from app.camera.models import CameraSlotConfig, SyncRecordingSession

        session = SyncRecordingSession.model_validate({
            "session_id": "legacy_sync",
            "status": "completed",
            "camera_slots": {
                "cam_1": CameraSlotConfig(role="cam_1", camera_id="cam_a").model_dump(),
                "cam_2": CameraSlotConfig(role="cam_2", camera_id="cam_b").model_dump(),
            },
            "registered_video_ids": {"cam_1": "video-a", "cam_2": "video-b"},
        })
        assert session.merge_status == "completed"

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
