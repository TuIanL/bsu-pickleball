## ADDED Requirements

### Requirement: rally_end 事件 payload schema

系统 MUST 为 `rally_result_a`、`rally_result_b`、`rally_replay` action 自动创建的 `rally_end` 事件写入结构化的回合结果数据，以支持后续统计分析和状态重放。

#### Scenario: A 方胜的 rally_end 事件
- **WHEN** 执行 `rally_result_a` action 后自动创建 `rally_end` 事件
- **THEN** 事件的 `payload_json.winner` SHALL 为 `"A"`
- **AND** `payload_json.validity` SHALL 为 `"valid"`
- **AND** `payload_json.reason` SHALL 为 `""`

#### Scenario: B 方胜的 rally_end 事件
- **WHEN** 执行 `rally_result_b` action 后自动创建 `rally_end` 事件
- **THEN** 事件的 `payload_json.winner` SHALL 为 `"B"`
- **AND** `payload_json.validity` SHALL 为 `"valid"`

#### Scenario: 重打的 rally_end 事件
- **WHEN** 执行 `rally_replay` action 后自动创建 `rally_end` 事件
- **THEN** 事件的 `payload_json.winner` SHALL 为 `null`
- **AND** `payload_json.validity` SHALL 为 `"replay"`

#### Scenario: 可选的备注字段
- **WHEN** 用户在结果 action 中通过 payload 提供了 `reason` 字段
- **THEN** 系统 SHALL 将 `reason` 写入 `rally_end` 事件的 `payload_json.reason`
- **WHEN** 未提供 `reason`
- **THEN** `payload_json.reason` SHALL 为 `""`

### Requirement: rally_end 事件不含比分

系统 MUST 确保 `rally_end` 事件不包含 `score_after` 或 `server_after` 字段。比分由 FSM 在重放时动态推演。

#### Scenario: 事件持久化不含比分
- **WHEN** `rally_end` 事件被持久化到数据库
- **THEN** `payload_json` SHALL 不包含 `score_a`、`score_b`、`score_after`、`server_after` 字段
- **AND** 这些字段 SHALL 仅存在于 `LiveCodingState` 快照中

### Requirement: score_correction 事件

系统 MUST 在用户执行 `correct_score` action 时创建一条 `score_correction` 类型的 TimelineEvent，记录修正前后的比分差值。

#### Scenario: 修正事件包含前后比分
- **WHEN** 执行 `correct_score` action
- **THEN** 系统 SHALL 创建 `event_type` 为 `score_correction` 的 `SessionTimelineEvent`
- **AND** `payload_json` SHALL 包含 `score_before`、`score_after`、`reason` 字段
- **AND** `score_before` SHALL 为修正前的 FSM 状态快照（`{a, b, server_team}`）
- **AND** `score_after` SHALL 为修正后的目标值

### Requirement: validity 合法值

系统 MUST 限制 `rally_end` 事件的 `validity` 字段值仅为 `"valid"` 和 `"replay"`。

#### Scenario: 合法值枚举
- **WHEN** `rally_end` 事件的 `validity` 不为 `"valid"` 或 `"replay"`
- **THEN** 系统 SHALL 拒绝该 action
- **AND** 系统 SHALL 返回校验错误
