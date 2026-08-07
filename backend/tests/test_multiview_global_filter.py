"""GlobalTrackFilter —— predict/update 单一状态源：EWMA、outlier、hold。"""

from __future__ import annotations

import pytest

from app.vision.multiview.global_filter import GlobalTrackFilter


def test_filter_first_update_adopts():
    filter_ = GlobalTrackFilter()
    x, y = filter_.update("g1", 5.0, 8.0, 0.0)
    assert (x, y) == (5.0, 8.0)


def test_filter_ewma_smooths():
    filter_ = GlobalTrackFilter(alpha=0.5, max_speed_ft_s=100.0)
    filter_.update("g1", 5.0, 8.0, 0.0)
    x, y = filter_.update("g1", 7.0, 8.0, 1 / 30.0)
    assert x == pytest.approx(6.0)  # 0.5*7 + 0.5*5
    assert y == pytest.approx(8.0)


def test_filter_outlier_clamped():
    filter_ = GlobalTrackFilter(alpha=0.5, max_speed_ft_s=30.0)
    filter_.update("g1", 5.0, 8.0, 0.0)
    # 0.05s 内跳 ~39ft → 远超 30ft/s，钳制到当前平滑位置。
    x, y = filter_.update("g1", 30.0, 30.0, 0.05)
    assert (x, y) == (5.0, 8.0)


def test_filter_predict_within_hold_only():
    filter_ = GlobalTrackFilter(max_hold_s=1.0)
    filter_.update("g1", 5.0, 8.0, 0.0)
    assert filter_.predict(0.5)["g1"] == (5.0, 8.0)
    assert filter_.predict(1.5) == {}  # 超出 hold 窗口 → 不再预测


def test_filter_predict_missing_player():
    filter_ = GlobalTrackFilter()
    assert filter_.predict(0.0) == {}
    assert filter_.state_for("g1") is None
