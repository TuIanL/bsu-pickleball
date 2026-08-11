"""Low-latency, recording-independent live overlay runtime."""

from __future__ import annotations

import os
import queue
import threading
import time
import uuid
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import cv2
from pydantic import BaseModel, Field

from app.camera.camera_registry import camera_registry
from app.camera.preview_service import _build_auth_stream_url
from app.vision.detectors.ball_adapter import YoloBallDetectorAdapter
from app.vision.pickleball_game_analysis.ball_tracker import BallTracker
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import PersonDetector


class ShowcaseCameraStatus(BaseModel):
    slot: str
    camera_id: str
    connection_status: str = "starting"
    last_frame_at: datetime | None = None
    actual_inference_fps: float = 0.0
    actual_output_fps: float = 0.0
    latency_ms: float | None = None
    track_count: int = 0
    person_status: str = "starting"
    ball_status: str = "disabled"
    degradation_reason: str | None = None
    frame_sequence: int = 0


class ShowcaseRuntimeStatus(BaseModel):
    runtime_id: str
    capture_take_id: str
    field_session_id: str | None = None
    status: str = "starting"
    recording_status: str = "recording"
    target_inference_fps: float
    processing_width: int
    jpeg_quality: int
    ball_enabled: bool
    cameras: dict[str, ShowcaseCameraStatus] = Field(default_factory=dict)
    degradation_reasons: list[str] = Field(default_factory=list)
    started_at: datetime
    stopped_at: datetime | None = None


@dataclass
class _Frame:
    image: Any
    captured_mono: float


class _LatestFrameQueue:
    """A one-element queue that always keeps the newest frame."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_Frame] = queue.Queue(maxsize=1)

    def put_latest(self, frame: _Frame) -> None:
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(frame)
            except queue.Full:
                pass

    def get(self, timeout: float) -> _Frame | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


def _rate(times: deque[float]) -> float:
    if len(times) < 2:
        return 0.0
    elapsed = times[-1] - times[0]
    return round((len(times) - 1) / elapsed, 2) if elapsed > 0 else 0.0


class _CameraWorker:
    def __init__(self, *, runtime_id: str, slot: str, camera_id: str, camera: Any, target_fps: float, width: int, quality: int, ball_enabled: bool, ball_model_path: str | None) -> None:
        self.runtime_id = runtime_id
        self.slot = slot
        self.camera_id = camera_id
        self.camera = camera
        self.target_fps = max(0.5, target_fps)
        self.width = max(320, width)
        self.quality = min(95, max(40, quality))
        self.ball_enabled = ball_enabled
        self.queue = _LatestFrameQueue()
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.jpeg: bytes | None = None
        self._capture = None
        self.sequence = 0
        self.status = ShowcaseCameraStatus(slot=slot, camera_id=camera_id)
        self._inference_times: deque[float] = deque(maxlen=30)
        self._output_times: deque[float] = deque(maxlen=30)
        self._person_detector = PersonDetector(model_path=os.getenv("PICKLEBALL_SHOWCASE_PERSON_MODEL_PATH", "yolov8n.pt"), conf_threshold=float(os.getenv("PICKLEBALL_SHOWCASE_PERSON_CONF", "0.25")))
        self._tracker = MultiObjectTracker(max_lost=8)
        self._ball_tracker: BallTracker | None = None
        if ball_enabled:
            try:
                self._ball_tracker = BallTracker(YoloBallDetectorAdapter(model_path=ball_model_path))
                self.status.ball_status = "starting"
            except Exception as exc:
                self._set_status(ball_status="unavailable", degradation_reason=f"球检测初始化失败: {exc}")
        self.reader_thread = threading.Thread(target=self._read_loop, name=f"showcase-reader-{slot}", daemon=True)
        self.worker_thread = threading.Thread(target=self._process_loop, name=f"showcase-worker-{slot}", daemon=True)

    def _set_status(self, **updates: Any) -> None:
        self.status = self.status.model_copy(update=updates)

    def start(self) -> None:
        self.reader_thread.start()
        self.worker_thread.start()

    def stop(self, timeout: float = 3.0) -> bool:
        self.stop_event.set()
        if self._capture is not None:
            self._capture.release()
        with self.condition:
            self.condition.notify_all()
        self.reader_thread.join(timeout=timeout)
        self.worker_thread.join(timeout=timeout)
        return not self.reader_thread.is_alive() and not self.worker_thread.is_alive()

    def _read_loop(self) -> None:
        cap = None
        try:
            url = _build_auth_stream_url(self.camera.stream_url, self.camera.protocol, self.camera.username, self.camera.password)
            cap = cv2.VideoCapture(url)
            self._capture = cap
            if not cap.isOpened():
                self._set_status(connection_status="unavailable", person_status="unavailable", degradation_reason="无法打开摄像头流")
                return
            self._set_status(connection_status="connected")
            while not self.stop_event.is_set():
                ret, image = cap.read()
                if not ret:
                    self._set_status(connection_status="unavailable", degradation_reason="摄像头流读取失败")
                    return
                self.queue.put_latest(_Frame(image=image, captured_mono=time.monotonic()))
        except Exception as exc:
            self._set_status(connection_status="failed", person_status="unavailable", degradation_reason=f"摄像头 reader 失败: {exc}")
        finally:
            if cap is not None:
                cap.release()
            self._capture = None

    def _process_loop(self) -> None:
        interval = 1.0 / self.target_fps
        frame_index = 0
        last_process = 0.0
        while not self.stop_event.is_set():
            item = self.queue.get(timeout=0.25)
            if item is None:
                continue
            now = time.monotonic()
            if now - last_process < interval:
                continue
            last_process = now
            frame_index += 1
            try:
                output = self._process_frame(item.image, frame_index)
                ok, encoded = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                if not ok:
                    raise RuntimeError("JPEG 编码失败")
                now = time.monotonic()
                self._inference_times.append(now)
                self._output_times.append(now)
                self.sequence += 1
                self._set_status(last_frame_at=datetime.now(UTC), actual_inference_fps=_rate(self._inference_times), actual_output_fps=_rate(self._output_times), latency_ms=round((now - item.captured_mono) * 1000, 1), frame_sequence=self.sequence)
                with self.condition:
                    self.jpeg = encoded.tobytes()
                    self.condition.notify_all()
            except Exception as exc:
                self._set_status(person_status="unavailable", degradation_reason=f"人体叠加不可用: {exc}")
                ok, encoded = cv2.imencode(".jpg", item.image, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                if ok:
                    now = time.monotonic()
                    self._output_times.append(now)
                    self.sequence += 1
                    self._set_status(last_frame_at=datetime.now(UTC), actual_output_fps=_rate(self._output_times), latency_ms=round((now - item.captured_mono) * 1000, 1), frame_sequence=self.sequence)
                    with self.condition:
                        self.jpeg = encoded.tobytes()
                        self.condition.notify_all()

    def _process_frame(self, frame: Any, frame_index: int) -> Any:
        height, width = frame.shape[:2]
        scale = 1.0
        processed = frame
        if width > self.width:
            scale = self.width / float(width)
            processed = cv2.resize(frame, (self.width, max(1, int(height * scale))))
        detections = self._person_detector.detect(processed)
        tracks = self._tracker.update(detections)
        self._set_status(person_status="available", track_count=len(tracks))
        for track in tracks:
            x1, y1, x2, y2 = [int(max(0, value / scale)) for value in track.bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (44, 220, 120), 2)
            cv2.putText(frame, f"P{track.track_id} {track.confidence:.2f}", (x1, max(18, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (44, 220, 120), 2)
        if self._ball_tracker is not None:
            try:
                sample = self._ball_tracker.update(processed, frame_index, frame_index / self.target_fps)
                if sample.accepted and sample.image_xy:
                    x, y = int(sample.image_xy[0] / scale), int(sample.image_xy[1] / scale)
                    cv2.circle(frame, (x, y), 7, (40, 180, 255), -1)
                    for previous in list(self._ball_tracker.trajectory)[-12:-1]:
                        px, py = int(previous[0] / scale), int(previous[1] / scale)
                        cv2.circle(frame, (px, py), 3, (40, 180, 255), -1)
                    self._set_status(ball_status="available")
                else:
                    self._set_status(ball_status="no_detections")
            except Exception as exc:
                self._set_status(ball_status="unavailable", degradation_reason=f"球检测不可用: {exc}")
        return frame

    def stream(self) -> Iterator[bytes]:
        sequence = 0
        while not self.stop_event.is_set():
            with self.condition:
                self.condition.wait_for(lambda: self.sequence > sequence or self.stop_event.is_set(), timeout=1.0)
                if self.stop_event.is_set():
                    return
                if self.sequence <= sequence or self.jpeg is None:
                    continue
                sequence = self.sequence
                payload = self.jpeg
            yield payload


class ShowcaseRuntime:
    def __init__(self, *, runtime_id: str, capture_take_id: str, field_session_id: str | None, slots: dict[str, Any]) -> None:
        self.runtime_id = runtime_id
        self.capture_take_id = capture_take_id
        self.field_session_id = field_session_id
        self.started_at = datetime.now(UTC)
        self.status = "starting"
        self.recording_status = "recording"
        self.target_fps = float(os.getenv("PICKLEBALL_SHOWCASE_INFERENCE_FPS", "8"))
        self.processing_width = int(os.getenv("PICKLEBALL_SHOWCASE_PROCESSING_WIDTH", "960"))
        self.jpeg_quality = int(os.getenv("PICKLEBALL_SHOWCASE_JPEG_QUALITY", "78"))
        self.ball_enabled = os.getenv("PICKLEBALL_SHOWCASE_BALL_ENABLED", "0").lower() in {"1", "true", "yes"}
        ball_path = os.getenv("PICKLEBALL_BALL_MODEL_PATH")
        self.workers: dict[str, _CameraWorker] = {}
        for slot in ("cam_1", "cam_2"):
            config = slots.get(slot)
            camera_id = getattr(config, "camera_id", None) if config is not None else None
            if camera_id is None and isinstance(config, dict):
                camera_id = config.get("camera_id")
            camera = camera_registry.get(camera_id) if camera_id else None
            if camera is not None:
                self.workers[slot] = _CameraWorker(runtime_id=runtime_id, slot=slot, camera_id=camera_id, camera=camera, target_fps=self.target_fps, width=self.processing_width, quality=self.jpeg_quality, ball_enabled=self.ball_enabled, ball_model_path=ball_path)

    def start(self) -> None:
        for worker in self.workers.values():
            worker.start()
        self.status = "running" if self.workers else "degraded"

    def stop(self, timeout: float = 3.0) -> bool:
        results = [worker.stop(timeout) for worker in self.workers.values()]
        self.status = "stopped"
        return all(results)

    def snapshot(self) -> ShowcaseRuntimeStatus:
        return ShowcaseRuntimeStatus(runtime_id=self.runtime_id, capture_take_id=self.capture_take_id, field_session_id=self.field_session_id, status=self.status, recording_status=self.recording_status, target_inference_fps=self.target_fps, processing_width=self.processing_width, jpeg_quality=self.jpeg_quality, ball_enabled=self.ball_enabled, cameras={slot: worker.status for slot, worker in self.workers.items()}, degradation_reasons=[worker.status.degradation_reason for worker in self.workers.values() if worker.status.degradation_reason], started_at=self.started_at)

    def stream(self, slot: str) -> Iterator[bytes] | None:
        worker = self.workers.get(slot)
        return worker.stream() if worker else None


class ShowcaseRuntimeManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runtimes: dict[str, ShowcaseRuntime] = {}
        self._by_take: dict[str, str] = {}

    def start_for_session(self, session: Any) -> ShowcaseRuntime:
        take_id = getattr(session, "capture_take_id", None)
        if not take_id:
            raise ValueError("展示旁路需要 CaptureTake")
        with self._lock:
            existing = self._runtimes.get(self._by_take.get(take_id, ""))
            if existing:
                return existing
            runtime = ShowcaseRuntime(runtime_id=f"showcase_{uuid.uuid4().hex[:12]}", capture_take_id=take_id, field_session_id=getattr(session, "field_session_id", None), slots=getattr(session, "camera_slots", {}))
            runtime.start()
            self._runtimes[runtime.runtime_id] = runtime
            self._by_take[take_id] = runtime.runtime_id
            return runtime

    def get(self, runtime_id: str) -> ShowcaseRuntime | None:
        with self._lock:
            return self._runtimes.get(runtime_id)

    def stop_for_session(self, session: Any, timeout: float = 3.0) -> bool:
        take_id = getattr(session, "capture_take_id", None)
        with self._lock:
            runtime_id = self._by_take.pop(take_id, None) if take_id else None
            runtime = self._runtimes.pop(runtime_id, None) if runtime_id else None
        return runtime.stop(timeout) if runtime else True


showcase_runtime_manager = ShowcaseRuntimeManager()
