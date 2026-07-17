## ADDED Requirements

### Requirement: 纯计分 reducer 函数

系统 MUST 将单打计分逻辑实现为一个纯函数 `reduce_scoring_state(state, action)`，同时用于在线实时执行和 undo/rebuild 状态重放，保证两种路径结果一致。

#### Scenario: reducer 函数签名
- **WHEN** 调用 `reduce_scoring_state(state, action)`
- **THEN** 函数 SHALL 接受一个 ScoringState 和一个 ScoringAction
- **AND** 函数 SHALL 返回一个新的 ScoringState
- **AND** 函数 SHALL 不产生任何副作用（不写入 DB、不创建事件）

### Requirement: 单打计分状态机

系统 MUST 为单打比赛维护一个计分状态机，在每次 `rally_result_a`、`rally_result_b` 或 `rally_replay` action 执行时自动更新比分和发球权。

#### Scenario: 发球方赢球得分
- **WHEN** `server_team` 为 `"A"`
- **AND** 用户执行 `rally_result_a` action
- **THEN** 系统 SHALL 将 `score_a` 增加 1
- **AND** 系统 SHALL 保持 `server_team` 为 `"A"`

#### Scenario: 发球方输球 side out
- **WHEN** `server_team` 为 `"A"`
- **AND** 用户执行 `rally_result_b` action
- **THEN** 系统 SHALL 将 `server_team` 设为 `"B"`
- **AND** 系统 SHALL 不改变 `score_a` 和 `score_b`

#### Scenario: 接发方赢球 side out
- **WHEN** `server_team` 为 `"B"`
- **AND** 用户执行 `rally_result_a` action
- **THEN** 系统 SHALL 将 `server_team` 设为 `"A"`
- **AND** 系统 SHALL 不改变 `score_a` 和 `score_b`

#### Scenario: 重打不改比分和发球权
- **WHEN** `server_team` 为 `"A"`
- **AND** 用户执行 `rally_replay` action
- **THEN** 系统 SHALL 不改变 `server_team`、`score_a` 和 `score_b`

#### Scenario: 无 open rally 时拒绝结果 action
- **WHEN** 不存在 open rally
- **AND** 用户执行 `rally_result_a`、`rally_result_b` 或 `rally_replay` action
- **THEN** 系统 SHALL 返回错误
- **AND** 系统 SHALL 不执行任何 FSM 更新

### Requirement: FSM 初始状态

系统 MUST 在每局开始时通过 `start_game` 的 `initial_server_team` 设置初始发球方和零分状态。FSM 不接受 `server_team=None`。

#### Scenario: start_game 初始化计分状态
- **WHEN** 用户执行 `start_game` action
- **AND** payload 包含 `initial_server_team`
- **THEN** 系统 SHALL 将 `score_a` 设为 0
- **AND** 系统 SHALL 将 `score_b` 设为 0
- **AND** 系统 SHALL 将 `server_team` 设为 payload 中的值
- **AND** 系统 SHALL 清空 `recent_results`

### Requirement: FSM 重放一致性

系统 MUST 在状态重放时（如 undo 后的重建）使用与在线执行相同的 `reduce_scoring_state` 函数，确保比分状态与有效 rally result 一致。

#### Scenario: 撤销后重放
- **WHEN** 撤销一个 `rally_result_a` action
- **THEN** 系统 SHALL 从本局初始状态开始，使用纯 reducer 重放剩余有效 action
- **AND** 重放后的 `server_team`、`score_a`、`score_b` SHALL 等价于被撤销的 action 从未发生

### Requirement: 计分规则版本化

系统 MUST 在 CaptureTake 创建时根据 `match_format` 设置 `scoring_mode` 和 `scoring_ruleset_version`，双打模式显式禁用单打 FSM。

#### Scenario: 单打创建
- **WHEN** 创建新的 CaptureTake
- **AND** `match_format` 为 `singles`
- **THEN** 系统 SHALL 将 `scoring_mode` 设为 `"side_out_singles_v1"`
- **AND** 系统 SHALL 将 `scoring_ruleset_version` 设为 `"side_out_singles_v1"`

#### Scenario: 双打创建
- **WHEN** 创建新的 CaptureTake
- **AND** `match_format` 为 `doubles`
- **THEN** 系统 SHALL 将 `scoring_mode` 设为 `"manual"`
- **AND** 系统 SHALL 将 `scoring_ruleset_version` 设为 `"manual"`
- **AND** 系统 SHALL 不初始化 FSM 计分状态

#### Scenario: 双打模式不执行 FSM
- **WHEN** `scoring_mode` 为 `"manual"`
- **AND** 用户执行 `rally_result_a` 或 `rally_result_b` action
- **THEN** 系统 SHALL 仅关闭 rally 并创建 `rally_end` 事件
- **AND** 系统 SHALL 不更新 `score_a`、`score_b`、`server_team`
