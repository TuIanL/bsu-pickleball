"""A/B 验证核心指标 —— RMSE、覆盖率、跳点、ID switch、区域拆分（合成数据）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "multiview_ab_validate.py"
_spec = importlib.util.spec_from_file_location("multiview_ab_validate", _SCRIPT)
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)


def _gt_sample(gid, ms, x, y):
    return {"global_player_id": gid, "take_timestamp_ms": ms, "x_ft": x, "y_ft": y}


def test_evaluate_group_rmse_and_coverage():
    gt = [_gt_sample("g1", 0.0, 5.0, 8.0), _gt_sample("g1", 33.3, 5.0, 8.0)]
    # 轨迹点略偏 0.5ft。
    points = [(0.0, 5.5, 8.0, "g1"), (33.3, 5.5, 8.0, "g1")]
    result = module.evaluate_group("fused", points, gt, tolerance_ms=50.0, jump_threshold_ft_s=30.0)
    assert result["coverage"] == 1.0
    assert result["rmse_ft"] == pytest.approx(0.5)
    assert result["identity_switch_count"] == 0


def test_evaluate_group_missing_tolerance_counts_uncovered():
    gt = [_gt_sample("g1", 0.0, 5.0, 8.0), _gt_sample("g1", 1000.0, 5.0, 8.0)]
    points = [(0.0, 5.0, 8.0, "g1")]
    result = module.evaluate_group("fused", points, gt, tolerance_ms=50.0, jump_threshold_ft_s=30.0)
    assert result["coverage"] == 0.5
    assert result["identity_switch_count"] == 0


def test_evaluate_group_identity_switch_detected():
    gt = [
        _gt_sample("g1", 0.0, 5.0, 8.0),
        _gt_sample("g1", 33.3, 5.0, 8.0),
        _gt_sample("g1", 66.7, 5.0, 8.0),
    ]
    # g1 的轨迹在第三帧换成了别的 player id。
    points = [(0.0, 5.0, 8.0, "g1"), (33.3, 5.0, 8.0, "g1"), (66.7, 5.0, 8.0, "global_player_2")]
    result = module.evaluate_group("fused", points, gt, tolerance_ms=50.0, jump_threshold_ft_s=30.0)
    assert result["identity_switch_count"] == 1


def test_region_split_far_vs_near():
    gt = [_gt_sample("g1", 0.0, 5.0, 10.0), _gt_sample("g1", 33.3, 5.0, 40.0)]
    far, near = module._region_split(gt, far_y_ft=22.0)
    assert len(far) == 1 and far[0]["y_ft"] == 40.0
    assert len(near) == 1 and near[0]["y_ft"] == 10.0


def test_jump_rate_counts_outliers():
    gt = [_gt_sample("g1", 0.0, 5.0, 8.0)]
    points = [
        (0.0, 5.0, 8.0, "g1"),
        (33.3, 5.0, 8.0, "g1"),
        (66.7, 20.0, 40.0, "g1"),  # 33ms 内跳 ~34ft → 超速
    ]
    result = module.evaluate_group("fused", points, gt, tolerance_ms=50.0, jump_threshold_ft_s=30.0)
    assert result["jump_rate"] == 0.5  # 2 段中 1 段超速
