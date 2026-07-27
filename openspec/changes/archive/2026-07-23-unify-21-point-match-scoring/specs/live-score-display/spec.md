## MODIFIED Requirements

### Requirement: 前端实时计分板

系统 MUST 在单摄和双摄比赛录制工作台显示一致的实时计分信息，包含当前局、双方胜局、当前比分、发球方、计分阶段、发球站位和最近 N 分。

#### Scenario: 单摄计分板布局
- **WHEN** 单摄 match 录制进行中
- **THEN** 系统 SHALL 在视频预览相邻区域显示完整计分板
- **AND** 计分板 SHALL 显示“第 N 局”、双方胜局、比分、发球方、计分阶段和发球站位

#### Scenario: 双摄计分界面
- **WHEN** 双摄 match 录制进行中
- **THEN** 系统 SHALL 显示包含相同权威计分字段的响应式计分栏或计分板
- **AND** 系统 SHALL NOT 显示“双打自动计分暂不可用”

#### Scenario: 比分实时更新
- **WHEN** 后端返回成功 coding action 响应
- **THEN** 计分板 SHALL 使用返回的完整 live state 更新比分、发球状态、胜局和比赛状态

#### Scenario: 计分阶段显示
- **WHEN** `scoring_phase=rally`
- **THEN** 计分板 SHALL 显示“每球得分”
- **WHEN** `scoring_phase=serve_only`
- **THEN** 计分板 SHALL 显示“发球得分”

#### Scenario: 发球站位显示
- **WHEN** match format 为单打且存在发球方
- **THEN** 计分板 SHALL 显示该方“左区发球”或“右区发球”
- **WHEN** match format 为双打且存在发球方
- **THEN** 计分板 SHALL 显示该方“左区队员发球”或“右区队员发球”

#### Scenario: 比赛完成显示
- **WHEN** `match_status=completed`
- **THEN** 计分板 SHALL 显示最终胜局比分和比赛胜方
- **AND** 系统 SHALL 不再显示开始新局或开始新分主操作

### Requirement: 每局初始发球方选择

系统 MUST 在每一局创建前要求用户选择 A 方或 B 方先发，并且只有选择后才提交 `start_game`。

#### Scenario: 打开选择器不创建局
- **WHEN** 用户点击“开始第 N 局”
- **THEN** 系统 SHALL 显示“A 方先发”和“B 方先发”选项
- **AND** 系统 SHALL NOT 立即发送 `start_game` action

#### Scenario: 确认先发方
- **WHEN** 用户选择 A 方或 B 方先发
- **THEN** 前端 SHALL 只发送一次 `start_game` action
- **AND** action payload SHALL 包含用户选择的 `initial_server_team`

#### Scenario: 取消选择
- **WHEN** 用户关闭选择器而未选择先发方
- **THEN** 系统 SHALL 不创建局、不修改比分且不增加 revision

### Requirement: 最近 N 分序列

系统 MUST 在计分板中展示最近最多 10 个 rally 结果，并明确区分有效胜负、重打和正在进行的 rally。

#### Scenario: 权威数据源
- **WHEN** 渲染最近结果
- **THEN** 数据源 SHALL 为 `live_state.recent_results`
- **AND** 已撤销结果 SHALL 不显示

#### Scenario: 结果与进行中指示
- **WHEN** recent results 包含 A 胜、B 胜或重打
- **THEN** 系统 SHALL 使用与 A/B 视觉身份一致的标记和中性重打标记按顺序显示
- **AND** 存在 open rally 时 SHALL 在末尾显示独立的进行中指示器

### Requirement: 录制前计分规则提示

系统 MUST 在 match 录制准备状态简洁展示本场采用的统一规则和稳定 A/B 身份。

#### Scenario: 规则摘要
- **WHEN** match CaptureTake 尚未开始录制
- **THEN** 系统 SHALL 显示“五局三胜 · 每局 21 分 · 20:20 后发球得分 · 21 分封顶”
- **AND** 系统 SHALL 说明 A/B 身份整场不随换边改变

## ADDED Requirements

### Requirement: 状态驱动比赛操作区

系统 MUST 根据权威比赛状态只显示或启用当前可执行的主要计分操作，并将辅助操作与主要比赛推进操作分离。

#### Scenario: 等待开局操作
- **WHEN** 比赛未完成且不存在 open game
- **THEN** 主操作区 SHALL 显示“开始第 N 局”
- **AND** 主操作区 SHALL 不显示 A 方胜、B 方胜或分结束

#### Scenario: 等待开分操作
- **WHEN** 存在 open game 且不存在 open rally
- **THEN** 主操作区 SHALL 显示“开始第 N 分”
- **AND** 主操作区 SHALL 不显示结果按钮

#### Scenario: 回合结果操作
- **WHEN** 存在 open rally
- **THEN** 主操作区 SHALL 显示尺寸一致的“A 方胜”和“B 方胜”按钮
- **AND** SHALL 显示视觉层级较弱的“重打”按钮
- **AND** SHALL 隐藏“开始下一分”和独立“分结束”按钮

#### Scenario: 辅助操作分组
- **WHEN** 渲染比赛操作区
- **THEN** 换边、战术暂停、重点标记和撤销 SHALL 位于次级操作区
- **AND** “盘开始” SHALL NOT 作为用户可见的比赛主操作

#### Scenario: pending 防重复提交
- **WHEN** 任一比赛推进 action 正在同步
- **THEN** 系统 SHALL 显示明确 pending 状态
- **AND** 系统 SHALL 禁用可能冲突或重复的主要操作直到收到权威响应
