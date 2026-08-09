"""JointViewRuntime —— joint_tracking_v2 单视角运行上下文(design D8)。

CanonicalAnalysisClock 只告诉 runtime 下一 `source_frame_index`;runtime 负责解帧、
`session.step`、per-view 诊断。`MultiViewJointRun` 持有两个 runtime(cam1 full / cam2 perception)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from app.vision.multiview.joint_types import JointViewInput
from app.vision.player_tracking_engine.view_tracking_session import ViewTrackingSession, ViewFrameResult

ViewScope = Literal["full", "perception"]


@dataclass
class JointViewRuntime:
    """单视角运行上下文:输入 + 帧源 + 元数据 + tracking session + scope + 计数。"""

    view_input: JointViewInput
    capture: Any  # Mapping[int, frame] 或实现了 read_frame(frame_index) 的对象
    fps: float
    frame_size: tuple[int, int]
    homography: list[list[float]]
    roi_artifact: Any
    tracking_session: ViewTrackingSession
    scope: ViewScope = "perception"
    court_view_scorer: Any | None = None
    court_view_state: Any | None = None
    counters: dict[str, int] = field(default_factory=dict)

    @property
    def view_id(self) -> str:
        return self.view_input.camera_slot

    def get_frame(self, source_frame_index: int) -> Any:
        """按源帧号解帧(支持 dict 帧源 / read_frame 协议 / cv2.VideoCapture)。"""
        cap = self.capture
        if isinstance(cap, Mapping):
            return cap.get(source_frame_index)
        read = getattr(cap, "read_frame", None)
        if callable(read):
            return read(source_frame_index)
        # cv2.VideoCapture:seek + read
        try:
            cap.set(0, source_frame_index)  # CAP_PROP_POS_FRAMES
            ok, frame = cap.read()
            return frame if ok else None
        except Exception:
            return None

    def step(
        self,
        source_frame_index: int,
        timestamp_s: float,
        guidance: tuple[Any, ...] = (),
    ) -> ViewFrameResult | None:
        """解帧 + 推进 tracking session;无帧返回 None。"""
        frame = self.get_frame(source_frame_index)
        if frame is None:
            self.counters["missing_frame"] = self.counters.get("missing_frame", 0) + 1
            return None
        result = self.tracking_session.step(
            frame,
            frame_index=source_frame_index,
            timestamp=timestamp_s,
            guidance=guidance,
        )
        self.counters["stepped_frames"] = self.counters.get("stepped_frames", 0) + 1
        return result
