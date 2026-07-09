"""测试 RTMPose26Adapter 的关键点可见性 hysteresis 机制。"""

import pytest

from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter


def _make_adapter(
    conf_threshold: float = 0.3,
    conf_exit_threshold: float = 0.20,
) -> RTMPose26Adapter:
    """创建无模型的适配器实例，仅测试 _normalize_keypoints 的 hysteresis 逻辑。"""
    return RTMPose26Adapter(
        config_path=None,
        checkpoint_path=None,
        conf_threshold=conf_threshold,
        conf_exit_threshold=conf_exit_threshold,
    )


def _normalize(
    adapter: RTMPose26Adapter,
    confidence: float,
    track_id: str = "player-1",
    keypoint_index: int = 0,
) -> bool:
    """模拟单关键点的归一化，返回 visible 值。"""
    # 用 26 个相同置信度的关键点测试，取第 keypoint_index 个
    keypoints = [[0.0, 0.0]] * 26
    scores = [confidence] * 26
    result = adapter._normalize_keypoints(keypoints, scores, track_id=track_id)
    return result[keypoint_index].visible


# ── 场景 1: 首次出现置信度低于 enter 阈值 → 不可见 ──


def test_first_appearance_below_enter_threshold_is_invisible() -> None:
    adapter = _make_adapter(conf_threshold=0.3, conf_exit_threshold=0.20)
    # 置信度 0.25，低于 enter(0.3) 但高于 exit(0.2)，首次出现不可见
    visible = _normalize(adapter, 0.25)
    assert not visible, "首次出现且置信度低于 enter 阈值应不可见"


# ── 场景 2: 临界波动保持可见（hysteresis 防抖） ──


def test_hysteresis_preserves_visibility_during_fluctuation() -> None:
    adapter = _make_adapter(conf_threshold=0.3, conf_exit_threshold=0.20)

    # 首帧：高置信度，进入可见
    visible = _normalize(adapter, 0.35)
    assert visible

    # 第二帧：波动到 0.28，在 [exit, enter) 区间内，应保持可见
    visible = _normalize(adapter, 0.28)
    assert visible

    # 第三帧：波动到 0.25，仍在 [exit, enter) 区间，继续可见
    visible = _normalize(adapter, 0.25)
    assert visible

    # 第四帧：回到 0.35，保持可见
    visible = _normalize(adapter, 0.35)
    assert visible


# ── 场景 3: 骤降至 exit 以下 → 立即不可见 ──


def test_drop_below_exit_becomes_invisible_immediately() -> None:
    adapter = _make_adapter(conf_threshold=0.3, conf_exit_threshold=0.20)

    # 首帧：高置信度，进入可见
    visible = _normalize(adapter, 0.35)
    assert visible

    # 骤降至 0.10，低于 exit(0.2)，立即不可见
    visible = _normalize(adapter, 0.10)
    assert not visible


# ── 场景 4: 持续高置信度保持可见 ──


def test_always_high_confidence_stays_visible() -> None:
    adapter = _make_adapter(conf_threshold=0.3, conf_exit_threshold=0.20)

    for _ in range(10):
        visible = _normalize(adapter, 0.8)
        assert visible


# ── 场景 5: exit >= enter 退化配置时仍正常工作 ──


def test_degenerate_config_exit_gte_enter() -> None:
    """当 exit >= enter 时，hysteresis 区间为空，行为退化为 enter 阈值判定。"""
    adapter = _make_adapter(conf_threshold=0.3, conf_exit_threshold=0.35)

    # 置信度 0.32：高于 enter(0.3)，可见
    visible = _normalize(adapter, 0.32)
    assert visible

    # 置信度 0.28：低于 enter(0.3)，不可见（exit 无效因为始终不低于 exit）
    visible = _normalize(adapter, 0.28)
    assert not visible
