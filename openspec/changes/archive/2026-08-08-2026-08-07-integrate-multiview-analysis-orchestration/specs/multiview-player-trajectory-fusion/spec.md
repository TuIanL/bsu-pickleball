# multiview-player-trajectory-fusion Specification

## Purpose

定义位置融合与下游消费契约：ViewIntrinsicQuality + PairConsistency、位置融合状态机、GlobalTrackFilter predict/update、`FusedPlayerTrajectoryArtifact` 与 metric eligibility、轨迹来源选择。本 Change 仅修正下游消费的轨迹来源选择：`select_trajectory_source()` 返回值扩展 `unavailable`，消除"双路失败仍声称存在单视角轨迹"的死三元。

## ADDED Requirements

### Requirement: 轨迹来源选择含 unavailable

`TrajectorySource` MUST 扩展为 `Literal["fused", "single_view", "unavailable"]`。`select_trajectory_source(fused_available, single_view_available)` MUST 按以下规则返回：fused 可用 → `"fused"`；仅单视角可用 → `"single_view"`；两者均不可用 → `"unavailable"`。MUST NOT 在双路失败时声称存在单视角轨迹。

#### Scenario: fused 可用

- **WHEN** `fused_available=True`
- **THEN** 返回 SHALL 为 `"fused"`

#### Scenario: 仅单视角可用

- **WHEN** `fused_available=False` 且 `single_view_available=True`
- **THEN** 返回 SHALL 为 `"single_view"`

#### Scenario: 双路失败

- **WHEN** `fused_available=False` 且 `single_view_available=False`
- **THEN** 返回 SHALL 为 `"unavailable"`
- **AND** 消费方 SHALL 按无可用轨迹处理（Parent 失败），不得虚构单视角轨迹

## MODIFIED Requirements

### Requirement: 下游消费受 metric eligibility 约束

下游消费 Fused Trajectory MUST 保持受 metric eligibility 约束：`dual_observed / single_view_fallback → metrics yes`；`conflict` 按 `metric_eligible` 标志；`predicted → visualization yes、metrics no`；`unavailable → no`。本 Change 的 Composer 接入 MUST NOT 放宽该消费契约。

#### Scenario: eligibility 契约不变

- **WHEN** Composer 消费 fused trajectory
- **THEN** `metric_eligibility_policy` 语义 SHALL 与 P0 冻结版本一致
- **AND** `predicted` / `unavailable` 样本 SHALL NOT 计入 movement / heatmap
