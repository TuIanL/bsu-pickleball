## MODIFIED Requirements

### Requirement: 在线恢复证据链

`joint_tracking_v2` SHALL 仅在 target view 从自身当前 source frame 的真实像素中重新获得 formal local player observation 后，声明一次 online recovery。该 observation SHALL 可追溯 donor view、guidance、target source frame、local player identity 与 identity epoch、source track、pre-gate residual 与 assigned global player。当 recovery 针对 `confirmed AND cross_view_anchored` 的 global player 时，assigned global SHALL 为 guidance 指定的 `expected_global_player_id`，除非几何不可行或 pre-gate 拒绝（此时记录 reject / unresolved，SHALL NOT 转投其他 global）。同 tick 的 base formal observation 正常走普通关联，stale guidance SHALL NOT 覆盖 base evidence（base 优先语义与 `base_recovered` 保持一致）。

#### Scenario: 双向 controlled dropout 恢复

- **WHEN** 已 anchored 的 global player 在 Cam1 变 weak、Cam2 保持可信 base observation，且 Cam1 当前 frame available
- **THEN** 系统 SHALL 使用 Cam2 donor guidance 在 Cam1 的真实像素中恢复 formal local player observation
- **AND** 恢复前、中、后的 global player identity SHALL 保持一致（即 guidance 指定的 expected global）

#### Scenario: 预测不构成恢复

- **WHEN** target ROI 未检测到或未接受真实 candidate
- **THEN** 系统 SHALL NOT 生成 target-view recovered observation
- **AND** SHALL NOT 将 prediction 或 guidance 计为 recovery

### Requirement: Recovery opportunity 判定与 fast path 同步

recovery opportunity 判定 SHALL 使用与 guidance 触发相同的共享 predicate `is_target_recovery_eligible(binding, fast_recovery_enabled)`：`visibility in {"weak","missing","lost"}` 或（`fast_recovery_enabled` 且 `consecutive_available_misses >= 1`）。fast path 触发的 recovery 机会 SHALL 同步建立 `recovery_episode_id` 并计入 `recovery_opportunity_count`；fast path 触发的 recovery 成功（target ROI 内重新获得 formal observation 并分配到 expected global）SHALL 计入 `guided_recovery_success_count`。fast path 因安全门（donor / uncertainty / geometry / cooldown）未生成 guidance 时 SHALL 记录对应 skip 且不建立 episode。episode 建立与关闭逻辑 SHALL 与 weak/lost 触发一致。

#### Scenario: available-miss fast path 恢复机会

- **WHEN** 目标 binding 因 `consecutive_available_misses >= 1` 触发 guidance，且 target ROI 内重新获得真实 formal observation
- **THEN** 系统 SHALL 记录一次 guided recovery（success 语义与 weak/lost 触发一致）
- **AND** episode 的建立与关闭逻辑 SHALL 与既有语义一致

#### Scenario: 无幽灵 guidance

- **WHEN** `is_target_recovery_eligible` 为 True 且 guidance 已生成
- **THEN** 对应的 `recovery_episode_id` 必须已建立（或复用）
- **AND** `recovery_opportunity_count` 必须已计入该机会
