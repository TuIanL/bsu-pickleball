## ADDED Requirements

### Requirement: 比分修正锚点

系统 MUST 支持 `correct_score` coding action，允许用户在 FSM 推演出错时注入修正锚点。重放时 FSM 以修正锚点为准，后续 rally 从锚点继续推演。

#### Scenario: 执行比分修正
- **WHEN** 用户执行 `correct_score` action
- **AND** action 的 payload 包含 `score_a`、`score_b`、`server_team`
- **THEN** 系统 SHALL 将 `LiveCodingState` 的 `score_a`、`score_b`、`server_team` 设为 payload 中的值
- **AND** 系统 SHALL 不改变 `set_ordinal`、`game_ordinal`、`rally_ordinal` 等段管理字段
- **AND** 系统 SHALL 创建一条 `score_correction` 类型的 `SessionTimelineEvent`

#### Scenario: 修正锚点在 reducer 中的行为
- **WHEN** `reduce_scoring_state` 遇到 action 类型为 `correct_score`
- **THEN** reducer SHALL 忽略当前 state 中的 `score_a`、`score_b`、`server_team`
- **AND** reducer SHALL 直接返回以 payload 值构造的新 ScoringState

#### Scenario: 修正后重放从锚点继续
- **WHEN** 重放 action 序列重建 FSM 状态
- **AND** 遇到 `correct_score` action
- **THEN** reducer SHALL 将当前状态直接设为修正锚点的值
- **AND** 后续 `rally_result_*` action SHALL 从锚点状态继续推演

### Requirement: 修正锚点不涉及段管理

系统 MUST 确保 `correct_score` action 不操作任何段相关的数据。

#### Scenario: 修正不创建段事件
- **WHEN** 执行 `correct_score` action
- **THEN** 系统 SHALL 不创建或关闭任何 `CaptureSegment`
- **AND** 系统 SHALL 不创建 `rally_start`、`rally_end`、`non_play_start`、`non_play_end` 等段相关的 TimelineEvent

### Requirement: 修正锚点可撤销

系统 MUST 允许撤销 `correct_score` action，撤销后 FSM 通过重放恢复到本次修正之前的状态。

#### Scenario: 撤销修正
- **WHEN** 执行 undo 撤销一个 `correct_score` action
- **THEN** 系统 SHALL 通过重放修正之前的所有有效 action 重建 FSM 状态
- **AND** 系统 SHALL 标记被撤销的 `score_correction` 事件为 `is_undone=true`

### Requirement: 修正排序按 revision

系统 MUST 在重放时按 `revision`（或 `sequence_number`）排序 action，而非按 `timestamp_ms`。

#### Scenario: 同时间戳多个修正
- **WHEN** 多个 `correct_score` action 具有相同的 `timestamp_ms`
- **THEN** 重放时 SHALL 按 `revision` 升序执行
- **AND** 最终状态 SHALL 以 `revision` 最大的修正为准

### Requirement: Vidat 比分锚点映射
系统 MUST 将 Vidat 中有效的比分修正标注转换为 `correct_score` 语义动作，并按既有修正锚点规则参与状态重放。

#### Scenario: 导入比分修正
- **WHEN** 确认的 Vidat 标注包含 score correction 及合法的 A/B 分数和发球方
- **THEN** 系统 SHALL 创建可审计的 `correct_score` 语义动作
- **AND** 后续回合 SHALL 从该锚点重放
