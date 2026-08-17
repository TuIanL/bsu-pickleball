"""JointViewRuntime —— joint_tracking_v2 单视角运行上下文(design D8)。

CanonicalAnalysisClock 只告诉 runtime 下一 `source_frame_index`;runtime 负责解帧、
`session.step`、per-view 诊断。`MultiViewJointRun` 持有两个 runtime(cam1 full / cam2 perception)。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping

import cv2

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
        # 必须用帧号语义（CAP_PROP_POS_FRAMES）定位，不能把帧号当毫秒（0 = CAP_PROP_POS_MSEC）：
        # 毫秒语义下 set(400) 实际定位到 400ms 处（60fps 时 ≈帧 25），导致检测跑在错误帧上、
        # 检测框每 ~5-8 tick 才变化一次（2026-08-13 定位的 joint 解帧 bug）。
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)
            ok, frame = cap.read()
            return frame if ok else None
        except Exception:
            return None

    def step(
        self,
        source_frame_index: int,
        timestamp_s: float,
        guidance: tuple[Any, ...] = (),
        timing_context: Any | None = None,
    ) -> ViewFrameResult | None:
        """解帧 + 推进 tracking session;无帧返回 None。兼容旧调用（prepare + complete 空 same-tick）。"""
        prepared = self.prepare(
            source_frame_index, timestamp_s,
            pre_tick_guidance=guidance, timing_context=timing_context,
        )
        if prepared is None:
            return None
        return self.complete(prepared, same_tick_guidance=(), timing_context=timing_context)

    def prepare(
        self,
        source_frame_index: int,
        timestamp_s: float,
        pre_tick_guidance: tuple[Any, ...] = (),
        timing_context: Any | None = None,
    ):
        """阶段 1：解帧恰好一次 + tracking_session.prepare_frame（不 update tracker）。

        decode 失败返回 None（decode skip，tracker.update 次数为 0）。
        """
        frame = self.get_frame(source_frame_index)
        if frame is None:
            self.counters["missing_frame"] = self.counters.get("missing_frame", 0) + 1
            return None
        return self.tracking_session.prepare_frame(
            frame,
            frame_index=source_frame_index,
            timestamp=timestamp_s,
            pre_tick_guidance=tuple(pre_tick_guidance),
        )

    def complete(
        self,
        prepared,
        same_tick_guidance: tuple[Any, ...] = (),
        timing_context: Any | None = None,
    ) -> ViewFrameResult | None:
        """阶段 2（commit）：转发 tracking_session.complete_frame（committed 防重复 update）。"""
        result = self.tracking_session.complete_frame(
            prepared, same_tick_guidance=tuple(same_tick_guidance)
        )
        self.counters["stepped_frames"] = self.counters.get("stepped_frames", 0) + 1
        if timing_context is None:
            return result
        return replace(
            result,
            source_timestamp_ms=getattr(timing_context, "source_timestamp_ms", None),
            mapped_take_timestamp_ms=getattr(timing_context, "mapped_take_timestamp_ms", None),
            selection_error_ms=getattr(timing_context, "selection_error_ms", None),
            timing_authority=getattr(timing_context, "timing_authority", "missing"),
            sync_quality=getattr(timing_context, "sync_quality", "unknown"),
        )
