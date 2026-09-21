## MODIFIED Requirements

### Requirement: SegmentationRun 与不可变窗口计划

系统 SHALL 为每次正式切分持久化 `MatchStateSegmentationRun`。Run MUST 关联 CaptureTake 和 planning job，并记录状态、模型/输入/sync provenance、artifact hash、unknown rate、片段数、`supersedes_run_id` 和开始/结束时间。成功或正常零回合运行 MUST 写出带 run id 与 hash 的不可变 `AnalysisWindowPlan`；若一个窗口可绑定该 Job 的 `AnalysisRallyContextSnapshot`，计划 MUST 保存 context reference/hash、binding method 和诊断。分析 Parent MUST 绑定 run id 与 plan hash，后续消费者 SHALL 仅使用该计划及其冻结 context，不得查询可变现场状态或可编辑名册。

#### Scenario: 成功运行绑定 Parent
- **WHEN** 正式切分识别出一个或多个 Rally
- **THEN** 系统 SHALL 创建 succeeded SegmentationRun、窗口计划和对应 algorithm Rally Segments
- **AND** Parent SHALL 在后续视觉执行开始前持久化该 run id 与 plan hash

#### Scenario: 上下文绑定优先级
- **WHEN** formal window 需要关联一个分析回合上下文
- **THEN** 系统 SHALL 按 `direct_segment_link`、`direct_start_event_link`、`unique_temporal_match` 的顺序选择第一个唯一有效候选
- **AND** 无直接或唯一时间关联时 SHALL 标记 context unavailable 并保存候选诊断

#### Scenario: 运行中出现新版本
- **WHEN** Job A 已绑定 Run 1，随后同一 CaptureTake 成功发布 Run 2 或产生新的 context 版本
- **THEN** Job A 的指标、事件归属和报告 SHALL 继续使用 Run 1 的窗口计划及其 context
- **AND** MUST NOT 改为查询当前最新的自动 Segment、LiveCodingState 或名册

#### Scenario: 正常零回合
- **WHEN** 模型输入有效且推理完成，但没有满足发布条件的 Rally
- **THEN** Run SHALL 记录 `valid_no_rallies`
- **AND** 窗口计划 SHALL 是显式空集合而非未设置
- **AND** 回合派生指标 SHALL 表达 `no_active_rallies`，不得将全视频当作有效比赛时间
