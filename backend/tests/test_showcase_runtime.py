from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np

import app.services.showcase_runtime as runtime_module
from app.services.showcase_runtime import _CameraWorker, _Frame, _LatestFrameQueue, _rate


def test_latest_frame_queue_drops_stale_item():
    queue = _LatestFrameQueue()
    queue.put_latest(_Frame(image="old", captured_mono=0.0))
    queue.put_latest(_Frame(image="new", captured_mono=1.0))
    item = queue.get(0.01)
    assert item is not None
    assert item.image == "new"


def test_rate_reports_measured_rate_not_target_rate():
    assert _rate(deque([1.0, 1.5, 2.0])) == 2.0
    assert _rate(deque([1.0])) == 0.0


def test_worker_publishes_frames_and_releases_capture(monkeypatch):
    class FakeCapture:
        def __init__(self):
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            return (not self.released, np.zeros((32, 48, 3), dtype=np.uint8))

        def release(self):
            self.released = True

    capture = FakeCapture()
    monkeypatch.setattr(runtime_module.cv2, "VideoCapture", lambda _: capture)
    camera = SimpleNamespace(stream_url="fake", protocol="rtsp", username=None, password=None)
    worker = _CameraWorker(runtime_id="rt", slot="cam_1", camera_id="c1", camera=camera, target_fps=30, width=48, quality=70, ball_enabled=False, ball_model_path=None)
    monkeypatch.setattr(worker._person_detector, "detect", lambda frame: [])
    worker.start()
    deadline = 100
    while worker.sequence == 0 and deadline > 0:
        deadline -= 1
        import time
        time.sleep(0.01)
    assert worker.sequence > 0
    frame = next(worker.stream())
    assert frame.startswith(b"\xff\xd8")
    assert worker.stop()
    assert capture.released
    assert worker.stop()


def test_model_failure_still_publishes_raw_fallback(monkeypatch):
    class FakeCapture:
        def isOpened(self): return True
        def read(self): return (True, np.zeros((32, 48, 3), dtype=np.uint8))
        def release(self): pass

    monkeypatch.setattr(runtime_module.cv2, "VideoCapture", lambda _: FakeCapture())
    camera = SimpleNamespace(stream_url="fake", protocol="rtsp", username=None, password=None)
    worker = _CameraWorker(runtime_id="rt", slot="cam_1", camera_id="c1", camera=camera, target_fps=30, width=48, quality=70, ball_enabled=False, ball_model_path=None)
    monkeypatch.setattr(worker._person_detector, "detect", lambda frame: (_ for _ in ()).throw(RuntimeError("model missing")))
    worker.start()
    import time
    time.sleep(0.08)
    assert worker.sequence > 0
    assert worker.status.person_status == "unavailable"
    assert worker.stop()


def test_camera_stream_failure_isolated_to_one_slot(monkeypatch):
    class OfflineCapture:
        def isOpened(self):
            return True

        def read(self):
            return (False, None)

        def release(self):
            pass

    class OnlineCapture:
        def __init__(self):
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            return (not self.released, np.zeros((32, 48, 3), dtype=np.uint8))

        def release(self):
            self.released = True

    captures = {"offline": OfflineCapture(), "online": OnlineCapture()}
    monkeypatch.setattr(runtime_module.cv2, "VideoCapture", lambda url: captures[url])
    camera = lambda url: SimpleNamespace(stream_url=url, protocol="rtsp", username=None, password=None)
    offline = _CameraWorker(runtime_id="rt", slot="cam_1", camera_id="c1", camera=camera("offline"), target_fps=30, width=320, quality=70, ball_enabled=False, ball_model_path=None)
    online = _CameraWorker(runtime_id="rt", slot="cam_2", camera_id="c2", camera=camera("online"), target_fps=30, width=320, quality=70, ball_enabled=False, ball_model_path=None)
    monkeypatch.setattr(online._person_detector, "detect", lambda frame: [])

    offline.start()
    online.start()
    import time
    deadline = time.monotonic() + 1
    while online.sequence == 0 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert offline.status.connection_status == "unavailable"
    assert online.status.connection_status == "connected"
    assert online.sequence > 0
    assert offline.stop()
    assert online.stop()


def test_showcase_session_snapshot_round_trip_preserves_runtime_reference():
    from app.camera.models import CameraSlotConfig, SyncRecordingSession

    session = SyncRecordingSession(
        session_id="sync_showcase_restore",
        status="recording",
        capture_take_id="take_showcase_restore",
        field_session_id="field-1",
        camera_slots={
            "cam_1": CameraSlotConfig(role="cam_1", camera_id="camera-a"),
            "cam_2": CameraSlotConfig(role="cam_2", camera_id="camera-b"),
        },
        display_mode="showcase",
        showcase_runtime_id="showcase-runtime-1",
        started_at=datetime.now(UTC),
    )

    restored = type(session).model_validate_json(session.model_dump_json())
    assert restored.display_mode == "showcase"
    assert restored.capture_take_id == "take_showcase_restore"
    assert restored.showcase_runtime_id == "showcase-runtime-1"


def test_showcase_start_failure_keeps_recording_and_exposes_degradation(monkeypatch):
    from app.camera.models import SyncRecordingSession
    from app.camera.sync_recorder_service import SyncRecordingService

    session = SyncRecordingSession(
        session_id="sync_showcase_start_failure",
        status="recording",
        capture_take_id="take-showcase-start-failure",
        display_mode="showcase",
    )

    def fail_start(_session):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(runtime_module.showcase_runtime_manager, "start_for_session", fail_start)
    updated = SyncRecordingService._start_showcase_runtime(session)

    assert updated.status == "recording"
    assert updated.showcase_runtime_id is None
    assert "展示旁路不可用" in (updated.error_message or "")


def test_showcase_stop_timeout_is_non_blocking(monkeypatch):
    from app.camera.models import SyncRecordingSession
    from app.camera.sync_recorder_service import SyncRecordingService

    session = SyncRecordingSession(
        session_id="sync_showcase_stop_timeout",
        status="recording",
        capture_take_id="take-showcase-stop-timeout",
        display_mode="showcase",
    )
    calls = []

    monkeypatch.setattr(
        runtime_module.showcase_runtime_manager,
        "stop_for_session",
        lambda current, timeout: calls.append((current.session_id, timeout)) or False,
    )
    SyncRecordingService._stop_showcase_runtime(session)

    assert calls == [("sync_showcase_stop_timeout", 3.0)]


def test_fixed_video_dual_camera_smoke_reports_measured_metrics(tmp_path, monkeypatch):
    """Run both workers against deterministic local videos without camera hardware."""
    import time

    videos = []
    for index in range(2):
        path = tmp_path / f"showcase_cam_{index}.avi"
        writer = runtime_module.cv2.VideoWriter(
            str(path),
            runtime_module.cv2.VideoWriter_fourcc(*"MJPG"),
            10,
            (64, 48),
        )
        assert writer.isOpened()
        for frame_index in range(12):
            frame = np.zeros((48, 64, 3), dtype=np.uint8)
            frame[:, :, index] = 40 + frame_index
            writer.write(frame)
        writer.release()
        videos.append(path)

    original_capture = runtime_module.cv2.VideoCapture

    class RealtimeVideoCapture:
        def __init__(self, url):
            self.capture = original_capture(url)

        def isOpened(self):
            return self.capture.isOpened()

        def read(self):
            time.sleep(0.11)
            return self.capture.read()

        def release(self):
            self.capture.release()

    monkeypatch.setattr(runtime_module.cv2, "VideoCapture", RealtimeVideoCapture)
    workers = []
    for index, path in enumerate(videos):
        camera = SimpleNamespace(stream_url=str(path), protocol="http", username=None, password=None)
        worker = _CameraWorker(runtime_id="fixed-video", slot=f"cam_{index + 1}", camera_id=f"fixed-{index}", camera=camera, target_fps=10, width=320, quality=70, ball_enabled=False, ball_model_path=None)
        monkeypatch.setattr(worker._person_detector, "detect", lambda frame: [])
        workers.append(worker)
        worker.start()

    deadline = time.monotonic() + 2
    while any(worker.sequence < 2 for worker in workers) and time.monotonic() < deadline:
        time.sleep(0.01)

    try:
        assert all(worker.sequence >= 2 for worker in workers)
        for worker in workers:
            assert worker.status.actual_output_fps > 0
            assert worker.status.latency_ms is not None
            assert next(worker.stream()).startswith(b"\xff\xd8")
    finally:
        for worker in workers:
            assert worker.stop()


def test_ball_detection_available_and_unavailable_states(monkeypatch):
    class FakeBallTracker:
        trajectory = [(8.0, 8.0), (9.0, 9.0)]

        def __init__(self, _adapter):
            pass

        def update(self, _frame, _frame_index, _timestamp):
            return SimpleNamespace(accepted=True, image_xy=(12.0, 14.0))

    monkeypatch.setattr(runtime_module, "BallTracker", FakeBallTracker)
    camera = SimpleNamespace(stream_url="fake", protocol="rtsp", username=None, password=None)
    available = _CameraWorker(runtime_id="rt", slot="cam_1", camera_id="c1", camera=camera, target_fps=8, width=320, quality=70, ball_enabled=True, ball_model_path=None)
    monkeypatch.setattr(available._person_detector, "detect", lambda frame: [])
    available._process_frame(np.zeros((48, 64, 3), dtype=np.uint8), 1)
    assert available.status.ball_status == "available"

    class FailingBallTracker(FakeBallTracker):
        def update(self, _frame, _frame_index, _timestamp):
            raise RuntimeError("ball model unavailable")

    monkeypatch.setattr(runtime_module, "BallTracker", FailingBallTracker)
    unavailable = _CameraWorker(runtime_id="rt", slot="cam_2", camera_id="c2", camera=camera, target_fps=8, width=320, quality=70, ball_enabled=True, ball_model_path=None)
    monkeypatch.setattr(unavailable._person_detector, "detect", lambda frame: [])
    unavailable._process_frame(np.zeros((48, 64, 3), dtype=np.uint8), 1)
    assert unavailable.status.ball_status == "unavailable"
    assert "球检测不可用" in (unavailable.status.degradation_reason or "")


def test_showcase_default_runtime_configuration_is_explicit(monkeypatch):
    for key in (
        "PICKLEBALL_SHOWCASE_INFERENCE_FPS",
        "PICKLEBALL_SHOWCASE_PROCESSING_WIDTH",
        "PICKLEBALL_SHOWCASE_JPEG_QUALITY",
        "PICKLEBALL_SHOWCASE_BALL_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)

    runtime = runtime_module.ShowcaseRuntime(runtime_id="rt", capture_take_id="take", field_session_id=None, slots={})
    assert runtime.target_fps == 8
    assert runtime.processing_width == 960
    assert runtime.jpeg_quality == 78
    assert runtime.ball_enabled is False
