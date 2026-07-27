## ADDED Requirements

### Requirement: 纯计分 reducer 函数

系统 MUST 将单打和双打共用的计分逻辑实现为纯函数 `reduce_scoring_state(state, action)`，同时用于在线实时执行和 undo/rebuild 状态重放，保证两种路径结果一致。

#### Scenario: reducer 函数签名
- **WHEN** 调用 `reduce_scoring_state(state, action)`
- **THEN** 函数 SHALL 接受一个包含比分、发球方、计分阶段和胜局投影的 ScoringState，以及一个 ScoringAction
- **AND** 函数 SHALL 返回新的 ScoringState 和局/场结束派生结果
- **AND** 函数 SHALL 不产生任何副作用（不写入 DB、不创建事件）

### Requirement: 单打计分状态机

系统 MUST 为单打和双打比赛维护统一的 21 分混合计分状态机，在每次 `rally_result_a`、`rally_result_b` 或 `rally_replay` action 执行时自动更新比分、发球权、计分阶段、发球站位和比赛结果。

#### Scenario: 每球得分阶段 A 方赢球
- **WHEN** `scoring_phase` 为 `rally`
- **AND** 用户执行 `rally_result_a` action
- **THEN** 系统 SHALL 将 `score_a` 增加 1
- **AND** 系统 SHALL 将 `server_team` 设为 `A`
- **AND** 系统 SHALL 根据 A 方新比分更新 `serving_side`

#### Scenario: 每球得分阶段 B 方赢球
- **WHEN** `scoring_phase` 为 `rally`
- **AND** 用户执行 `rally_result_b` action
- **THEN** 系统 SHALL 将 `score_b` 增加 1
- **AND** 系统 SHALL 将 `server_team` 设为 `B`
- **AND** 系统 SHALL 根据 B 方新比分更新 `serving_side`

#### Scenario: 发球得分阶段发球方赢球
- **WHEN** `scoring_phase` 为 `serve_only`
- **AND** rally 胜方等于 `server_team`
- **THEN** 系统 SHALL 仅为发球方增加 1 分
- **AND** 系统 SHALL 保持发球方不变

#### Scenario: 发球得分阶段接发方赢球
- **WHEN** `scoring_phase` 为 `serve_only`
- **AND** rally 胜方不等于 `server_team`
- **THEN** 系统 SHALL 不改变双方比分
- **AND** 系统 SHALL 将 rally 胜方设为下一发球方

#### Scenario: 重打不改计分状态
- **WHEN** 用户执行 `rally_replay` action
- **THEN** 系统 SHALL 不改变发球方、比分、计分阶段、发球站位、胜局或比赛状态

#### Scenario: 无 open rally 时拒绝结果 action
- **WHEN** 不存在 open rally
- **AND** 用户执行 `rally_result_a`、`rally_result_b` 或 `rally_replay` action
- **THEN** 系统 SHALL 返回错误
- **AND** 系统 SHALL 不执行任何 FSM 更新

### Requirement: FSM 初始状态

系统 MUST 在每局开始时通过 `start_game.initial_server_team` 设置本局初始发球方、零分状态、每球得分阶段和右区发球站位。FSM 不接受缺失的初始发球方。

#### Scenario: start_game 初始化计分状态
- **WHEN** 用户执行 `start_game` action
- **AND** payload 包含合法的 `initial_server_team`
- **THEN** 系统 SHALL 将 `score_a` 和 `score_b` 设为 0
- **AND** 系统 SHALL 将 `server_team` 设为 payload 中的值
- **AND** 系统 SHALL 将 `scoring_phase` 设为 `rally`
- **AND** 系统 SHALL 将 `serving_side` 设为 `right`
- **AND** 系统 SHALL 清空 `recent_results`

#### Scenario: 初始发球方缺失
- **WHEN** 新规则 take 的 `start_game` payload 未包含合法的 `initial_server_team`
- **THEN** 系统 SHALL 拒绝该 action
- **AND** 系统 SHALL 不创建 game segment 或修改 revision

### Requirement: FSM 重放一致性

系统 MUST 在状态重放时使用与在线执行相同且由 `scoring_ruleset_version` 选择的 reducer，恢复比分、发球权、计分阶段、站位、胜局和比赛状态。

#### Scenario: 撤销普通 rally result
- **WHEN** 用户撤销一个有效 rally result action
- **THEN** 系统 SHALL 从有效 action 日志重放状态
- **AND** 重放投影 SHALL 等价于被撤销 action 从未发生

#### Scenario: 撤销制胜分
- **WHEN** 用户撤销一个曾使当前局或比赛结束的 rally result action
- **THEN** 系统 SHALL 恢复该 rally 之前的比分与比赛状态
- **AND** 系统 SHALL 撤销对应的 game/set 结束投影和胜局累计
- **AND** 系统 SHALL 允许继续当前局

### Requirement: 计分规则版本化

系统 MUST 为新的单打和双打 match CaptureTake 使用 `hybrid_21_best_of_5_v1`，并继续按历史 take 已保存的规则版本读取与重放。

#### Scenario: 新单打比赛创建
- **WHEN** 创建 `match_format=singles` 的新 match CaptureTake
- **THEN** `scoring_mode` 和 `scoring_ruleset_version` SHALL 均为 `hybrid_21_best_of_5_v1`
- **AND** 系统 SHALL 初始化统一 FSM 投影

#### Scenario: 新双打比赛创建
- **WHEN** 创建 `match_format=doubles` 的新 match CaptureTake
- **THEN** `scoring_mode` 和 `scoring_ruleset_version` SHALL 均为 `hybrid_21_best_of_5_v1`
- **AND** 系统 SHALL 初始化与单打相同的计分 FSM 投影

#### Scenario: 历史规则兼容
- **WHEN** 系统读取或重放规则版本为 `side_out_singles_v1` 或 `manual` 的历史 CaptureTake
- **THEN** 系统 SHALL 保持该历史版本原有语义
- **AND** 系统 SHALL NOT 将历史结果按新规则重新计分

### Requirement: Vidat 修正的比赛状态重放

系统 MUST 使用 CaptureTake 已保存的 `scoring_ruleset_version` 重放已确认 Vidat 导入得到的回合结果和比分锚点，生成一致的比分、胜局和比赛胜者投影。

#### Scenario: 导入回合结果后重放
- **WHEN** 确认的 Vidat 导入包含有效的 rally 结果变更
- **THEN** 系统 SHALL 从该 CaptureTake 的语义动作序列重放计分状态
- **AND** LiveCodingState、TimelineEvent 与报告可见的最终比赛结果 SHALL 与重放结果一致
