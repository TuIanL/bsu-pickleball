"""JointViewRuntime.get_frame 解帧语义测试（2026-08-13 解帧 bug 回归保护）。

背景：`get_frame` 曾用 `cap.set(0, source_frame_index)`，0 = CAP_PROP_POS_MSEC（毫秒），
把帧号当毫秒使用导致 set(400) 实际定位到 ≈帧 25、检测框每 ~5-8 tick 才变化。
修复后必须使用 CAP_PROP_POS_FRAMES（帧号语义）。
"""

from __future__ import annotations

import cv2
import pytest

from app.vision.multiview.joint_types import JointViewInput
from app.vision.multiview.joint_view_runtime import JointViewRuntime


class _FakeCapture:
    """记录 set/read 调用的假 VideoCapture。"""

    def __init__(self) -> None:
        self.set_calls: list[tuple[int, object]] = []
        self.read_calls = 0
        self._frame = None

    def set(self, prop_id: int, value: object) -> bool:
        self.set_calls.append((prop_id, value))
        return True

    def read(self):
        self.read_calls += 1
        return True, self._frame


def _make_runtime(capture: object) -> JointViewRuntime:
    return JointViewRuntime(
        view_input=JointViewInput(camera_slot="cam_1", camera_id="c1"),
        capture=capture,
        fps=60.0,
        frame_size=(1920, 1080),
        homography=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        roi_artifact=None,
        tracking_session=None,
        scope="full",
    )


def test_get_frame_seeks_with_frame_index_semantics():
    """get_frame 必须用 CAP_PROP_POS_FRAMES（帧号），不得用 POS_MSEC（毫秒）。"""
    cap = _FakeCapture()
    runtime = _make_runtime(cap)
    runtime.get_frame(400)
    assert cap.set_calls, "get_frame 必须调用 cap.set 定位帧"
    prop_id, value = cap.set_calls[0]
    assert prop_id == cv2.CAP_PROP_POS_FRAMES, (
        f"set 第一参数应为 CAP_PROP_POS_FRAMES({cv2.CAP_PROP_POS_FRAMES})，"
        f"实际 {prop_id}（0=POS_MSEC 会把帧号当毫秒，导致解帧漂移）"
    )
    assert value == 400
    assert cap.read_calls == 1


def test_get_frame_uses_index_value_not_seconds():
    """帧号原样传入 set，不得换算成毫秒/秒。"""
    cap = _FakeCapture()
    runtime = _make_runtime(cap)
    runtime.get_frame(1024)
    _, value = cap.set_calls[0]
    assert value == 1024


def test_get_frame_returns_none_when_decode_fails():
    """解码失败返回 None（现有契约保持）。"""

    class _FailCapture(_FakeCapture):
        def read(self):
            return False, None

    runtime = _make_runtime(_FailCapture())
    assert runtime.get_frame(10) is None


def test_get_frame_mapping_source_unchanged():
    """dict 帧源路径行为不变（不触发 cap.set）。"""
    frames = {5: object(), 6: object()}
    runtime = _make_runtime(frames)
    assert runtime.get_frame(5) is frames[5]
    assert runtime.get_frame(6) is frames[6]
    assert runtime.get_frame(99) is None
