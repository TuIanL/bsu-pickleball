"""Future RTMPose26 adapter.

Expected normalization:
- keypoint names should be stable, human-readable strings
- coordinates remain in frame pixel space before court mapping
- downstream features can derive center of mass, knee/hip angles, shoulder-hip
  separation, preparation timing, and recovery posture

The lightweight backend deliberately does not import mmpose/mmcv here.
"""

from app.vision.pose.base import PoseResult


class RTMPose26Adapter:
    def __init__(self, config_path: str, checkpoint_path: str) -> None:
        self.config_path = config_path
        self.checkpoint_path = checkpoint_path

    def estimate(self, frame_path: str, subject_boxes: list[tuple[float, float, float, float]]) -> list[PoseResult]:
        raise NotImplementedError(
            "RTMPose26 integration is reserved for the real vision phase; "
            f"would run {self.checkpoint_path} on {frame_path}."
        )
