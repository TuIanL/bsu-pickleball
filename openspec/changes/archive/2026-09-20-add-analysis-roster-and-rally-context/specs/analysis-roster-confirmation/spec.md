## ADDED Requirements

### Requirement: 分析前确认的不可变名册与身份锚点
系统 SHALL 在正式分析 Job 创建前提供受限 player bootstrap，允许用户确认 P1–P4、Team A/B 与初始端位，并冻结 `AnalysisRosterSnapshot`。每个确认条目 MUST 保存 `canonical_player_id`、display_name、team_id、`source_view_id`、`anchor_timestamp_ms`、`anchor_bbox`、`anchor_court_xy`、`bootstrap_run_id`、`bootstrap_model_version` 和 bootstrap_confidence。

#### Scenario: 用户确认四名球员
- **WHEN** bootstrap 返回可辨识的 P1–P4 候选
- **THEN** 系统 SHALL 展示候选参考帧与编辑入口
- **AND** 提交 Job 时 SHALL 保存不可变 roster snapshot，而非在现场 `rally_start` 创建或读取未来名册

#### Scenario: 用户跳过或候选不足
- **WHEN** 用户跳过确认或 bootstrap 不足四人
- **THEN** 普通分析 SHALL 继续可创建
- **AND** 系统 SHALL 不推断 Team A/B，并为依赖正式身份的消费者提供 unavailable reason

### Requirement: Bootstrap 到正式身份的可审计绑定
正式 tracking SHALL 为每个 roster 条目生成 `bootstrap_binding_audit`，证明 bootstrap anchor 与 formal canonical Player 的关系；绑定不成立时不得静默重新编号。

#### Scenario: 身份连续性被确认
- **WHEN** formal tracking 能将 anchor 与同一 canonical player 稳定关联
- **THEN** audit SHALL 保存 bootstrap id、formal canonical id、方法、置信度和 `confirmed` 状态

#### Scenario: 身份连续性不能确认
- **WHEN** formal tracking 无法可靠绑定某个确认条目
- **THEN** audit SHALL 记录失败或不确定状态
- **AND** 所有需要该条目正式 Team A/B 的下游能力 SHALL 为 unavailable，而不得以新编号替换
