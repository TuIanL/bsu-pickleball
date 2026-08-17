## ADDED Requirements

### Requirement: Available-Miss 可用性维度记账

系统 SHALL 在 `ViewBinding` 上维护独立于 `visibility` 的可用性维度字段：`consecutive_available_misses`（默认 0）、`last_attempted_take_timestamp_ms`（可空）、`last_attempted_tick`（可空）、`last_observed_tick`（可空）。`visibility` SHALL 保持纯 recency 语义（`observed | weak | missing | lost`），MUST NOT 因 fast path 记账而改变。每个 canonical tick 的 association 完成后，系统 SHALL 对 `roster confirmed player × attempted available view` 记账，其中 **attempt authority SHALL 为 `view_results`（该 view 本 tick 真实产生 `ViewFrameResult`）**，`bundle.frame_status == "available"` 仅是 source availability authority。记账规则：该 view 有该 global 的 `AssociationUpdate` → 清零；该 view 为 attempted available 但无 `AssociationUpdate` → `consecutive_available_misses += 1`；frame 不可用或 `view_results` 无该 view（view_degraded / decode 失败等）→ 不计 visual miss（availability/decode/runtime skip）。记账方法 SHALL 按 canonical tick 幂等（相同 tick 重复调用不重复记账）。

#### Scenario: 有观测清零

- **WHEN** 某 tick 某 global 在 attempted available view 获得 `AssociationUpdate`
- **THEN** 该 view binding 的 `consecutive_available_misses` SHALL 清零
- **AND** `last_observed_tick` SHALL 更新为当前 canonical tick

#### Scenario: available global-view miss 递增

- **WHEN** 某 tick 某 view 为 attempted available（`view_id ∈ view_results` 且 `frame_status == "available"`）但该 global 在该 view 无 `AssociationUpdate`
- **THEN** 该 view binding 的 `consecutive_available_misses` SHALL 递增 1
- **AND** `last_attempted_tick` / `last_attempted_take_timestamp_ms` SHALL 更新

#### Scenario: view 未被成功尝试不计 miss

- **WHEN** 某 tick `frame_status[view] == "available"` 但 `view_results` 无该 view（view_degraded 跳过 / runtime.step 返回 None / 其他未产生 ViewFrameResult 路径）
- **THEN** 该 view binding 的 `consecutive_available_misses` SHALL NOT 递增
- **AND** 该情况 SHALL 记为 availability/decode/runtime skip，不得误记为"尝试了但球员未出现"

#### Scenario: frame 不可用不计 miss

- **WHEN** 某 tick 某 view frame 状态非 available（如 `unavailable_outside_valid_interval`）
- **THEN** 该 view binding 的 `consecutive_available_misses` SHALL NOT 递增

#### Scenario: 记账幂等

- **WHEN** 同一 canonical tick 对同一 binding 重复调用记账方法
- **THEN** 第二次调用 SHALL 直接返回，不重复递增或清零
- **AND** 状态与单次调用一致

### Requirement: Next-Tick Fast Path 触发（共享 predicate）

系统 SHALL 提供共享纯函数 `is_target_recovery_eligible(binding, fast_recovery_enabled) -> bool`，语义为：`binding.visibility in {"weak","missing","lost"}` 返回 True；否则当 `fast_recovery_enabled == True` 且 `binding.consecutive_available_misses >= 1` 返回 True；否则返回 False。该 predicate SHALL 被 `MultiViewJointRun` 的 recovery opportunity/episode 建立逻辑与 `GuidanceGenerator.generate()` 的 target eligibility 共同使用（MUST NOT 两处各自实现）。`fast_recovery_enabled` 配置开关（默认 True）SHALL 由 `MultiViewJointRun.__init__` 从 `P1OnlineRecoveryConfig` 同步进 `CrossViewGuidancePolicy`，两个地方不得各自持有独立默认值。fast path SHALL 不改变任何既有安全门（confirmed + cross_view_anchored、prediction uncertainty、donor quality/recency/origin、cooldown、max_regions_per_view_per_tick、geometry）。

#### Scenario: 上一 tick available miss 下一 tick 触发

- **WHEN** 某 global 在 target view 上一 canonical tick 出现 available miss（`consecutive_available_misses >= 1`），且本 tick 满足全部安全门
- **THEN** 系统 SHALL 生成该 `(global, target_view)` 的 guidance
- **AND** 即使该 binding `visibility` 仍为 `observed` 也 SHALL 触发

#### Scenario: 无 miss 时保持现状

- **WHEN** `consecutive_available_misses == 0` 且 `visibility == "observed"`
- **THEN** 系统 SHALL NOT 触发 guidance
- **AND** 行为与 fast path 引入前一致

#### Scenario: fast path 关闭回退现状

- **WHEN** `fast_recovery_enabled=false`
- **THEN** 触发条件 SHALL 仅使用 `visibility in {"weak","missing","lost"}`
- **AND** `consecutive_available_misses >= 1` SHALL NOT 单独触发

#### Scenario: run 与 guidance 使用同一 predicate

- **WHEN** 某 binding 的 `is_target_recovery_eligible` 返回 True
- **THEN** recovery opportunity/episode 建立逻辑 SHALL 与 guidance 触发逻辑得出一致结论
- **AND** 不得出现"guidance 已生成但 episode 未建立"的幽灵 guidance

### Requirement: Recovery opportunity/episode 与 fast path 同步

fast path 触发的 guidance SHALL 同步建立 `recovery_episode_id` 并计入 `recovery_opportunity_count`（复用 `is_target_recovery_eligible` 判定）。fast path 触发的 recovery 成功（target ROI 内重新获得 formal observation 并分配到 expected global）SHALL 计入 `guided_recovery_success_count`，episode 建立与关闭逻辑与 weak/lost 触发一致。fast path 因安全门（donor / uncertainty / geometry / cooldown）未生成 guidance 时，SHALL 记录 skip 计数且不建立 episode。

#### Scenario: fast path 触发并建立 episode

- **WHEN** 某 `(global, target_view)` 的 `is_target_recovery_eligible` 为 True（含 fast path）且满足全部安全门
- **THEN** 系统 SHALL 生成 guidance 并建立/复用 `recovery_episode_id`
- **AND** `recovery_opportunity_count` SHALL 递增

#### Scenario: fast path 被安全门拦截不建 episode

- **WHEN** `is_target_recovery_eligible` 为 True 但 donor quality 低于门限（或 uncertainty 超限等）
- **THEN** 系统 SHALL NOT 生成 guidance、SHALL NOT 建立 episode
- **AND** 对应 skip 计数 SHALL 递增

### Requirement: GuidanceDecision trigger/reason 分离

`GuidanceDecision` SHALL 增加 `trigger_source` 字段（`"visibility_age" | "available_miss" | None`），表示"为什么有资格"；原 `reason` 字段 SHALL 保持表示"最终为什么生成/拒绝"（`target_not_missing / donor_unavailable / donor_low_quality / prediction_uncertain / cooldown / geometry_unavailable / not_confirmed_anchored / generated` 等）。两者同时满足时 `trigger_source` 优先为 `visibility_age`。系统 MUST NOT 把 `available_miss` 语义塞进 `reason`（否则"有资格但被 donor 拒绝"场景会丢失真正失败原因）。

#### Scenario: fast path 有资格但 donor 拒绝

- **WHEN** `consecutive_available_misses >= 1` 使 fast path 有资格，但 donor quality 低于门限
- **THEN** `GuidanceDecision.trigger_source` SHALL 为 `available_miss`
- **AND** `GuidanceDecision.reason` SHALL 为 `donor_low_quality`（不丢失真正失败原因）

#### Scenario: visibility age 触发优先

- **WHEN** binding 同时满足 `visibility in {"weak","missing","lost"}` 与 `consecutive_available_misses >= 1`
- **THEN** `trigger_source` SHALL 为 `visibility_age`

#### Scenario: 生成 guidance 时双字段

- **WHEN** guidance 成功生成
- **THEN** `trigger_source` SHALL 为实际触发来源，`reason` SHALL 为 `generated`

### Requirement: 非 same-tick 语义与顺序冻结

本能力的快速触发 SHALL 基于**上一 canonical tick** 已完成的 miss 记账（pre-tick snapshot 可读取），MUST NOT 依赖当前 tick 内另一视角的新发现"倒回去"补检当前帧。`multiview_joint_run.py` 的主循环顺序（`age_bindings → predict → guidance snapshot → perception → association → available-miss ledger → display diagnostics → fusion/debug`）SHALL 保持，其中 available-miss ledger MUST 在 display diagnostics 构建之前完成（当前 tick 的 miss 状态不得晚一拍呈现）。

#### Scenario: 同 tick 新发现不回溯

- **WHEN** 本 tick donor view 刚发现某 global，但 target view 本 tick 的 guidance snapshot 已生成
- **THEN** 系统 SHALL NOT 用该 donor 新发现回溯修改本 tick 的 target guidance
- **AND** 该目标最早 SHALL 在下一 tick 才有机会被 guidance 覆盖

#### Scenario: 漏斗不晚一拍

- **WHEN** 某 tick 首次出现 available miss
- **THEN** 该 tick 的 display diagnostics 漏斗行 SHALL 已显示 `available_miss_streak=1`（先记账后构建）
- **AND** MUST NOT 显示 0（诊断晚一拍）

### Requirement: cooldown 原样保持

fast path SHALL 原样保持 `guidance_cooldown_ticks` 的现有计数 key、单位解释与 `commit()` 消费语义（仅真正调用 target ROI detection 后消费）；本能力 SHALL NOT 重新定义 cooldown 为严格 canonical-tick 语义，SHALL NOT 引入 time-based cooldown。

#### Scenario: cooldown 仍生效

- **WHEN** 某 `(global, target_view)` 距上次 guidance 不足 `guidance_cooldown_ticks`（按现有单位解释）
- **THEN** 即使 `consecutive_available_misses >= 1` 也 SHALL NOT 触发
- **AND** `GuidanceDecision.reason=cooldown`

#### Scenario: 未定义新 cooldown 语义

- **WHEN** 本能力实施后
- **THEN** cooldown 的计数 key 与消费行为 SHALL 与实施前一致（无兼容性变化）
