from pathlib import Path
from types import SimpleNamespace

from app.services.joint_ball_2d_artifacts import build_joint_ball_2d_artifact
from test_joint_pose_artifacts import Capture


def test_ball_2d_keeps_view_clock_identity_and_does_not_publish_predictions():
    calls = []
    trackers = []
    class Tracker:
        def __init__(self, view):
            self.view = view
            self.calls = 0
            trackers.append(self)

        def update(self, image, *, frame_index, timestamp_sec):
            calls.append((self.view, int(image[0, 0, 0]), frame_index, timestamp_sec))
            self.calls += 1
            return SimpleNamespace(
                accepted=self.calls == 1, publication_eligible=True,
                image_xy=(20, 30) if self.calls == 1 else None,
                predicted_position=(25, 35),
                confidence=.8, visible=self.calls == 1, candidate_count=int(self.calls == 1),
                source="detector", reject_reason=None, quality_status="accepted",
            )
    views = {k: {"source": {"width": 100, "height": 100}, "frames": [
        {"frame_index": i, "timestamp_seconds": 30.},
        {"frame_index": i + 2, "timestamp_seconds": 30.033333},
    ]} for k, i in [("cam_1", 10), ("cam_2", 8)]}
    artifact = build_joint_ball_2d_artifact(
        job_id="j", reference_view_id="cam_1", timing_overlay={"views": views},
        video_paths={k: Path(k) for k in views}, tracker_factory=Tracker, capture_factory=Capture,
    )
    assert calls == [("cam_1", 10, 10, 30.), ("cam_1", 12, 12, 30.033333),
                     ("cam_2", 8, 8, 30.), ("cam_2", 10, 10, 30.033333)]
    assert len(trackers) == 2
    assert artifact["samples"][0]["image_xy"] == [20, 30]
    assert artifact["samples"][1]["image_xy"] is None
    assert not artifact["samples"][1]["accepted"]
    assert artifact["views"]["cam_2"]["samples"][1]["image_xy"] is None


def test_ball_tentative_points_and_pre_window_context_are_not_real_detections():
    tracker = SimpleNamespace(update=lambda *a, **kw: SimpleNamespace(
        accepted=True, publication_eligible=False, image_xy=(20, 30),
        confidence=.9, visible=True, candidate_count=1, source="detector", reject_reason=None,
        quality_status="diagnostic_only",
    ))
    artifact = build_joint_ball_2d_artifact(
        job_id="j", reference_view_id="cam_1", video_paths={"cam_1": Path("x")},
        timing_overlay={"views": {"cam_1": {"frames": [{"frame_index": 10, "timestamp_seconds": 29.} ]}}},
        tracker_factory=lambda _: tracker, capture_factory=Capture, publish_start_seconds=30.,
    )
    assert artifact["status"] == "no_detections"
    assert artifact["samples"][0]["image_xy"] is None
