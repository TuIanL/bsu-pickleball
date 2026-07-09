"""测试 BallTracker 静止黑名单机制。"""

from collections.abc import Sequence

import numpy as np
import pytest

from app.vision.pickleball_game_analysis.ball_tracker import BallTracker, BallTrackerConfig
from app.vision.pickleball_game_analysis.court_adapter import BallCourtAdapter
from app.vision.pickleball_game_analysis.schemas import BallCandidate


class _FakeDetector:
    """模拟球检测器：按预设坐标列表逐帧返回候选。"""

    def __init__(self, positions: Sequence[tuple[float, float] | list[BallCandidate]]) -> None:
        self._positions = positions
        self._call_count = 0

    def detect(self, _frame: np.ndarray, conf: float = 0.18) -> list[BallCandidate]:
        if self._call_count >= len(self._positions):
            return []
        item = self._positions[self._call_count]
        self._call_count += 1
        if isinstance(item, list):
            return item
        if item is None:
            return []
        x, y = item
        return [BallCandidate(image_x=x, image_y=y, confidence=0.5)]


def _make_tracker(blacklist_frames: int = 12) -> BallTracker:
    """创建带较小黑名单阈值（12 帧，测试用）的 tracker。"""
    config = BallTrackerConfig(stationary_blacklist_frames=blacklist_frames)
    detector = _FakeDetector([])
    return BallTracker(detector=detector, config=config, court_adapter=BallCourtAdapter())


def _stationary_candidates(x: float, y: float, count: int) -> list[BallCandidate]:
    """生成 count 帧的静止候选探测器数据。"""
    results: list[tuple[float, float]] = [(x, y)] * count
    return results


# ── 场景 1: 静止候选累积达到阈值 → 加入黑名单 ──


def test_stationary_candidate_accumulates_to_blacklist() -> None:
    """连续检测到同一位置的候选，累积帧数达到阈值后加入黑名单并拒绝。"""
    pos = (100.0, 200.0)
    tracker = _make_tracker(blacklist_frames=12)
    detector = _FakeDetector(_stationary_candidates(*pos, 20))
    tracker.detector = detector  # type: ignore[assignment]

    accepted_count = 0
    rejected_blacklist_count = 0

    for i in range(20):
        sample = tracker.update(
            frame=np.zeros((480, 640, 3), dtype=np.uint8),
            frame_index=i,
            timestamp_sec=i / 30.0,
        )
        if sample.accepted:
            accepted_count += 1
        elif sample.reject_reason == "stationary_blacklisted":
            rejected_blacklist_count += 1

    # 前几帧应被接受（尚未达到黑名单阈值）
    assert accepted_count > 0, "黑名单阈值达到前应有帧被接受"
    # 达到阈值后应开始拒绝
    assert rejected_blacklist_count > 0, "静止候选达到阈值后应被黑名单拒绝"
    # 黑名单位置应已被记录
    assert len(tracker._stationary_blacklist_positions) >= 1


# ── 场景 2: 真球覆盖黑名单（通过连续性检查） ──


def test_continuity_passing_candidate_overrides_blacklist() -> None:
    """通过连续性检查的真球候选覆盖黑名单，被接受。"""
    stationary_pos = (100.0, 200.0)
    tracker = _make_tracker(blacklist_frames=12)

    # 直接注入黑名单（避免累积期间轨迹被静止候选污染）
    grid = tracker.config.stationary_blacklist_grid_px
    grid_key = (int(stationary_pos[0] / grid) * grid, int(stationary_pos[1] / grid) * grid)
    tracker._stationary_blacklist_positions.add(grid_key)

    # 先在远处建立轨迹（跳跃距离应 > 2*stationary_radius 以触发覆盖路径）
    far_positions = [
        (400.0, 400.0),
        (380.0, 390.0),
        (360.0, 380.0),
        (340.0, 370.0),
        (320.0, 360.0),
    ]
    for frame_offset, pos in enumerate(far_positions):
        detector = _FakeDetector([pos])
        tracker.detector = detector  # type: ignore[assignment]
        sample = tracker.update(
            frame=np.zeros((480, 640, 3), dtype=np.uint8),
            frame_index=20 + frame_offset,
            timestamp_sec=(20 + frame_offset) / 30.0,
        )
        detector._call_count = 0
        assert sample.accepted, f"Frame {frame_offset} at {pos} should be accepted"

    # 真球逐步移动到黑名单位置（在 continuity gate 内）
    moving_pos = [
        (300.0, 350.0),
        (250.0, 300.0),
        (200.0, 260.0),
        (stationary_pos[0], stationary_pos[1]),  # 到达黑名单位置
    ]
    ball_accepted_at_blacklist = False
    for frame_offset, pos in enumerate(moving_pos):
        detector3 = _FakeDetector([pos])
        tracker.detector = detector3  # type: ignore[assignment]
        sample = tracker.update(
            frame=np.zeros((480, 640, 3), dtype=np.uint8),
            frame_index=30 + frame_offset,
            timestamp_sec=(30 + frame_offset) / 30.0,
        )
        detector3._call_count = 0
        if sample.accepted and pos == stationary_pos:
            ball_accepted_at_blacklist = True

    # 真球应能覆盖黑名单（连续性检查通过）
    assert ball_accepted_at_blacklist, "通过连续性检查的真球应覆盖静止黑名单"


# ── 场景 3: 标定重置清空黑名单 ──


def test_clear_resets_blacklist() -> None:
    """调用 clear() 后静止黑名单应被清空。"""
    tracker = _make_tracker(blacklist_frames=5)
    pos = (50.0, 100.0)
    detector = _FakeDetector(_stationary_candidates(*pos, 10))
    tracker.detector = detector  # type: ignore[assignment]

    for i in range(10):
        tracker.update(
            frame=np.zeros((480, 640, 3), dtype=np.uint8),
            frame_index=i,
            timestamp_sec=i / 30.0,
        )

    assert len(tracker._stationary_blacklist_positions) >= 1, "黑名单应有记录"

    tracker.clear()

    assert len(tracker._stationary_blacklist) == 0, "clear() 应清空累计计数器"
    assert len(tracker._stationary_blacklist_positions) == 0, "clear() 应清空黑名单"


# ── 场景 4: 不同位置不冲突 ──


def test_different_positions_independent() -> None:
    """不同位置的静止候选分别累积，互不干扰。"""
    pos_a = (100.0, 200.0)
    pos_b = (500.0, 300.0)

    tracker = _make_tracker(blacklist_frames=8)

    # 交替在两个位置出现候选
    for i in range(16):
        pos = pos_a if i % 2 == 0 else pos_b
        detector = _FakeDetector([pos])
        tracker.detector = detector  # type: ignore[assignment]
        tracker.update(
            frame=np.zeros((480, 640, 3), dtype=np.uint8),
            frame_index=i,
            timestamp_sec=i / 30.0,
        )
        detector._call_count = 0  # type: ignore[attr-defined]

    # 两个位置的帧数各为 8，应达到阈值（纯累积，无衰减）
    count_a = tracker._stationary_blacklist.get(
        (int(pos_a[0] / 5) * 5, int(pos_a[1] / 5) * 5), 0
    )
    count_b = tracker._stationary_blacklist.get(
        (int(pos_b[0] / 5) * 5, int(pos_b[1] / 5) * 5), 0
    )
    # 两处应分别累加
    assert count_a >= 8, f"交替出现时，位置A应累加到8，实际={count_a}"
    assert count_b >= 8, f"交替出现时，位置B应累加到8，实际={count_b}"
