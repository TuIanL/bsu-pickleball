## MODIFIED Requirements

### Requirement: CrossViewGuidancePolicy 触发语义

系统 SHALL 提供 `CrossViewGuidancePolicy`,冻结 guidance 触发条件:`min_global_confidence` / `max_uncertainty_ft` / `missing_after_ticks` / `guidance_cooldown_ticks` / `max_regions_per_view_per_tick`。`ViewBinding` SHALL 包含 `visibility: observed | weak | missing | lost`、`last_seen_take_timestamp_ms`、`quality`、`consecutive_available_misses`。目标视角的 guidance 触发资格 SHALL 由共享 predicate `is_target_recovery_eligible(binding, fast_recovery_enabled)` 判定：`visibility in {"weak","missing","lost"}` 或（`fast_recovery_enabled` 且 `consecutive_available_misses >= 1`）时 SHALL 允许触发 high-recall ROI；两者均不满足（observed 且无 available miss）的 global SHALL 不重复补跑 guided ROI。

#### Scenario: 仅弱/缺/失触发（fast path 无 miss）

- **WHEN** 某 confirmed+anchored global 的目标视角 binding 为 `observed` 且 `consecutive_available_misses == 0`
- **THEN** 系统 SHALL NOT 为该 tick 生成 guided ROI
- **AND** `GuidanceDecision.reason` SHALL 为 `target_not_missing`

#### Scenario: available miss 快速触发

- **WHEN** 某 confirmed+anchored global 的目标视角 binding 仍为 `observed`，但上一 canonical tick 出现 available miss（`consecutive_available_misses >= 1`）且 `fast_recovery_enabled=true`
- **THEN** 系统 SHALL 允许为该 tick 生成 guided ROI
- **AND** `GuidanceDecision.trigger_source` SHALL 为 `available_miss`

#### Scenario: cooldown 与上限

- **WHEN** 已触发过一次 guidance
- **THEN** 在 `guidance_cooldown_ticks` 内 SHALL NOT 重复触发（按现有单位解释与消费语义）
- **AND** 每 view 每 tick 的 guided region 数 SHALL 不超过 `max_regions_per_view_per_tick`

### Requirement: GuidanceDecision 触发来源可观测

`GuidanceDecision` SHALL 携带 `trigger_source`（`"visibility_age" | "available_miss" | None`）以区分"为什么有资格"，同时保留 `reason` 表示"最终为什么生成/拒绝"。系统 MUST NOT 将 fast path 语义写入 `reason` 而丢失真正的拒绝原因。

#### Scenario: 有资格但被拒绝时双字段独立

- **WHEN** fast path 有资格（`trigger_source=available_miss`）但 donor 不合格
- **THEN** `GuidanceDecision.reason` SHALL 为 `donor_low_quality`（或对应 donor 原因）
- **AND** `trigger_source` SHALL 保持 `available_miss`
