"""下游消费契约（consumers）—— fused trajectory 的 metric eligibility 与消费适配。

- **metric eligibility**：哪些 fused sample 允许进入 movement / speed / heatmap。
  - `dual_observed` / `single_view_fallback` → metrics yes
  - `conflict` → 取决于是否接受某一路真实观测（sample 的 `metric_eligible` 标志）
  - `predicted` → visualization yes；movement / heatmap 默认 no
  - `unavailable` → no
- 提供移动/可视化点提取与 fused 不可用时的单视角回退选择。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FusedTrackPoint:
    """下游消费用的 fused 轨迹点（canonical 坐标）。"""

    global_player_id: str
    take_timestamp_ms: float
    reference_frame_index: int
    x_ft: float
    y_ft: float
    fusion_status: str
    measurement_source: str
    metric_eligible: bool


def metric_eligibility_policy(
    fusion_status: str,
    *,
    metric_eligible_flag: bool,
) -> bool:
    """按融合状态判定该 sample 是否进入运动指标。

    返回 False 的样本仍可做 visualization，只是不计入真实移动量。
    """
    if fusion_status in ("dual_observed", "single_view_fallback"):
        return True
    if fusion_status == "conflict":
        # 取决于是否接受某一路真实观测：由 sample 的 metric_eligible 标志决定。
        return metric_eligible_flag
    if fusion_status == "predicted":
        # 预测点：visualization yes，movement/heatmap 默认 no。
        return False
    return False  # unavailable


def _parse_samples(artifact: dict[str, object]) -> Sequence[dict[str, object]]:
    samples = artifact.get("samples")
    return samples if isinstance(samples, list) else []


def movement_points(
    artifact: dict[str, object],
    *,
    policy=metric_eligibility_policy,
) -> list[FusedTrackPoint]:
    """提取可进入 movement / speed / heatmap 的 fused 点（metric-eligible）。"""
    points: list[FusedTrackPoint] = []
    for sample in _parse_samples(artifact):
        x = sample.get("x_ft")
        y = sample.get("y_ft")
        if x is None or y is None:
            continue
        status = str(sample.get("fusion_status", "unavailable"))
        eligible = bool(sample.get("metric_eligible", False))
        if not policy(status, metric_eligible_flag=eligible):
            continue
        points.append(
            FusedTrackPoint(
                global_player_id=str(sample.get("global_player_id", "")),
                take_timestamp_ms=float(sample.get("take_timestamp_ms", 0.0)),
                reference_frame_index=int(sample.get("reference_frame_index", 0)),
                x_ft=float(x),
                y_ft=float(y),
                fusion_status=status,
                measurement_source=str(sample.get("measurement_source", "none")),
                metric_eligible=True,
            )
        )
    return points


def visualization_points(
    artifact: dict[str, object],
) -> list[FusedTrackPoint]:
    """提取全部有坐标的 fused 点（含 predicted，供 visualization）。"""
    points: list[FusedTrackPoint] = []
    for sample in _parse_samples(artifact):
        x = sample.get("x_ft")
        y = sample.get("y_ft")
        if x is None or y is None:
            continue
        points.append(
            FusedTrackPoint(
                global_player_id=str(sample.get("global_player_id", "")),
                take_timestamp_ms=float(sample.get("take_timestamp_ms", 0.0)),
                reference_frame_index=int(sample.get("reference_frame_index", 0)),
                x_ft=float(x),
                y_ft=float(y),
                fusion_status=str(sample.get("fusion_status", "unavailable")),
                measurement_source=str(sample.get("measurement_source", "none")),
                metric_eligible=bool(sample.get("metric_eligible", False)),
            )
        )
    return points


TrajectorySource = Literal["fused", "single_view", "unavailable"]


def select_trajectory_source(
    fused_available: bool,
    single_view_available: bool,
) -> TrajectorySource:
    """选择位置型输出的轨迹来源：优先 fused，否则单视角，双路失败为 unavailable。

    现有单视角 artifact 不删除、不覆盖；本函数只决定"消费哪个"。
    双路失败时返回 `unavailable`，不得假装存在单视角轨迹。
    """
    if fused_available:
        return "fused"
    if single_view_available:
        return "single_view"
    return "unavailable"
