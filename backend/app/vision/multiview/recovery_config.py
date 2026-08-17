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
    # available-miss fast path：上一 canonical tick 出现 available miss 时，
    # 下一 tick 即可触发 guidance（无需等待 binding_weak_after_ms）。
    fast_recovery_enabled: bool = True
    # same-tick usable-candidate recovery（B-Phase-2）：本 tick 另一路有可靠 base
    # candidate、本路无 usable candidate 时，在 tracker commit 前受控补检。
    same_tick_recovery_enabled: bool = True
    # pre-association：一对一匹配门限（canonical 英尺）与 ambiguity margin
    pre_association_gate_ft: float = 3.0
    ambiguity_margin: float = 0.15
    _metadata: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def snapshot(self) -> dict[str, Any]:
        """Return JSON-friendly configuration data for manifests/diagnostics."""
        data = asdict(self)
        data["donor_origins"] = list(self.donor_origins)
        data.pop("_metadata", None)
        return data


def is_target_recovery_eligible(binding: Any, fast_recovery_enabled: bool) -> bool:
    """共享 predicate：目标视角是否具备 recovery 触发资格。

    语义（run 的 opportunity/episode 建立 与 guidance 触发 MUST 共用本函数，
    避免两处漂移产生"幽灵 guidance"）：

    - `visibility in {"weak", "missing", "lost"}` → True（visibility age 触发）；
    - 否则 `fast_recovery_enabled and binding.consecutive_available_misses >= 1`
      → True（available-miss fast path 触发）；
    - 否则 False。
    """
    if binding is None:
        return False
    if binding.visibility in {"weak", "missing", "lost"}:
        return True
    if fast_recovery_enabled and getattr(binding, "consecutive_available_misses", 0) >= 1:
        return True
    return False
