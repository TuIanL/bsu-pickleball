## MODIFIED Requirements

### Requirement: Coding Actions 语义命令 API

系统 MUST 提供语义级命令 API，后端在一个 SQLite 事务中完成命令日志、事件、区间投影、统一计分 FSM、自动收局和状态更新，并返回当前 CaptureTake 的完整有效投影。

#### Scenario: 执行 rally_result_a 或 rally_result_b
- **WHEN** 用户请求 coding action API
- **AND** action 为 `rally_result_a` 或 `rally_result_b`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在一个事务中关闭 rally、创建含胜方的 `rally_end`、运行对应规则 reducer、更新 `recent_results` 和 LiveCodingState
- **AND** 达到 21 分时系统 SHALL 在同一事务中自动关闭当前 game、写入最终比分并累计胜局
- **AND** 一方累计 3 个胜局时系统 SHALL 在同一事务中完成比赛

#### Scenario: 执行 rally_replay
- **WHEN** action 为 `rally_replay` 且存在 open rally
- **THEN** 系统 SHALL 关闭当前 rally 并记录 `validity=replay`
- **AND** 系统 SHALL 不改变任何计分或比赛结果字段

#### Scenario: 新规则拒绝无结果分结束
- **WHEN** take 使用 `hybrid_21_best_of_5_v1`
- **AND** 用户执行 `end_rally`
- **THEN** 系统 SHALL 拒绝该 action
- **AND** 系统 SHALL 提示必须选择 A 方胜、B 方胜或重打

#### Scenario: start_game 携带初始发球方
- **WHEN** 用户执行 `start_game`
- **AND** payload 包含 `initial_server_team`
- **THEN** 系统 SHALL 创建唯一的新 game 并初始化 0:0、发球方、每球得分阶段和右区站位

#### Scenario: revision 冲突
- **WHEN** 请求的 `expected_revision` 与当前 revision 不匹配且 `client_action_id` 为新 ID
- **THEN** 系统 SHALL 返回 409 Conflict 和权威 LiveCodingState
- **AND** 系统 SHALL 不自动重新执行该动作

### Requirement: LiveCodingState 快照管理

系统 MUST 维护实时编码状态快照，完整表达比赛阶段、比分、发球状态、胜局和比赛完成状态。

#### Scenario: 新比赛初始状态
- **WHEN** 创建新的单打或双打 match CaptureTake
- **THEN** 系统 SHALL 初始化 `score_a=0`、`score_b=0`、`games_won_a=0`、`games_won_b=0`
- **AND** `server_team` 和 `serving_side` SHALL 为 None
- **AND** `scoring_phase` SHALL 为 `rally`
- **AND** `match_status` SHALL 为 `not_started`
- **AND** `scoring_ruleset_version` SHALL 为 `hybrid_21_best_of_5_v1`

#### Scenario: API 返回完整状态
- **WHEN** 客户端获取 live state 或成功执行 coding action
- **THEN** 响应 SHALL 包含 revision、segment ordinals、match phase、比分、发球方、计分阶段、发球站位、双方胜局、比赛状态和 recent results

#### Scenario: 状态重放恢复
- **WHEN** undo 或一致性检查触发状态重建
- **THEN** 系统 SHALL 按有效命令日志恢复 segment、比分、发球状态、胜局和比赛结果

### Requirement: 完整层级状态转移规则

系统 MUST 根据比赛状态只允许合法的开局、开分和结果操作，并由制胜分自动完成局与比赛层级关闭。

#### Scenario: 等待开局
- **WHEN** 没有 open game 且比赛尚未完成
- **THEN** 系统 SHALL 允许 `start_game`
- **AND** 系统 SHALL 拒绝 `start_next_rally` 和 rally result action

#### Scenario: 等待开分
- **WHEN** 存在 open game 且不存在 open rally
- **THEN** 系统 SHALL 允许 `start_next_rally`
- **AND** 系统 SHALL 拒绝 rally result action

#### Scenario: 回合进行中
- **WHEN** 存在 open rally
- **THEN** 系统 SHALL 允许 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **AND** 系统 SHALL 拒绝重复开分或开局

#### Scenario: 比赛已结束
- **WHEN** `match_status=completed`
- **THEN** 系统 SHALL 拒绝 `start_game`、`start_next_rally` 和全部 rally result action

#### Scenario: side_change 不改比赛投影
- **WHEN** 用户执行 `change_side`
- **THEN** 系统 SHALL 不改变比分、胜局、发球方、计分阶段或 A/B 身份

### Requirement: 一键推进操作

系统 MUST 采用状态化的比赛推进流程，每一分通过一次开始操作和一次明确结果操作完成。

#### Scenario: 完成一分
- **WHEN** 用户在等待开分状态执行 `start_next_rally`
- **AND** 随后执行 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **THEN** 系统 SHALL 记录完整 rally 区间和结果
- **AND** 系统 SHALL 回到等待开分、等待下一局或比赛完成状态之一

### Requirement: 键盘快捷键

系统 MUST 让比赛快捷键服从当前状态和先发方选择流程，不得绕过 UI 可用性约束。

#### Scenario: 动态快捷键
- **WHEN** 录制中且焦点不在表单控件或弹窗内
- **THEN** `2` SHALL 在允许开局时打开初始发球方选择器
- **AND** `3` SHALL 仅在等待开分时开始下一分
- **AND** `4`、`5`、`6` SHALL 仅在回合进行中分别提交 A 方胜、B 方胜和重打
- **AND** `7`、`8`、`H`、`Backspace` SHALL 分别保持换边、暂停、重点标记和撤销语义

#### Scenario: 选择器打开时
- **WHEN** 初始发球方选择器处于打开状态
- **THEN** 比赛 action 快捷键 SHALL 不触发后台 action

### Requirement: 前端乐观更新

系统 MUST 在等待比赛 action 响应时展示 pending 状态，但不得在客户端伪造比分、发球权、胜局或比赛结果。

#### Scenario: 结果提交中
- **WHEN** 用户提交 A 方胜、B 方胜或重打并等待后端响应
- **THEN** 当前结果操作 SHALL 显示 pending
- **AND** 所有会造成冲突的比赛主操作 SHALL 暂时禁用
- **AND** 计分板 SHALL 保持最近一次权威状态

#### Scenario: 权威响应返回
- **WHEN** coding action 成功返回
- **THEN** 前端 SHALL 用完整响应替换 live state、segments 和 timeline events
- **AND** 操作区 SHALL 根据新权威状态重新派生可用动作
