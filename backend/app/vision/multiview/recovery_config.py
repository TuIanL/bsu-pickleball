"""P1 online recovery 的集中、可序列化运行配置。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class P1OnlineRecoveryConfig:
    """在线恢复语义与实验参数的单一快照。

    这些默认值沿用现有 joint 实现的阈值；调用方可以注入实验配置，
    但运行产物必须保存 ``snapshot()`` 以保证可复现。
    """

    enabled: bool = True
    binding_weak_after_ms: float = 300.0
    binding_lost_after_ms: float = 1000.0
    min_donor_quality: float = 0.55
    donor_max_age_ms: float = 300.0
    donor_origins: tuple[str, ...] = ("base",)
    max_prediction_uncertainty_ft: float = 8.0
    guidance_cooldown_ticks: int = 3
    max_regions_per_view_per_tick: int = 4
    guided_detector_confidence: float = 0.15
    guided_max_residual_ft: float = 3.0
    association_gate_ft: float = 3.0
    local_identity_switch_penalty: float = 0.25
    guidance_global_mismatch_penalty: float = 0.5
    reassociation_confirm_ticks: int = 3
    guided_merge_iou_threshold: float = 0.5
    recovery_episode_gap_ms: float = 300.0
    _metadata: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def snapshot(self) -> dict[str, Any]:
        """Return JSON-friendly configuration data for manifests/diagnostics."""
        data = asdict(self)
        data["donor_origins"] = list(self.donor_origins)
        data.pop("_metadata", None)
        return data
