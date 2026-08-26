## ADDED Requirements

### Requirement: Calibrated semantic boundaries preserve reversible tracker lifecycle

当 semantic adjudicator 输出 `pending_start` 或 `pending_end` 时，BallTracker SHALL 保留受配置 grace window 约束的连续性上下文；只有 confirmed boundary 在 Enforced rollout 下才可以封存 segment、reset tracker 或打开新的 formal segment。

#### Scenario: Pending end does not clear active tracker state

- **WHEN** algorithmic evidence 使回合结束变得可能但 boundary 尚未 confirmed
- **THEN** tracker SHALL 保留当前预测位置、连续性计数和 formal segment
- **AND** SHALL 将候选标记为 pending 或 diagnostic，而不是立即执行 reset

#### Scenario: Confirmed boundary still resets exactly once

- **WHEN** manual/corrected boundary 已通过 adjudicator 确认且 Enforced rollout 生效
- **THEN** tracker SHALL 在 formal candidate publication 前执行对应 lifecycle action
- **AND** 同一 `boundary_action_id` 的后续 tick MUST NOT 重复封存、reset 或创建 segment

#### Scenario: New rally does not reuse the sealed segment

- **WHEN** confirmed end 已封存上一段且后续语义进入 `RALLY_ACTIVE`
- **THEN** tracker SHALL 创建新的 formal segment id
- **AND** 新段 MUST NOT 复用上一段的预测历史、暂态候选或 segment id

### Requirement: Pending semantic boundaries support bounded active-rally rescue

系统 SHALL 允许在 boundary 尚未 confirmed 时使用满足配置的球运动、轨迹连续性和球员活动联合证据救援当前回合；rescue 不得跨越已经执行的 authoritative reset。

#### Scenario: Continuous moving candidates rescue pending end

- **WHEN** tracker 处于 `pending_end`
- **AND** 候选在预测门内连续出现且球员活动符合比赛中条件
- **THEN** tracker SHALL 清除 pending end 影响并继续当前 formal segment
- **AND** diagnostics SHALL 记录 `rescued_active` 及其证据 ids

#### Scenario: Weak candidate cannot rescue by itself

- **WHEN** pending end 期间只有单帧高置信候选但没有运动连续性或球员活动 corroboration
- **THEN** tracker SHALL 保持 pending 或 fail-open 的既有处理
- **AND** SHALL NOT 因该候选直接创建新的 formal segment

#### Scenario: Authoritative reset blocks rescue across segments

- **WHEN** authoritative boundary 已确认并执行 `seal_formal_segment` 与 `reset_tracker_for_next_rally`
- **THEN** 后续候选 MUST NOT 追加到旧 segment
- **AND** 只能通过新的 rally start/open action 进入新的 segment

### Requirement: Tracker diagnostics expose adjudication impact

系统 SHALL 在球跟踪诊断中区分 pending、confirmed、rescued 和 suppressed candidate，并记录 semantic boundary action、formal candidate before/after、segment id、grace window 和 fallback reason。

#### Scenario: Pending candidate is auditable

- **WHEN** 候选被 pending semantic boundary 影响
- **THEN** diagnostics SHALL 保留 raw candidate、pending reason、evidence ids 和当前 segment id
- **AND** SHALL 不将其误记为 stationary false positive

#### Scenario: Enforced and Shadow remain distinguishable

- **WHEN** 同一输入分别运行 Shadow 与 Enforced policy
- **THEN** tracker diagnostics SHALL 能区分建议的 boundary action 与实际执行的 lifecycle action
- **AND** SHALL 记录两种模式的 formal candidate counts
