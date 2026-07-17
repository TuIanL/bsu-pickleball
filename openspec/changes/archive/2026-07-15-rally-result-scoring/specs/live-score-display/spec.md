## ADDED Requirements

### Requirement: 前端实时计分板

系统 MUST 在视频预览右侧固定区域显示实时计分板，包含盘号、局号、比分、发球方、初始发球方选择和最近 N 分序列。

#### Scenario: 计分板布局
- **WHEN** 录制进行中或已完成
- **THEN** 系统 SHALL 在视频预览右侧显示计分板组件
- **AND** 计分板 SHALL 包含 `ScoreHeader`（当前盘号、局号）
- **AND** 计分板 SHALL 包含 `ScoreDisplay`（A 方得分、B 方得分、发球方指示器）
- **AND** 计分板 SHALL 包含 `RecentPoints`（最近最多 10 分的胜负序列小方块）

#### Scenario: 比分实时更新
- **WHEN** 用户执行 `rally_result_a` 或 `rally_result_b` action
- **AND** 后端返回权威 `live_state`
- **THEN** 计分板 SHALL 立即以服务端返回的 `score_a`、`score_b`、`server_team`、`recent_results` 为准更新显示

#### Scenario: 发球方指示器
- **WHEN** `live_state.server_team` 为 `"A"`
- **THEN** 计分板 SHALL 在 A 方一侧显示发球标记（如实心圆点 ●）
- **WHEN** `live_state.server_team` 为 `"B"`
- **THEN** 计分板 SHALL 在 B 方一侧显示发球标记

#### Scenario: A/B 标签稳定
- **WHEN** 用户执行 `side_change` action
- **THEN** 计分板的 A 方/B 方标签 SHALL 不变
- **AND** 计分板的 `score_a`、`score_b` SHALL 不变
- **AND** 发球方指示器 SHALL 不变

#### Scenario: 双打模式隐藏计分板
- **WHEN** `scoring_mode` 为 `"manual"`
- **THEN** 系统 SHALL 隐藏自动计分板区域
- **AND** 系统 SHALL 显示提示 "当前双打自动计分暂不可用"

### Requirement: 每局初始发球方选择

系统 MUST 在 `start_game` 操作时（或之前）提供一个初始发球方选择器，允许用户指定本局首轮发球方。

#### Scenario: 初始发球方选择器
- **WHEN** 用户点击"局开始"按钮
- **THEN** 系统 SHALL 显示初始发球方选择弹窗或内联控件
- **AND** 选择器 SHALL 包含两个选项："A 方先发"和"B 方先发"
- **AND** 默认值 SHALL 继承上一局的选择（第一局默认为 A）
- **AND** 用户确认后，`start_game` action 的 payload 中 SHALL 包含 `initial_server_team`
- **AND** 选择器 SHALL NOT 在非 match 模式下显示

### Requirement: 最近 N 分序列

系统 MUST 在计分板中展示最近 10 分的胜负序列，以彩色小方块的形式直观呈现实时的 momentum。

#### Scenario: 数据源为 live_state.recent_results
- **WHEN** 渲染 RecentPoints
- **THEN** 数据源 SHALL 为 `live_state.recent_results` 数组
- **AND** 前端 SHALL NOT 直接遍历原始 `timelineEvents`
- **AND** 已撤销的 rally result SHALL 不在 `recent_results` 中（后端在 undo 时 pop）

#### Scenario: 最近 N 分显示
- **WHEN** `recent_results` 非空
- **THEN** 每个小方块 SHALL 按顺序从左到右排列
- **AND** `winner=A` 的方块显示为绿色；`winner=B` 显示为蓝色；重打显示为灰色

#### Scenario: 活跃分 pending indicator
- **WHEN** 存在 open rally segment
- **THEN** RecentPoints 序列末尾 SHALL 渲染一个独立的空心闪烁方块
- **AND** 该方块 SHALL 不与最后一个已完成结果重叠

#### Scenario: 不足 10 分时不补齐
- **WHEN** 当前仅有 3 条 `recent_results`
- **THEN** 最近 N 分序列 SHALL 只显示 3 个方块
- **AND** 剩余 7 个位置 SHALL 留空

### Requirement: 录制前计分规则提示

系统 MUST 在录制控制台的非录制状态下显示计分规则提示，让用户理解 A/B 方的认定逻辑和换边规则。

#### Scenario: 规则提示显示
- **WHEN** 场次模式为 `match`
- **AND** 当前 phase 为 `idle`
- **THEN** 系统 SHALL 在事件按钮区域上方或计分板区域显示提示文本
- **AND** 提示 SHALL 说明：
  - "A 方 = 第 1 局优先选择发球的队伍"
  - "B 方 = 对方队伍"
  - "A/B 身份整场比赛不变，换边不改比分"
