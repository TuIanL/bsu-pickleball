"""弹地抑制 prefilter 的窗口边界与快速垫击回归测试（设计 D2 / I7 / I8 / I12）。"""

from app.vision.pickleball_game_analysis.ball_contact_event_detector import HitCandidate
from app.vision.pickleball_game_analysis.ball_event_resolver import BallEventResolver
from app.vision.pickleball_game_analysis.schemas import BounceEvent


def _bounce(frame: int, timestamp_sec: float, conf: float = 0.9) -> BounceEvent:
    return BounceEvent(
        event_id=f"bounce-{frame}",
        frame_index=frame,
        timestamp_sec=timestamp_sec,
        image_xy=(140.0, 200.0),
        court_xy=None,
        confidence=conf,
        detection_method="test",
    )


def _candidate(frame: int, timestamp_sec: float, conf: float = 0.8) -> HitCandidate:
    return HitCandidate(
        frame_index=frame,
        timestamp_sec=timestamp_sec,
        image_xy=(140.0, 200.0),
        confidence=conf,
        status="confirmed_hit",
    )


def test_window_boundaries():
    """有符号非对称窗口边界：-0.05s 与 +0.08s 抑制；+0.12s 与 +0.20s 放行。"""
    resolver = BallEventResolver()
    bounce = _bounce(30, 1.00, conf=0.95)

    cases = [
        (0.95, "suppressed"),  # bounce - 0.05s
        (1.08, "suppressed"),  # bounce + 0.08s
        (1.12, "survived"),  # bounce + 0.12s
        (1.20, "survived"),  # bounce + 0.20s
    ]
    for timestamp, expected in cases:
        candidate = _candidate(int(timestamp * 30), timestamp)
        result = resolver.prefilter([candidate], [bounce])[0]
        assert result.prefilter_status == expected, f"t={timestamp}s 期望 {expected}"


def test_weak_bounce_does_not_suppress():
    """弹地置信度低于抑制阈值时不抑制候选。"""
    resolver = BallEventResolver()
    weak = _bounce(30, 1.00, conf=0.30)
    candidate = _candidate(30, 1.00)
    result = resolver.prefilter([candidate], [weak])[0]
    assert result.prefilter_status == "survived"


def test_quick_dink_after_bounce_survives_and_opens_new_shot():
    """快速垫击回归：frame 136（bounce 后 0.20s）不被抑制，能关闭上一 Shot。"""
    resolver = BallEventResolver()
    # frame 100 P1 hit，frame 130 bounce，frame 136 P3 快速垫击（30fps）
    bounce = _bounce(130, 130 / 30.0, conf=0.95)
    dink = _candidate(136, 136 / 30.0)
    result = resolver.prefilter([dink], [bounce])[0]
    assert result.prefilter_status == "survived"
    # 该候选进入最终事件列表，可供 ShotAssembler 关闭上一 Shot（I12）
    events = resolver.finalize([result], [bounce])
    hits = [e for e in events if e.event_type.value == "hit"]
    assert len(hits) == 1
    assert hits[0].frame_index == 136


def test_config_snapshot():
    """抑制窗口配置快照写入 diagnostics。"""
    resolver = BallEventResolver()
    snapshot = resolver.suppression_config_snapshot(fps=30.0, frame_stride=1)
    assert snapshot["bounce_suppress_before_sec"] == 0.07
    assert snapshot["bounce_suppress_after_sec"] == 0.10
    assert snapshot["effective_fps"] == 30.0
    assert snapshot["frame_stride"] == 1
