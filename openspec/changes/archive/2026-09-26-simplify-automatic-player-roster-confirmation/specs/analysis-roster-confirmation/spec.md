## MODIFIED Requirements

### Requirement: 分析前确认的不可变名册与身份锚点
系统 SHALL 在正式分析 Job 创建前提供受限 player bootstrap，默认直接展示自动生成的 P1–P4 候选人物卡片与参考画面，允许用户确认或纠正候选与 P 槽位的映射，并确认 Team A/B 与初始端位，随后冻结 `AnalysisRosterSnapshot`。单打 SHALL 展示 P1–P2。每个确认条目 MUST 保存用户 P 槽位、来源 `candidate_id`（手工候选除外）、`canonical_player_id`、可为空的 `display_name`、`team_id`、`source_view_id`、`anchor_timestamp_ms`、`anchor_bbox`、可用时的 `anchor_court_xy`、`bootstrap_run_id`、`bootstrap_model_version` 和 bootstrap_confidence；用于绑定的画面与外观证据 SHALL 随 Job 保持可追溯。正式 Team A/B 与初始端位 MUST 由用户确认，不得只按画面位置自动定案。

#### Scenario: 用户确认四名球员
- **WHEN** bootstrap 返回四名可辨识的双打候选
- **THEN** 系统 SHALL 直接显示四张带 P1–P4 标签的人物卡片与可核对的参考画面，不要求用户先播放、截帧或逐人画框
- **AND** 用户确认 Team A/B、初始端位并提交 Job 时 SHALL 保存不可变 roster snapshot，而非在现场 `rally_start` 创建或读取未来名册

#### Scenario: 用户纠正 P 映射
- **WHEN** 用户发现某候选被放进错误 P 槽位并交换或替换候选
- **THEN** 系统 SHALL 同步更新卡片、参考画面标签与待冻结的候选到 P 映射，且同一候选 MUST NOT 占据两个 P 槽位

#### Scenario: 自动候选不足
- **WHEN** bootstrap 只可靠识别出部分球员
- **THEN** 系统 SHALL 保留可用卡片并指出未完成槽位，提供重新选帧和手工框选入口；自动证据不足时不得展示伪造的人物裁剪图

#### Scenario: 用户跳过或候选不足
- **WHEN** 用户跳过确认或 bootstrap 不足预期人数
- **THEN** 普通分析 SHALL 继续可创建
- **AND** 系统 SHALL 不推断正式 Team A/B，并为依赖正式身份的消费者提供 unavailable reason

#### Scenario: 第一阶段仅确认 P 身份
- **WHEN** 用户确认 P 槽位但未填写真实姓名
- **THEN** 系统 SHALL 始终显示 P 编号，并允许 `display_name` 为空；真实姓名不得成为本次任务的提交条件

### Requirement: Bootstrap 到正式身份的可审计绑定
正式 tracking SHALL 为每个 roster 条目生成 `bootstrap_binding_audit`，在锚点对应的机位和时间窗口内，以实际轨迹观测建立唯一的用户 P 槽位到 formal canonical Player 映射。核验 SHALL 综合可用的 bbox、球场位置、衣着外观及跨机位证据并记录各项来源、匹配质量与冲突原因；仅凭同名编号、全片任意时刻的位置相近或单一低质量外观证据 MUST NOT 标记为 `confirmed`。绑定不成立时不得静默重新编号；依赖 P 到正式身份映射的下游能力 SHALL 按该槽位降级，而非使用未经确认的编号。

#### Scenario: 身份连续性被确认
- **WHEN** formal tracking 在锚点时间附近找到与用户确认候选唯一匹配的正式球员观测
- **THEN** audit SHALL 保存用户 P 槽位、bootstrap id、formal canonical id、方法、证据、置信度和 `confirmed=true`
- **AND** 依赖身份的画面标记、报告与 Team A/B 指标 SHALL 使用经确认的映射解析该 P 槽位

#### Scenario: 身份连续性不能确认
- **WHEN** formal tracking 无法在锚点附近可靠绑定某个确认条目，或两个槽位竞争同一正式球员
- **THEN** audit SHALL 记录失败或不确定状态及原因
- **AND** 所有需要该条目正式 Team A/B 的下游能力 SHALL 为 unavailable，而不得以新编号替换

#### Scenario: 仅有宽松位置或编号相同
- **WHEN** 候选与正式轨迹只在全片其他时间接近，或仅具有相同的 `Player_N` 字符串
- **THEN** audit MUST NOT 将该条目标记为已确认
