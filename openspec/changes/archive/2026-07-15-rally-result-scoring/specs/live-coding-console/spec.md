## MODIFIED Requirements

### Requirement: Coding Actions 语义命令 API

系统 MUST 提供语义级命令 API，后端在一个 SQLite 事务中完成命令日志、事件、区间投影、计分状态机和状态更新，并返回当前 CaptureTake 的完整有效投影。

**修改内容**: 新增三种结果 action 类型（`rally_result_a`、`rally_result_b`、`rally_replay`），match + singles 模式下替代 `end_rally`；新增 `correct_score` action 类型；`start_game` 新增 `initial_server_team` payload。每个 result action 在同一事务内完成段操作、比分 FSM 和状态更新。`end_rally` 作为后端合法 action 保留。

#### Scenario: 执行 rally_result_a action
- **WHEN** 用户请求 `POST /api/capture-takes/{id}/coding-actions`
- **AND** `action` 为 `rally_result_a`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在一个事务内完成：
  - 关闭 open rally segment，创建 `rally_end` 事件（payload 含 `winner:"A"`、`validity:"valid"`）
  - 关闭当前间歇（如果有）
  - 创建 `non_play_start` 事件（`intermission_kind: "between_rallies"`）
  - 执行 FSM reducer：发球方为 A 时 `score_a` 加 1；发球方为 B 时 side out
  - push 到 `recent_results` 尾部
  - 更新 `LiveCodingState` 的 `score_a`、`server_team`、`match_phase`、`recent_results` 等字段
  - 更新 `CaptureTake.revision`

#### Scenario: 执行 rally_result_b action
- **WHEN** `action` 为 `rally_result_b`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在同一事务内完成 rally 关闭、`rally_end` 事件创建（`winner:"B"`）、FSM 更新（发球方赢则加分，接发方赢则 side out）

#### Scenario: 执行 rally_replay action
- **WHEN** `action` 为 `rally_replay`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在同一事务内完成 rally 关闭、`rally_end` 事件创建（`validity:"replay"`）
- **AND** FSM SHALL 不改变 `score_a`、`score_b` 和 `server_team`
- **AND** `recent_results` SHALL push `{"validity": "replay"}`

#### Scenario: 无 open rally 时结果 action 返回错误
- **WHEN** 不存在 open rally
- **AND** 用户执行 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **THEN** 系统 SHALL 返回错误
- **AND** 系统 SHALL 不执行 FSM 更新

#### Scenario: 执行 correct_score action
- **WHEN** `action` 为 `correct_score`
- **AND** payload 包含 `score_a`、`score_b`、`server_team`
- **THEN** 系统 SHALL 将 `LiveCodingState` 的 `score_a`、`score_b`、`server_team` 设为 payload 中的值
- **AND** 系统 SHALL 不创建或关闭任何 `CaptureSegment` 或段相关 `TimelineEvent`
- **AND** 系统 SHALL 创建一条 `score_correction` 类型的 TimelineEvent

#### Scenario: start_game 携带初始发球方
- **WHEN** 用户执行 `start_game` action
- **AND** payload 包含 `initial_server_team`
- **THEN** 系统 SHALL 在现有段操作之外额外执行：
  - `score_a` = 0
  - `score_b` = 0
  - `server_team` = `payload.initial_server_team`
  - `recent_results` = []

### Requirement: LiveCodingState 快照管理

系统 MUST 维护 CaptureTake 的实时编码状态快照，每次成功 action 在同一事务内更新，并显式表达比赛阶段、间歇原因、计分状态和计分模式。

**修改内容**: `LiveCodingState` 新增 `server_team`、`score_a`、`score_b`、`scoring_mode`、`scoring_ruleset_version`、`recent_results` 字段；`start_game` 初始化比分和发球方。

#### Scenario: 初始状态
- **WHEN** 创建新的 CaptureTake
- **AND** `match_format` 为 `singles`
- **THEN** 系统 SHALL 初始化 LiveCodingState：
  - `set_ordinal` = 0, `game_ordinal` = 0, `rally_ordinal` = 0
  - `match_phase` = `idle`, `intermission_kind` = None
  - `score_a` = 0, `score_b` = 0, `server_team` = None
  - `scoring_mode` = `"side_out_singles_v1"`
  - `scoring_ruleset_version` = `"side_out_singles_v1"`
  - `recent_results` = []

#### Scenario: 双打初始状态
- **WHEN** 创建新的 CaptureTake
- **AND** `match_format` 为 `doubles`
- **THEN** 系统 SHALL 将 `scoring_mode` 设为 `"manual"`
- **AND** `scoring_ruleset_version` 设为 `"manual"`
- **AND** 不初始化计分相关字段

#### Scenario: 响应包含计分状态
- **WHEN** 执行任何 coding action 成功后返回 `live_state`
- **THEN** 响应 SHALL 包含 `score_a`、`score_b`、`server_team`、`scoring_mode`、`scoring_ruleset_version`、`recent_results`
- **AND** 前端 SHALL 以这些字段为准更新计分板显示

### Requirement: 完整层级状态转移规则

系统 MUST 根据完整的状态转移表执行层级关闭、开分、间歇操作和计分状态机更新。

**修改内容**: match + singles 模式下 `end_rally` 被三种结果 action 替代；`side_change` 额外要求不改变比分和发球方；双打模式不执行 FSM。

#### Scenario: rally_result_a 关闭当前分并进入间歇
- **WHEN** `match_phase` 为 `rally_active`
- **AND** 执行 `rally_result_a` action
- **THEN** 系统 SHALL 关闭 open rally 并创建 `rally_end` 事件（`payload.winner="A"`）
- **AND** 系统 SHALL 创建 `intermission_kind` 为 `between_rallies` 的 `non_play_start` 事件
- **AND** 系统 SHALL 将 `match_phase` 设为 `intermission`
- **AND** 系统 SHALL 执行 FSM 计分和发球权更新

#### Scenario: side_change 不改比分和发球权
- **WHEN** 执行 `change_side` action
- **THEN** 系统 SHALL 不改变 `score_a`、`score_b`、`server_team`
- **AND** A/B 身份 SHALL 保持不变

#### Scenario: start_next_rally 后比分不变
- **WHEN** 执行 `start_next_rally` action
- **THEN** 系统 SHALL 不改变 `score_a`、`score_b`、`server_team` 和 `recent_results`
- **AND** FSM 状态 SHALL 保持不动

### Requirement: 一键推进操作

**修改内容**: 新增 "分开始后再点结果按钮" 的配搭操作模式。

#### Scenario: 比分模式下的一分两击
- **WHEN** 比赛录制中
- **AND** 用户点击 `start_next_rally` 开分
- **AND** 用户随后点击 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **THEN** 系统 SHALL 记录该分结果并更新计分状态
- **AND** 每分必须经过"分开始"和"结果按钮"两次操作

### Requirement: 键盘快捷键

**修改内容**: 新增三个结果按钮和修正比分的快捷键映射。

#### Scenario: 快捷键映射
- **WHEN** 录制中且焦点不在 input/textarea/select，且无弹窗
- **THEN** 系统 SHALL 响应以下快捷键：
  - `1` → 开始新盘
  - `2` → 开始新局
  - `3` → 开始下一分
  - `4` → A 方胜
  - `5` → B 方胜
  - `6` → 重打
  - `7` → 换边
  - `8` → 战术暂停
  - `H` → 重点片段
  - `Backspace` → 撤销

### Requirement: 前端乐观更新

**修改内容**: 前端在等待 `rally_result_*` 响应时，乐观显示计分板 pending 状态而非伪造比分。

#### Scenario: 结果按钮 pending 状态
- **WHEN** 用户点击 `rally_result_a`
- **AND** 等待后端响应期间
- **THEN** 前端 SHALL 将结果按钮展示为 pending 状态（禁用、旋转动画或透明度变化）
- **AND** 前端 SHALL 不自行增加比分或改变发球方显示
- **AND** 计分板 SHALL 保持之前的状态

#### Scenario: 结果确认后计分板同步
- **WHEN** 收到后端成功响应
- **THEN** 前端 SHALL 以后端返回的 `live_state.score_a`、`score_b`、`server_team`、`recent_results` 更新计分板
- **AND** 前端 SHALL 释放按钮的 pending 状态
