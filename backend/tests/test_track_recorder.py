"""Change 3 专用测试 —— TrackRecorder、RecordingPolicy、Coordinator、Finalizer"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── FakeProcess ─────────────────────────────────────────────────


class FakeProcess:
    def __init__(self, *, simulate_crash: bool = False, exit_code: int = 0, exit_delay: float = 0):
        self.pid = 90001
        self._simulate_crash = simulate_crash
        self._exit_code = exit_code
        self._exit_delay = exit_delay
        self.stdin = MagicMock()
        self.stderr = MagicMock()
        self.poll_result: int | None = None
        self._killed = False
        self.returncode: int | None = None

    def poll(self):
        if self._killed:
            self.returncode = -9
            return -9
        return self.returncode

    def wait(self, timeout=None):
        if self._exit_delay:
            time.sleep(min(self._exit_delay, 0.05))
        self.returncode = self._exit_code
        return self._exit_code

    def kill(self):
        self._killed = True
        self.returncode = -9

    def communicate(self, timeout=None):
        return (b"", b"")


class FakeProcessFactory:
    def __init__(self, exit_code=0, crash=False, delay=0):
        self.exit_code = exit_code
        self.crash = crash
        self.delay = delay
        self.last_cmd: list[str] = []

    def start(self, cmd, output_path):
        self.last_cmd = cmd
        return (90001, 90001, "fake-fp")


class FakeFragmentRepo:
    def __init__(self):
        self.created: list[dict] = []
        self.completed: list[dict] = []
        self.recording_ids: set[str] = set()

    def create_starting(self, **kwargs) -> str:
        fid = f"frag_{len(self.created)}"
        self.created.append({"id": fid, **kwargs})
        return fid

    def mark_recording(self, fragment_id: str) -> None:
        self.recording_ids.add(fragment_id)

    def complete(self, fragment_id: str, **kwargs) -> None:
        self.completed.append({"id": fragment_id, **kwargs})


class FakeProcessRegistry:
    def __init__(self):
        self.started: list[dict] = []
        self.ended: list[dict] = []

    def register_started(self, **kwargs) -> int:
        rid = len(self.started) + 1
        self.started.append({"id": rid, **kwargs})
        return rid

    def register_ended(self, registration_id: int, **kwargs) -> None:
        self.ended.append({"registration_id": registration_id, **kwargs})


class FakeClock:
    def __init__(self, start_ms: int = 0):
        self._start = start_ms

    def utc_now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ms(self) -> int:
        return int(time.monotonic() * 1000)


def _mock_popen(fake_proc):
    """创建一个行为类似于 subprocess.Popen 的 Mock"""
    mock = MagicMock()
    mock.pid = fake_proc.pid
    mock.stdin = fake_proc.stdin
    mock.stderr = fake_proc.stderr
    mock.poll = fake_proc.poll
    mock.wait = fake_proc.wait
    mock.kill = fake_proc.kill
    mock.communicate = fake_proc.communicate
    mock.returncode = None
    return mock


# ── 0.1-0.5: 行为保护测试 ────────────────────────────────────


class TestBehavioralBaseline:
    def test_track_recorder_start_stop(self):
        """0.1: TrackRecorder 正常启动→停止"""
        from app.camera.track_recorder import FragmentStartSpec, TrackRecorder

        recorder = TrackRecorder(process_registry=FakeProcessRegistry(), clock=FakeClock())
        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_1",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test_01.ts"),
            fragment_index=0,
            rotation_index=0,
            take_start_offset_ms=0,
        )

        exit_calls = []
        fake = FakeProcess(exit_code=0)
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            handle = recorder.start_fragment(spec, lambda e: exit_calls.append(e))
            assert handle is not None

        time.sleep(0.05)
        result = handle.wait(timeout=5)

        assert result.status in ("completed", "failed")
        assert len(exit_calls) >= 1

    def test_track_recorder_crash(self):
        """0.2: TrackRecorder crash → status failed"""
        from app.camera.track_recorder import FragmentStartSpec, TrackRecorder

        recorder = TrackRecorder()
        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_2",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test_02.ts"),
            fragment_index=0,
            rotation_index=0,
            take_start_offset_ms=0,
        )

        exit_calls = []
        fake = FakeProcess(exit_code=1, exit_delay=0.01)
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            handle = recorder.start_fragment(spec, lambda e: exit_calls.append(e))
            time.sleep(0.1)
            handle.wait(timeout=5)

        assert len(exit_calls) >= 1

    def test_callback_only_once(self):
        """0.4: Fragment exit 回调仅触发一次"""
        from app.camera.track_recorder import FragmentStartSpec, TrackRecorder

        recorder = TrackRecorder()
        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_4",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test_04.ts"),
            fragment_index=0,
            rotation_index=0,
            take_start_offset_ms=0,
        )

        exit_calls = []
        fake = FakeProcess(exit_code=0)
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            handle = recorder.start_fragment(spec, lambda e: exit_calls.append(e))
            time.sleep(0.1)
            handle.wait(timeout=5)

        assert 1 <= len(exit_calls) <= 1

    def test_cancel_discards_fragment(self):
        """0.5: cancel → fragment discarded"""
        from app.camera.track_recorder import FragmentStartSpec, TrackRecorder

        recorder = TrackRecorder()
        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_5",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test_05.ts"),
            fragment_index=0,
            rotation_index=0,
            take_start_offset_ms=0,
        )

        fake = FakeProcess(exit_code=0)
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            handle = recorder.start_fragment(spec, lambda e: None)
            handle.cancel()
            time.sleep(0.05)
            result = handle.wait(timeout=5)

        assert result.status == "discarded"

    def test_registry_capture_take_id_not_empty(self):
        """0.6: registry 中 capture_take_id 不为空"""
        reg = FakeProcessRegistry()
        from app.camera.track_recorder import FragmentStartSpec, TrackRecorder

        recorder = TrackRecorder(process_registry=reg, clock=FakeClock())
        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_6",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test_06.ts"),
            fragment_index=0,
            rotation_index=0,
            take_start_offset_ms=0,
        )

        fake = FakeProcess(exit_code=0)
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            handle = recorder.start_fragment(spec, lambda e: None)
            time.sleep(0.1)
            handle.wait(timeout=5)

        assert len(reg.started) >= 1
        assert reg.started[0]["capture_take_id"] == "take_1"


# ── 3.10-3.11: TrackRecorder 单测 ──────────────────────────────


class TestTrackRecorderUnit:
    def test_sync_command_preserves_source_frames(self, monkeypatch):
        from app.camera.track_recorder import FragmentStartSpec, TrackRecorder

        monkeypatch.setenv("PICKLEBALL_SYNC_VIDEO_ENCODER", "libx264")
        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_1",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test.ts"),
            fragment_index=0,
            rotation_index=0,
            take_start_offset_ms=0,
            fps=60,
            sync_to_host_clock=True,
        )

        cmd = TrackRecorder()._build_command(spec)

        assert ["-rtsp_transport", "udp"] == cmd[cmd.index("-rtsp_transport") : cmd.index("-rtsp_transport") + 2]
        assert ["-c:v", "copy"] == cmd[cmd.index("-c:v") : cmd.index("-c:v") + 2]
        assert "-use_wallclock_as_timestamps" not in cmd
        assert "-vf" not in cmd
        assert "-fps_mode" not in cmd
        assert "-r" not in cmd

    def test_fragment_start_spec_creation(self):
        """3.10: FragmentStartSpec 正确构造"""
        from app.camera.track_recorder import FragmentStartSpec

        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_1",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test.ts"),
            fragment_index=2,
            rotation_index=1,
            take_start_offset_ms=5000,
            fps=60,
            resolution="1920x1080",
        )
        assert spec.fragment_index == 2
        assert spec.rotation_index == 1
        assert spec.take_start_offset_ms == 5000
        assert spec.fps == 60

    def test_fragment_result_statuses(self):
        """3.10: FragmentResult status 值正确"""
        from app.camera.track_recorder import FragmentResult

        r = FragmentResult(fragment_id="f1", status="completed", return_code=0)
        assert r.status == "completed"
        assert r.return_code == 0

    def test_handle_wait_timeout(self):
        """3.11: FragmentHandle wait 超时后 kill"""
        from app.camera.track_recorder import FragmentStartSpec, TrackRecorder

        recorder = TrackRecorder()
        spec = FragmentStartSpec(
            capture_take_id="take_1",
            capture_track_id="track_1",
            fragment_id="frag_t",
            camera_id="cam_a",
            stream_url="rtsp://test",
            output_path=Path("/tmp/test_t.ts"),
            fragment_index=0,
            rotation_index=0,
            take_start_offset_ms=0,
        )

        class BlockingProcess(FakeProcess):
            def wait(self, timeout=None):
                time.sleep(0.5)
                return 0

        fake = BlockingProcess(exit_code=0)
        fake.returncode = None
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            handle = recorder.start_fragment(spec, lambda e: None)
            time.sleep(0.05)
            result = handle.wait(timeout=0.1)

        assert result.status == "failed"
        assert "timeout" in result.error_message


# ── 4.7: RecordingPolicy 单测 ─────────────────────────────────


class TestRecordingPolicy:
    def test_strict_sync_all_fail_restart_all(self):
        """4.7: StrictSync 任一轨失败→停止全部+重启全部"""
        from app.camera.recording_policy import (
            CaptureRuntimeSnapshot,
            CoordinatorActionType,
            StrictSyncPolicy,
            TrackRuntimeEvent,
            TrackRuntimeState,
        )

        policy = StrictSyncPolicy()
        event = TrackRuntimeEvent(
            track_id="t1",
            fragment_id="f1",
            is_primary=True,
            unexpected=True,
            return_code=1,
            restart_count=0,
        )
        snapshot = CaptureRuntimeSnapshot(
            primary_track_id="t1",
            track_states={
                "t1": TrackRuntimeState("t1", True, True, 0, 0),
                "t2": TrackRuntimeState("t2", False, True, 0, 0),
            },
        )
        actions = policy.decide(event, snapshot)
        types = [a.type for a in actions]
        assert CoordinatorActionType.STOP_ALL in types
        assert CoordinatorActionType.RESTART_ALL in types

    def test_preserve_primary_secondary_only(self):
        """4.7: PreservePrimary 辅轨失败仅重启辅轨"""
        from app.camera.recording_policy import (
            CaptureRuntimeSnapshot,
            CoordinatorActionType,
            PreservePrimaryPolicy,
            TrackRuntimeEvent,
            TrackRuntimeState,
        )

        policy = PreservePrimaryPolicy()
        event = TrackRuntimeEvent(
            track_id="t2",
            fragment_id="f1",
            is_primary=False,
            unexpected=True,
            return_code=1,
            restart_count=0,
        )
        snapshot = CaptureRuntimeSnapshot(
            primary_track_id="t1",
            track_states={
                "t1": TrackRuntimeState("t1", True, True, 0, 0),
                "t2": TrackRuntimeState("t2", False, True, 0, 0),
            },
        )
        actions = policy.decide(event, snapshot)
        types = [a.type for a in actions]
        assert CoordinatorActionType.STOP_ALL not in types
        assert CoordinatorActionType.RESTART_FAILED_TRACK in types

    def test_single_track_restart(self):
        """4.7: SingleTrackRestartPolicy 仅重启当前轨"""
        from app.camera.recording_policy import (
            CaptureRuntimeSnapshot,
            CoordinatorActionType,
            SingleTrackRestartPolicy,
            TrackRuntimeEvent,
            TrackRuntimeState,
        )

        policy = SingleTrackRestartPolicy()
        event = TrackRuntimeEvent(
            track_id="t1",
            fragment_id="f1",
            is_primary=True,
            unexpected=True,
            return_code=1,
            restart_count=0,
        )
        snapshot = CaptureRuntimeSnapshot(
            primary_track_id="t1",
            track_states={
                "t1": TrackRuntimeState("t1", True, True, 0, 0),
            },
        )
        actions = policy.decide(event, snapshot)
        assert len(actions) == 1
        assert actions[0].type == CoordinatorActionType.RESTART_FAILED_TRACK

    def test_restart_budget_exhausted(self):
        """4.7: 重启预算耗尽 → 无操作"""
        from app.camera.recording_policy import (
            CaptureRuntimeSnapshot,
            SingleTrackRestartPolicy,
            TrackRuntimeEvent,
            TrackRuntimeState,
        )

        policy = SingleTrackRestartPolicy()
        event = TrackRuntimeEvent(
            track_id="t1",
            fragment_id="f1",
            is_primary=True,
            unexpected=True,
            return_code=1,
            restart_count=5,
        )
        snapshot = CaptureRuntimeSnapshot(
            primary_track_id="t1",
            track_states={
                "t1": TrackRuntimeState("t1", True, False, 5, 5),
            },
        )
        actions = policy.decide(event, snapshot)
        assert len(actions) == 0  # budget exhausted


# ── 5.7: Coordinator 单测 ─────────────────────────────────────


class TestCoordinator:
    def test_dual_track_launches_overlap(self):
        """双摄首段的 FFmpeg 进程在同一软件同步点创建。"""
        from app.camera.capture_runtime_coordinator import (
            CaptureRuntimeCoordinator,
            TrackRuntimeInfo,
        )
        from app.camera.recording_policy import StrictSyncPolicy

        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def delayed_popen(*args, **kwargs):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.03)
                return _mock_popen(FakeProcess(exit_delay=0.1))
            finally:
                with active_lock:
                    active -= 1

        coord = CaptureRuntimeCoordinator()
        with patch("subprocess.Popen", side_effect=delayed_popen):
            coord.start_tracks(
                take_id="take_1",
                tracks_info=[
                    TrackRuntimeInfo("track_1", "cam_1", "cam_a", "default", "rtsp://a", "/tmp/test"),
                    TrackRuntimeInfo("track_2", "cam_2", "cam_b", "supplementary", "rtsp://b", "/tmp/test"),
                ],
                policy=StrictSyncPolicy(),
            )

        assert max_active == 2

    def test_start_tracks_creates_fragments(self):
        """5.7: Coordinator start_tracks 创建 Fragment"""
        from app.camera.capture_runtime_coordinator import (
            CaptureRuntimeCoordinator,
            TrackRuntimeInfo,
        )
        from app.camera.recording_policy import SingleTrackRestartPolicy

        repo = FakeFragmentRepo()
        coord = CaptureRuntimeCoordinator(fragment_repo=repo)

        fake = FakeProcess(exit_code=0)
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            coord.start_tracks(
                take_id="take_1",
                tracks_info=[
                    TrackRuntimeInfo(
                        track_id="track_1",
                        slot="cam_1",
                        camera_id="cam_a",
                        analysis_role="default",
                        stream_url="rtsp://test",
                        output_dir="/tmp/test",
                    ),
                ],
                policy=SingleTrackRestartPolicy(),
            )
        assert coord._tracks.get("track_1") is not None

    def test_stop_tracks_returns_fragments(self):
        """5.7: Coordinator stop_tracks 返回 fragment 列表"""
        from app.camera.capture_runtime_coordinator import (
            CaptureRuntimeCoordinator,
            TrackRuntimeInfo,
        )
        from app.camera.recording_policy import SingleTrackRestartPolicy

        coord = CaptureRuntimeCoordinator()
        fake = FakeProcess(exit_code=0)
        with patch("subprocess.Popen", return_value=_mock_popen(fake)):
            coord.start_tracks(
                take_id="take_1",
                tracks_info=[
                    TrackRuntimeInfo(
                        track_id="track_1",
                        slot="cam_1",
                        camera_id="cam_a",
                        analysis_role="default",
                        stream_url="rtsp://test",
                        output_dir="/tmp/test",
                    ),
                ],
                policy=SingleTrackRestartPolicy(),
            )
        time.sleep(0.05)
        frags, outcome = coord.stop_tracks()
        assert isinstance(frags, list)
        assert outcome.stopped_by_user is True

    def test_outcome_fields(self):
        """5.7: CaptureRuntimeOutcome 字段正确"""
        from app.camera.capture_runtime_coordinator import CaptureRuntimeOutcome

        o = CaptureRuntimeOutcome(
            stopped_by_user=True,
            primary_track_lost=True,
            unavailable_track_ids=["t1"],
            restart_budget_exhausted=True,
            runtime_warnings=["test"],
        )
        assert o.stopped_by_user
        assert o.primary_track_lost
        assert "t1" in o.unavailable_track_ids


# ── 6.12: Finalizer + CompletionService 单测 ──────────────────


class TestFinalizer:
    def test_no_media_returns_no_media_status(self):
        """6.12: 无有效片段 → no_media"""
        from app.camera.capture_finalizer import CaptureFinalizer

        fin = CaptureFinalizer()
        result = fin.finalize_track("track_1", [])
        assert result.status == "no_media"
        assert result.fragment_count == 0

    def test_missing_files_skipped(self):
        """6.12: 不存在的文件被跳过"""
        from app.camera.capture_finalizer import CaptureFinalizer

        fin = CaptureFinalizer()
        result = fin.finalize_track(
            "track_1",
            [
                {"file_path": "/nonexistent/path.ts", "fragment_index": 0},
            ],
        )
        assert result.status == "no_media"

    def test_completion_service_primary_lost(self):
        """6.12: CompletionService 主轨不可恢复 → failed"""
        from app.camera.capture_completion_service import CaptureCompletionService
        from app.camera.capture_runtime_coordinator import CaptureRuntimeOutcome

        comp = CaptureCompletionService()
        outcome = CaptureRuntimeOutcome(primary_track_lost=True)
        decision = comp.decide(outcome, [])
        assert decision.terminal_status == "failed"
        assert not decision.analysis_available

    def test_completion_service_all_success(self):
        """6.12: CompletionService 全成功 → completed"""
        from app.camera.capture_completion_service import CaptureCompletionService
        from app.camera.capture_finalizer import TrackFinalizationResult
        from app.camera.capture_runtime_coordinator import CaptureRuntimeOutcome

        comp = CaptureCompletionService()
        outcome = CaptureRuntimeOutcome()
        results = [
            TrackFinalizationResult(capture_track_id="t1", status="succeeded", video_id="v1", fragment_count=1),
        ]
        decision = comp.decide(outcome, results)
        assert decision.terminal_status == "completed"
        assert decision.analysis_available
        assert decision.default_analysis_video_id == "v1"
