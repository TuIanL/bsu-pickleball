from pathlib import Path
import numpy as np
import pytest

from app.schemas.pose import PoseOverlayFrame, PoseSubject
from app.services.joint_pose_artifacts import build_joint_pose_artifact


class Capture:
    def __init__(self, path):
        self.index = 0
        self.released = False

    def isOpened(self):
        return True

    def set(self, _, index):
        self.index = index

    def grab(self):
        self.index += 1
        return True

    def read(self):
        image = np.full((100, 100, 3), self.index, dtype=np.uint8)
        self.index += 1
        return True, image

    def release(self):
        self.released = True


def player(pid="Player_1", evidence="base_observed", bbox=None):
    return {"player_id": pid, "evidence_type": evidence, "bbox": bbox or [10, 10, 50, 90]}


def view(index, players):
    return {"source": {"width": 100, "height": 100}, "frames": [
        {"frame_index": index, "timestamp_seconds": 30., "players": players},
    ]}


class Estimator:
    def __init__(self):
        self.calls = []

    def estimate_frame(self, image, subjects, frame_index, timestamp_seconds):
        self.calls.append((int(image[0, 0, 0]), subjects, timestamp_seconds))
        return PoseOverlayFrame(frame_index=frame_index, timestamp_seconds=timestamp_seconds, subjects=[
            PoseSubject(track_id=s.track_id, bbox=s.bbox, confidence=s.confidence) for s in subjects
        ])


def build(views, estimator=None, **kwargs):
    return build_joint_pose_artifact(
        job_id="j", reference_view_id="cam_1", fused_overlay={"views": views},
        video_paths={k: Path(k) for k in views}, video_ids={k: k for k in views},
        estimator=estimator or Estimator(), sample_stride=1, capture_factory=Capture, **kwargs,
    )


def test_pose_uses_each_views_source_frame_with_shared_canonical_time_and_identity():
    estimator = Estimator()
    artifact = build({"cam_1": view(10, [player()]), "cam_2": view(8, [player()])}, estimator)
    assert [c[0] for c in estimator.calls] == [10, 8]
    assert [c[2] for c in estimator.calls] == [30., 30.]
    assert [c[1][0].track_id for c in estimator.calls] == ["cam_1:Player_1", "cam_2:Player_1"]
    assert artifact["frames"][0]["subjects"][0]["track_id"] == "Player_1"
    assert artifact["views"]["cam_2"]["frames"][0]["frame_index"] == 8
    assert artifact["views"]["cam_2"]["frames"][0]["subjects"][0]["track_id"] == "Player_1"


@pytest.mark.parametrize("evidence,pid", [
    ("cross_view_projected", "Player_1"), ("predicted_only", "Player_1"),
    ("bootstrap_backfill", "Player_1"), ("base_observed", "global_player_1"),
])
def test_pose_rejects_nonobserved_or_unconfirmed_identity(evidence, pid):
    estimator = Estimator()
    artifact = build({"cam_1": view(10, [player(pid, evidence)])}, estimator)
    assert not estimator.calls
    assert artifact["status"] == "no_poses"
    assert artifact["frames"][0]["subjects"] == []


def test_duplicate_identity_is_not_silently_chosen_for_pose():
    estimator = Estimator()
    artifact = build({"cam_1": view(10, [player(), player(bbox=[50, 10, 90, 90])])}, estimator)
    assert not estimator.calls
    assert artifact["timing_provenance"]["counters"]["duplicate_identity_rejected"] == 2


def test_pose_clips_actual_image_bounds_and_keeps_empty_frames_after_decode_failure():
    estimator = Estimator()
    artifact = build({"cam_1": view(10, [player(bbox=[-5, 10, 150, 90])])}, estimator)
    assert estimator.calls[0][1][0].bbox == [0, 10, 100, 90]

    capture = Capture("x")
    capture.read = lambda: (False, None)
    artifact = build_joint_pose_artifact(
        job_id="j", reference_view_id="cam_1", fused_overlay={"views": {"cam_1": view(10, [player()])}},
        video_paths={"cam_1": Path("x")}, video_ids={}, estimator=estimator,
        capture_factory=lambda _: capture,
    )
    assert artifact["frames"][0]["subjects"] == []
    assert capture.released


def test_pose_cancellation_releases_source_and_is_not_success():
    capture = Capture("x")
    def cancel():
        raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        build_joint_pose_artifact(
            job_id="j", reference_view_id="cam_1", fused_overlay={"views": {"cam_1": view(10, [player()])}},
            video_paths={"cam_1": Path("x")}, video_ids={}, estimator=Estimator(),
            capture_factory=lambda _: capture, cancellation_check=cancel,
        )
    assert capture.released
