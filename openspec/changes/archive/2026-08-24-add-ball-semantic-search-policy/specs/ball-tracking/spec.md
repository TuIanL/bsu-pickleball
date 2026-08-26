## MODIFIED Requirements

### Requirement: Non-play timeline context is optional

当 pipeline 提供比赛语义搜索策略时，BallTracker SHALL 消费该策略作为正式候选发布和 tracker 更新的上层约束；当策略不可用、时间线缺失或 phase 为 `UNKNOWN` 时，tracker SHALL 使用既有兼容行为。人工或 corrected 来源的 `non_play` 时间线可以禁止新球候选进入正式 tracker 输出，但被抑制的原始候选必须保留在诊断中。

#### Scenario: 没有非比赛时间线和语义策略

- **WHEN** pipeline 不提供非比赛时间线和 `BallSearchPolicy`
- **THEN** tracker SHALL 使用 `player_motion_pixels` 作为比赛活动的弱信号
- **AND** 如果 `player_motion_pixels` 也不可用，tracker SHALL 回退现有静止黑名单行为且不得报错

#### Scenario: 语义策略为 UNKNOWN

- **WHEN** `BallSearchPolicy` 提供的 phase 为 `UNKNOWN` 或 provider 发生可恢复失败
- **THEN** tracker SHALL 继续执行既有候选过滤、连续性和物理门
- **AND** SHALL 在诊断中记录 `semantic_fallback=true`

#### Scenario: 权威非比赛时间线抑制正式候选

- **WHEN** 当前时间位于人工或 corrected 来源的 `non_play` 窗口
- **AND** policy mode 为 `enforced`
- **THEN** tracker SHALL 不得将新的球候选发布为正式球观察
- **AND** SHALL 保留原始候选、策略 phase、authority 和抑制原因
- **AND** 被抑制的候选 SHALL NOT 仅因该策略抑制而增加静止误检黑名单计数

#### Scenario: 算法活动判断只能作为弱约束

- **WHEN** 当前非比赛判断仅来自球员静止、球员站位或活动变化
- **THEN** tracker SHALL 将其作为策略 evidence 或软门
- **AND** 在证据不足时 SHALL NOT 硬性清除现有轨迹历史
- **AND** 真球连续性和动态物理证据仍 SHALL 有机会覆盖软抑制
