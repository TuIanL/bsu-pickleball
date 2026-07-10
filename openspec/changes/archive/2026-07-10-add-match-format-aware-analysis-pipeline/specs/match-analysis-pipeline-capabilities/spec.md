## ADDED Requirements

### Requirement: 指标状态区分"不适用"和"未识别到"

系统 SHALL 为每个指标提供 `status` 字段，明确区分"该指标不适用"（如单打中的双打间距）和"该指标应计算但未识别到足够数据"（如双打中同侧球员不足）。

#### Scenario: 单打中 doubles_spacing 为 not_applicable

- **WHEN** `match_context.enable_doubles_spacing=False`（单打）
- **THEN** `metric_statuses["doubles_spacing"]` SHALL 为 `{"status": "not_applicable", "reason": "singles_match"}`
- **AND** `doubles_spacing: List[DoublesSpacingSummary]` SHALL 为空数组（保持类型兼容）
- **AND** 系统 SHALL NOT 调用 `doubles_spacing()` 函数

#### Scenario: 双打中 doubles_spacing 为 insufficient_players

- **WHEN** `match_context.enable_doubles_spacing=True` 但 `observed_player_count < expected_player_count`（如同侧只识别出 1 人）
- **THEN** `metric_statuses["doubles_spacing"]` SHALL 为 `{"status": "insufficient_players", "expected_player_count": 4, "observed_player_count": 3}`
- **AND** `doubles_spacing: List[DoublesSpacingSummary]` SHALL 为空数组

#### Scenario: 正常双打

- **WHEN** `match_context.enable_doubles_spacing=True` 且识别到 4 名球员
- **THEN** `metric_statuses["doubles_spacing"]` SHALL 为 `{"status": "available"}`
- **AND** `doubles_spacing: List[DoublesSpacingSummary]` SHALL 包含正常计算的间距数据

### Requirement: 报告隐藏单打不适用模块

系统 SHALL 在分析结果持久化后，使前端能通过 `match_context` 和指标 `status` 字段判断是否显示双打专属模块。

#### Scenario: 单打报告隐藏双打间距

- **WHEN** 前端渲染单打分析报告且 `doubles_spacing.status === "not_applicable"`
- **THEN** 前端 SHALL 隐藏"搭档间距"和"双打协同"等双打专属模块
- **AND** SHALL 不渲染空白的组件占位

#### Scenario: 双打报告正常显示

- **WHEN** 前端渲染双打分析报告且 `doubles_spacing.status === "available"`
- **THEN** 前端 SHALL 正常显示双打间距和配合指标

### Requirement: 任务签名包含 matchFormat

系统 SHALL 确保 matchFormat 参与分析任务签名计算，使同一视频以不同赛制提交时产生不同的任务签名和不同的分析结果。

#### Scenario: 同视频不同赛制产生不同签名

- **WHEN** 同一 `video_id` 以 `matchFormat="singles"` 创建任务
- **AND** 再以 `matchFormat="doubles"` 创建任务
- **THEN** 两个任务 SHALL 具有不同的输入签名
- **AND** SHALL 分别执行两次独立的分析

#### Scenario: 同视频同赛制复用结果

- **WHEN** 同一 `video_id` 以 `matchFormat="singles"` 提交两次
- **THEN** 第二次提交 SHALL 引用或返回原有分析结果（符合现有去重逻辑）
