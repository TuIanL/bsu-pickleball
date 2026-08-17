# multiview-online-player-recovery Specification

## Purpose
TBD - created by archiving change make-p1-cross-view-player-recovery-operational. Update Purpose after archive.
## Requirements
### Requirement: 在线恢复证据链
`joint_tracking_v2` SHALL 仅在 target view 从自身当前 source frame 的真实像素中重新获得 formal local player observation 后，声明一次 online recovery。该 observation SHALL 可追溯 donor view、guidance、target source frame、local player identity 与 identity epoch、source track、pre-gate residual 与 assigned global player。当 recovery 针对 `confirmed AND cross_view_anchored` 的 global player 时，assigned global SHALL 为 guidance 指定的 `expected_global_player_id`，除非几何不可行或 pre-gate 拒绝（此时记录 reject / unresolved，SHALL NOT 转投其他 global）。同 tick 的 base formal observation 正常走普通关联，stale guidance SHALL NOT 覆盖 base evidence（base 优先语义与 `base_recovered` 保持一致）。recovery opportunity 的判定 SHALL 支持 available-miss fast path：目标 binding 因 `consecutive_available_misses >= 1` 触发的 guidance 生成的 recovery 机会 SHALL 与 weak/lost 触发的机会同等计入，但 episode 建立与 success 语义 SHALL 不变。

#### Scenario: 双向 controlled dropout 恢复
- **WHEN** 已 anchored 的 global player 在 Cam1 变 weak、Cam2 保持可信 base observation，且 Cam1 当前 frame available
- **THEN** 系统 SHALL 使用 Cam2 donor guidance 在 Cam1 的真实像素中恢复 formal local player observation
- **AND** 恢复前、中、后的 global player identity SHALL 保持一致（即 guidance 指定的 expected global）

#### Scenario: 预测不构成恢复
- **WHEN** target ROI 未检测到或未接受真实 candidate
- **THEN** 系统 SHALL NOT 生成 target-view recovered observation
- **AND** SHALL NOT 将 prediction 或 guidance 计为 recovery

#### Scenario: guided 恢复不转投其他 global
- **WHEN** guidance 明确 `expected_global_player_id=G3`，Cam1 在 ROI 内通过 pre-gate 重新检测到球员，但该候选与 G2 的几何代价更低
- **THEN** 系统 SHALL 仍优先绑定回 G3
- **AND** SHALL NOT 因排序代价转投 G2

#### Scenario: guidance 目标不可行则拒绝
- **WHEN** guided candidate 与 G3 的几何距离超出该状态门限，或 pre-gate 拒绝
- **THEN** 系统 SHALL 将该候选记为 reject / unresolved
- **AND** SHALL NOT 将其分配给其他 roster global

#### Scenario: base 证据优先于 stale guidance
- **WHEN** 同 tick 的 base formal observation 已可靠看到目标球员，而 guidance 期望另一 global（陈旧）
- **THEN** base observation SHALL 走普通关联，guidance 强约束不覆盖
- **AND** 恢复 episode 按 base_recovered 记录，不计为 guided success

#### Scenario: available-miss fast path 恢复机会
- **WHEN** 目标 binding 因 `consecutive_available_misses >= 1` 触发 guidance，且 target ROI 内重新获得真实 formal observation
- **THEN** 系统 SHALL 记录一次 guided recovery（success 语义与 weak/lost 触发一致）
- **AND** episode 的建立与关闭逻辑 SHALL 与既有语义一致

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
### Requirement: Recovery diagnostics 完整性

运行 diagnostics SHALL 记录 target weak、eligible opportunity、guidance generated、ROI invoked、candidate、pre-gate accepted、tracker admitted、local identity admitted 与 expected-global preserved 的漏斗，并按原因区分 donor、availability、pre-gate、lock 与 global assignment 失败。

#### Scenario: 可定位恢复失败
- **WHEN** 某 target view 没有产生恢复 observation
- **THEN** diagnostics SHALL 记录最早阻断阶段及结构化 reason
- **AND** target frame unavailable SHALL 与 source frame available 但无视觉 observation 区分

### Requirement: Recovery episode 与成功语义

系统 SHALL 在 target binding 首次进入 weak/lost 时建立 `recovery_episode_id`，直至 target 重新形成 formal observation。`recovery_opportunity` SHALL 要求 target frame available、weak/lost、global confirmed+anchored 与可接受 uncertainty；`guided_recovery_success` SHALL 要求真实 guided pixel evidence 经 pre-gate、surviving tracker、formal lock/local identity 后被分配到 expected global。same-tick base recovery SHALL 记录为 `base_recovered`，不得计入 guided success。

#### Scenario: same-tick base 优先
- **WHEN** pre-tick target binding weak，且该 tick 的 base 与 guided detection 都命中同一 target player
- **THEN** 系统 SHALL 保留 base evidence 并记录 `base_recovered`
- **AND** SHALL NOT 将该 episode 标记为 guided recovery success

### Requirement: same-tick 恢复单独计数

same-tick 双向恢复形成的 target-view formal observation SHALL 作为独立 recovery 来源，**单独计数**（`same_tick_opportunity_count / same_tick_guidance_generated_count / same_tick_roi_invocation_count / same_tick_formal_observation_count / same_tick_recovery_success_count`），MUST NOT 混入 #2 的 `guided_recovery_success_count`（证明增益来源：next-tick fast path vs same-tick path）。recovery episode 建立与关闭逻辑 SHALL 与既有语义一致。

#### Scenario: same-tick 恢复计入独立计数

- **WHEN** 某 global 因 same-tick guidance 在缺失路 ROI 内重新获得 formal observation
- **THEN** 系统 SHALL 递增 `same_tick_formal_observation_count` 与 `same_tick_recovery_success_count`
- **AND** `guided_recovery_success_count`（#2 语义）SHALL NOT 因此递增

#### Scenario: same-tick 未恢复不虚报

- **WHEN** same-tick ROI 内未检测到或未接受真实 candidate
- **THEN** 系统 SHALL NOT 声明 recovery success
- **AND** SHALL NOT 将 same-tick guidance 计为恢复
