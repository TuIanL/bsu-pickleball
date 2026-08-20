"""fix-multiview-anchor-span-debug-frame-mapping 的 Debug Renderer 测试（验收指标 1/2 视觉侧）。

验证：
- available_extrapolated 被当作可渲染状态，且 source_frame_index 递增时正常解码（不冻结）；
- 历史 fallback_valid_start trace 仍被渲染（向后兼容）；
- improve-multiview-debug-replay-readability：候选框双层绘制、display-only 主动禁画、
  court panel 等比几何（纯函数级断言）。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.services.joint_debug_renderer import (
    _CANDIDATE_COLOR,
    _DISPLAY_ONLY_BANNER_COLOR,
    _FORMAL_DETECTED_COLOR,
    _court_layout,
    _court_panel,
    _court_to_panel,
    _draw_view_overlays,
    _read_trace_frame,
)


class _FakeCapture:
    """用一个以帧索引填充的纯色帧模拟解码器，便于检测“是否冻结”。"""

    def __init__(self, size: tuple[int, int, int] = (4, 4, 3)) -> None:
        self.size = size
        self.pos: int | None = None

    def set(self, _prop: int, idx: int) -> bool:
        # cv2: set(POS_FRAMES, x) 设定“下一帧读取位置”，read() 读取该帧。
        self.pos = int(idx)
        return True

    def read(self):
        if self.pos is None:
            return False, None
        frame = np.full(self.size, float(self.pos), dtype=np.uint8)
        # 模拟解码器读取后指针前进（连续 read 优化依赖此自洽性）。
        self.pos += 1
        return True, frame

    def isOpened(self) -> bool:
        return True

    def release(self) -> None:
        return None


def _view(*, status: str, source_frame_index: int | None) -> dict:
    return {
        "status": status,
        "source_frame_index": source_frame_index,
        "source_timestamp_ms": 0.0,
        "mapped_take_timestamp_ms": 0.0,
        "selection_error_ms": None,
        "timing_authority": "source_pts",
        "observation_status": "unavailable",
        "observations": [],
        "detections": [],
        "guidance": [],
        "bindings": {},
    }


def test_renderer_available_extrapolated_not_frozen():
    """available_extrapolated 递增 source_index 时正常解码，不冻结为同一帧。"""
    cap = _FakeCapture()
    cursor: dict[str, object] = {"last_index": None, "frame": None}
    tick = {"canonical_tick": 0}
    previous: np.ndarray | None = None
    for idx in [195, 196, 197]:
        view = _view(status="available_extrapolated", source_frame_index=idx)
        frame = _read_trace_frame(cap, view, "cam_2", tick, cursor)
        assert isinstance(frame, np.ndarray) and frame.shape[-1] == 3
        # 源帧索引不同 → 解码得到不同的纯色帧（未被 cached_frame.copy() 冻结）
        if previous is not None:
            assert not np.array_equal(frame, previous)
        previous = frame


def test_renderer_legacy_fallback_valid_start_still_renders():
    """历史 fallback_valid_start trace 仍被渲染（向后兼容，D6）。"""
    cap = _FakeCapture()
    cursor: dict[str, object] = {"last_index": None, "frame": None}
    tick = {"canonical_tick": 0}
    frame = _read_trace_frame(cap, _view(status="fallback_valid_start", source_frame_index=204), "cam_2", tick, cursor)
    assert isinstance(frame, np.ndarray) and frame.shape[-1] == 3


# ---- improve-multiview-debug-replay-readability：候选框 / display-only / court 等比 ----

_FORMAL_BOX_COLOR = _FORMAL_DETECTED_COLOR
_FOOTPOINT_COLOR = (0, 255, 0)
_GUIDANCE_COLOR = (255, 80, 210)


def _has_color(frame: np.ndarray, color: tuple[int, int, int]) -> bool:
    return bool(np.any(np.all(frame == color, axis=2)))


def _available_view(**overrides) -> dict:
    view = _view(status="available", source_frame_index=0)
    view.update(overrides)
    return view


def test_overlays_draw_candidate_boxes_without_formal_labels():
    """bootstrap 期：formal 空但 candidate 非空 → 细线弱色候选框，无 Player_N 正式框。"""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    view = _available_view(
        detections=[],
        candidate_detections=[{"bbox": [10, 30, 100, 80], "track_id": 2, "confidence": 0.7}],
    )
    _draw_view_overlays(frame, view)
    # 候选框出现：thickness=1 顶边像素命中候选色
    assert tuple(frame[30, 55]) == _CANDIDATE_COLOR
    # 无正式框颜色（也无 Player_N 橙色标注）与 footpoint
    assert not _has_color(frame, _FORMAL_BOX_COLOR)
    assert not _has_color(frame, _FOOTPOINT_COLOR)


def test_candidate_box_replaced_by_formal_box_once_locked():
    """同一 track 完成正式锁定后：候选弱框消失，被 Player_N 正式框取代（不同时出现）。"""
    candidate_view = _available_view(
        detections=[],
        candidate_detections=[{"bbox": [10, 30, 100, 80], "track_id": 2, "confidence": 0.7}],
    )
    formal_view = _available_view(
        detections=[
            {
                "bbox": [10, 30, 100, 80],
                "track_id": 2,
                "player_id": "Player_2",
                "tracking_status": "detected",
                "image_footpoint": None,
            }
        ],
        candidate_detections=[],
    )
    candidate_frame = np.zeros((120, 160, 3), dtype=np.uint8)
    formal_frame = np.zeros((120, 160, 3), dtype=np.uint8)
    _draw_view_overlays(candidate_frame, candidate_view)
    _draw_view_overlays(formal_frame, formal_view)
    assert _has_color(candidate_frame, _CANDIDATE_COLOR)
    assert not _has_color(candidate_frame, _FORMAL_BOX_COLOR)
    assert _has_color(formal_frame, _FORMAL_BOX_COLOR)
    assert not _has_color(formal_frame, _CANDIDATE_COLOR)


def test_display_only_frame_skips_all_overlays_even_with_adversarial_detections():
    """display-only 帧主动禁画：即使异常 trace 带有 detections/candidate/guidance 也不画任何框。"""
    for status in ("available_extrapolated", "fallback_valid_start"):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        view = _view(status=status, source_frame_index=3)
        view["detections"] = [
            {
                "bbox": [10, 30, 100, 80],
                "track_id": 1,
                "tracking_status": "detected",
                "image_footpoint": [50, 60],
            }
        ]
        view["candidate_detections"] = [{"bbox": [20, 40, 80, 90], "track_id": 2}]
        view["guidance"] = [{"roi": [5, 20, 60, 70]}]
        _draw_view_overlays(frame, view)
        # 横幅存在（DISPLAY ONLY | TRACKING NOT STEPPED）
        assert _has_color(frame, _DISPLAY_ONLY_BANNER_COLOR), status
        # 对抗样本：全部 overlay 颜色被主动禁止
        for banned in (_FORMAL_BOX_COLOR, _CANDIDATE_COLOR, _FOOTPOINT_COLOR, _GUIDANCE_COLOR):
            assert not _has_color(frame, banned), (status, banned)


def test_display_only_banner_absent_when_frame_is_available():
    """进入 available tick（perception 实际执行）后横幅消失。"""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    _draw_view_overlays(frame, _available_view(detections=[]))
    assert not _has_color(frame, _DISPLAY_ONLY_BANNER_COLOR)


def test_court_layout_uses_single_scale():
    """单一 px/ft：横纵同比例，球场保持真实 44:20 = 2.2:1 外观。"""
    layout = _court_layout()
    assert layout.scale == pytest.approx(min((640 - 40.0) / 44.0, (260 - 40.0) / 20.0))
    assert layout.court_width_px == int(44.0 * layout.scale)
    assert layout.court_height_px == int(20.0 * layout.scale)
    assert layout.court_width_px / layout.court_height_px == pytest.approx(44.0 / 20.0, rel=0.02)
    # 1 ft 在两个方向产生相同像素长度（等比，无非均匀拉伸）
    x0, _ = _court_to_panel(0.0, 0.0, layout)
    x1, _ = _court_to_panel(0.0, 1.0, layout)
    _, y0 = _court_to_panel(0.0, 0.0, layout)
    _, y1 = _court_to_panel(1.0, 0.0, layout)
    assert abs((x1 - x0) - (y1 - y0)) <= 1


def test_court_lines_map_to_expected_positions():
    """网位于横向中点，两侧 NVZ line 各距网 7 ft，service centerline 在 x_ft=10。"""
    layout = _court_layout()
    left_x, _ = _court_to_panel(0.0, 0.0, layout)
    net_x, _ = _court_to_panel(0.0, 22.0, layout)
    left_nvz_x, _ = _court_to_panel(0.0, 15.0, layout)
    right_nvz_x, _ = _court_to_panel(0.0, 29.0, layout)
    center_x, _ = _court_to_panel(10.0, 0.0, layout)
    assert left_x < left_nvz_x < net_x < right_nvz_x
    assert net_x - left_nvz_x == pytest.approx(7 * layout.scale, abs=1)
    assert right_nvz_x - net_x == pytest.approx(7 * layout.scale, abs=1)
    # x_ft=10 → 纵向中点
    _, top_y = _court_to_panel(0.0, 0.0, layout)
    _, center_y = _court_to_panel(10.0, 0.0, layout)
    assert center_y - top_y == pytest.approx(10 * layout.scale, abs=1)


def test_court_to_panel_clamps_out_of_range_coordinates():
    """保留既有 [0,20]×[0,44] clamp：越界球员点吸附到球场边缘。"""
    layout = _court_layout()
    assert _court_to_panel(-3.0, -3.0, layout) == (layout.origin_x, layout.origin_y)
    far_x, far_y = _court_to_panel(30.0, 60.0, layout)
    assert far_x == layout.origin_x + int(44.0 * layout.scale)
    assert far_y == layout.origin_y + int(20.0 * layout.scale)


def test_court_panel_draws_boundary_within_layout():
    """court panel 顶边落在 layout 预期像素位置（绘制与几何一致），MP4 尺寸契约另由集成测试守护。"""
    panel = _court_panel({"reference_frame_index": -1}, SimpleNamespace(samples=[]))
    assert panel.shape == (260, 640, 3)
    layout = _court_layout()
    top_mid_x = layout.origin_x + layout.court_width_px // 2
    assert tuple(panel[layout.origin_y, top_mid_x]) == (35, 80, 35)
    # 网线存在（横向中点纵贯线）
    assert tuple(panel[layout.origin_y + layout.court_height_px // 2, top_mid_x]) == (35, 80, 35)
