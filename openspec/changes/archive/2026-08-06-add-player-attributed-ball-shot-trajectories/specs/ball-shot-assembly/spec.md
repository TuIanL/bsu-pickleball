# ball-shot-assembly Specification

## Purpose
定义 Shot 生命周期与归属传播：`shot_id` 表示一次击球产生的完整球路，跨弹地段落传播击球者归属；bounce 只切分 flight segment，不改变 shot 归属。

## Requirements

### Requirement: Shot 生命周期
系统 SHALL 维护 Shot 生命周期：confirmed/ambiguous 击球与 serve 开启新 Shot，bounce 保持当前 Shot，long tracking loss 与流终止关闭 Shot。

#### Scenario: 确认击球开启新 Shot
- **WHEN** 出现 `event_status = confirmed` 的击球事件
- **THEN** 系统 SHALL 关闭当前 Shot 并开启新 Shot
- **AND** 新 Shot 的 `hitter_player_id` SHALL 为该击球的归属球员

#### Scenario: 弹地不改变 Shot
- **WHEN** 一个 Shot 的飞行过程中出现 bounce
- **THEN** 该 bounce SHALL 只产生新的 flight segment
- **AND** 新 segment SHALL 继承原 Shot 的 `shot_id` 与 `hitter_player_id`

#### Scenario: 弹地后快速击球关闭上一 Shot
- **WHEN** bounce 后短时间内出现新的真实击球（如网前快速垫击）
- **THEN** 该击球 SHALL 关闭上一 Shot 并开启新 Shot
- **AND** 上一 Shot 的归属 MUST NOT 因 bounce 而丢失

#### Scenario: ambiguous 击球开启无主 Shot
- **WHEN** 出现 `event_status = ambiguous` 的击球事件
- **THEN** 系统 SHALL 关闭当前 Shot 并开启新 Shot
- **AND** 新 Shot 的 `ownership_status` SHALL 为 `ambiguous` 或 `unassigned`，`hitter_player_id` 可为 null

#### Scenario: suppressed/rejected 候选无影响
- **WHEN** 击球候选被 bounce 抑制或被拒绝
- **THEN** 该候选 SHALL NOT 关闭当前 Shot、开启新 Shot 或改变现有 Shot owner

#### Scenario: 长时间丢失关闭 Shot
- **WHEN** 出现 long tracking loss 或流终止
- **THEN** 系统 SHALL 关闭当前 Shot
- **AND** 后续残余轨迹 SHALL 为 `shot_id = null` 的孤立段，直到下一次 confirmed/ambiguous 击球

#### Scenario: 发球播种 Shot
- **WHEN** serve 事件携带 `player_id`
- **THEN** serve 重置 SHALL 开启新 Shot
- **AND** 新 Shot 的 `hitter_player_id` SHALL 直接使用发球球员

### Requirement: Shot 归属传播
系统 SHALL 将击球归属传播到该 Shot 内的所有 segment。

#### Scenario: 多段同属一个 Shot
- **WHEN** 一次击球产生的球路被 bounce 切成两个 flight segment
- **THEN** 两个 segment SHALL 具有相同的 `shot_id` 与 `hitter_player_id`
- **AND** 后段 SHALL 记录 `ownership_source_event_id` 指向开启该 Shot 的击球事件

#### Scenario: 归属置信度随段保留
- **WHEN** 一个 Shot 内的 segment 继承归属
- **THEN** 每个 segment SHALL 携带与源击球事件一致的 `ownership_status` 与 `ownership_confidence`

### Requirement: 半场交替序列校验
系统 SHALL 在 Shot 序列上校验击球半场交替关系，作为归属的序列合理性检查。

#### Scenario: 连续同半场且证据弱
- **WHEN** 连续两次击球归属到同一半场，且当前归属置信度低于阈值或评分余量不足
- **THEN** 当前归属 SHALL 降级为 `ambiguous`
- **AND** `hitter_player_id` SHALL 置为 null

#### Scenario: 连续同半场但证据强
- **WHEN** 连续两次击球归属到同一半场，但当前归属置信度高且评分余量充足
- **THEN** 系统 SHALL 保留当前归属结论
- **AND** SHALL 在 diagnostics 中记录 `side_alternation_violation`

#### Scenario: 使用接触时刻半场
- **WHEN** 系统判断击球半场
- **THEN** 半场 SHALL 基于球员在击球接触时刻的球场位置推导
- **AND** MUST NOT 使用 roster 的 `initial_side`

### Requirement: 统计语义
系统 SHALL 提供按 `shot_id` 去重的统计语义，区分无 Shot 上下文的孤立段与有 Shot 但击球者未知的段。

#### Scenario: 总 Shot 数
- **WHEN** 系统统计球路总数
- **THEN** 总数 SHALL 为 `shot_id` 非空值去重计数
- **AND** SHALL 包含 `ownership_status` 为 unassigned 的 Shot
- **AND** SHALL NOT 包含 `shot_id = null` 的孤立段

#### Scenario: 球员击球数
- **WHEN** 系统统计某球员击球数
- **THEN** 该数 SHALL 为 `hitter_player_id == Player_N` 的 Shot 去重计数
- **AND** SHALL NOT 按 flight segment 计数

#### Scenario: 未归属 Shot 数
- **WHEN** 系统统计未归属球路
- **THEN** 该数 SHALL 为 `shot_id` 非空且 `ownership_status ∈ {ambiguous, unassigned}` 的 Shot 去重计数
