"""ReferenceRichAnalysisContext —— cam_1 `full` scope 富分析(design D8)。

消费**同一次 reference frame decode** 的 `ViewFrameResult` 运行 pose / ball / debug,
不二次调用 `AnalysisPipeline.run()`(否则 cam_1 视频会解码第二遍、local tracking 重跑)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.vision.multiview.joint_view_runtime import JointViewRuntime


@dataclass
class ReferenceRichAnalysisContext:
    """某一 reference 帧的富分析上下文(cam_1 full scope)。"""

    runtime: JointViewRuntime
    frame: Any
    frame_index: int
    timestamp_s: float
    view_result: Any  # ViewFrameResult
    pose_frames: list[Any] = field(default_factory=list)
    pose_error: str | None = None
    ball_samples: list[Any] = field(default_factory=list)
    ball_ctx_error: str | None = None

    def run_pose(self, pose_estimator: Any | None) -> None:
        """在**同一帧**上运行姿态估计(不重新解码)。"""
        if pose_estimator is None or not self.view_result.frame_detections:
            return
        try:
            pose_frame = pose_estimator.estimate_frame(
                frame=self.frame,
                subjects=self.view_result.frame_detections,
                frame_index=self.frame_index,
                timestamp_seconds=self.timestamp_s,
            )
            pose_frame.subjects = [s for s in pose_frame.subjects if s.keypoints]
            if pose_frame.subjects:
                self.pose_frames.append(pose_frame)
        except Exception as exc:  # noqa: BLE001
            self.pose_error = str(exc)

    def run_ball(
        self,
        ball_ctx: Any | None,
        *,
        homography: list[list[float]],
        frame_width: int,
        frame_height: int,
    ) -> None:
        """在**同一帧**上运行球检测(消费 session 的 player_motion_pixels)。"""
        if ball_ctx is None or getattr(ball_ctx, "tracker", None) is None:
            return
        try:
            ball_sample = ball_ctx.tracker.update(
                frame=self.frame,
                frame_index=self.frame_index,
                timestamp_sec=self.timestamp_s,
                roi_corners=None,
                homography=homography,
                player_motion_pixels=self.view_result.player_motion_pixels,
            )
            self.ball_samples.append(ball_sample)
        except Exception as exc:  # noqa: BLE001
            self.ball_ctx_error = f"球检测运行时失败: {exc}"
            ball_ctx.tracker = None

    # 供 cam_1 full scope 的 debug / serve / action helpers 扩展挂载点
    def debug_signature(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "position_sample_count": len(self.view_result.frame_positions),
            "pose_subject_count": sum(len(f.subjects) for f in self.pose_frames),
        }
