# match-format-context Specification

## Purpose
定义 MatchAnalysisContext 作为比赛制式驱动的分析上下文，封装总人数、每侧人数、分侧配额和双打间距开关等稳定的比赛领域事实。

## Requirements

### Requirement: MatchAnalysisContext 统一定义分析上下文

系统 SHALL 定义 `MatchAnalysisContext` 作为比赛制式驱动的分析上下文，封装总人数、每侧人数、分侧配额和双打间距开关等稳定的比赛领域事实。`PlayerGroupProfile` 等算法内部配置由独立的 `build_player_group_profile()` 派生，不存储在 Context 中。

#### Scenario: Singles 上下文

- **WHEN** `build_match_context("singles")` 被调用
- **THEN** 返回的 MatchAnalysisContext SHALL 包含 `schema_version="match-analysis-context.v1"`、`match_format="singles"`、`expected_player_count=2`、`players_per_side=1`、`near_side_quota=1`、`far_side_quota=1`、`enable_doubles_spacing=False`
- **AND** `build_player_group_profile(ctx)` SHALL 返回 `expected_same_side_others=0`、`expected_opposite_players=1`

#### Scenario: Doubles 上下文

- **WHEN** `build_match_context("doubles")` 被调用
- **THEN** 返回的 MatchAnalysisContext SHALL 包含 `schema_version="match-analysis-context.v1"`、`match_format="doubles"`、`expected_player_count=4`、`players_per_side=2`、`near_side_quota=2`、`far_side_quota=2`、`enable_doubles_spacing=True`
- **AND** `build_player_group_profile(ctx)` SHALL 返回 `expected_same_side_others=1`、`expected_opposite_players=2`

#### Scenario: 历史任务缺失 matchFormat

- **WHEN** `build_match_context(None)` 被调用（历史任务字段缺失）
- **THEN** 返回的 MatchAnalysisContext SHALL 等同于 doubles 上下文
- **AND** 函数 SHALL NOT 抛出验证错误
- **AND** 系统 SHALL 写入 `{"event": "match_format_defaulted", "reason": "legacy_job_missing_match_format", "default": "doubles"}` 兼容诊断

#### Scenario: 新请求传入非法 matchFormat

- **WHEN** 新 API 请求传入 `matchFormat="single"` 或 `matchFormat="double"`
- **THEN** API schema 的 Literal 校验 SHALL 在进入 `build_match_context` 前返回 422 验证错误
- **AND** 不默认为 doubles

#### Scenario: 禁止客户端直接指定 player_count

- **WHEN** 客户端通过 API 创建任务时在请求中额外包含 `playerCount` 或 `expected_player_count` 字段
- **THEN** 后端 SHALL 忽略该字段
- **AND** 仅通过 `metadata.matchFormat` 派生产出人数

### Requirement: Worker 将上下文传入 Pipeline

系统 SHALL 在 Worker 执行分析任务时从任务元数据提取 `matchFormat`，构造 `MatchAnalysisContext`，并传递给 `AnalysisPipeline.run()`。

#### Scenario: Worker 构造上下文

- **WHEN** `AnalysisWorker._execute(job)` 处理一个 `matchFormat="singles"` 的任务
- **THEN** Worker SHALL 在当前方法中调用 `build_match_context("singles")`
- **AND** 将结果作为 `match_context` 关键字参数传递给 `pipeline.run()`

#### Scenario: Pipeline 接收并传递上下文

- **WHEN** `AnalysisPipeline.run()` 收到非空的 `match_context`
- **THEN** Pipeline SHALL 将 `match_context` 传递给 `_run_tracking()`
- **AND** SHALL 在 `_compute_metrics()` 中使用 `match_context.enable_doubles_spacing` 决定是否计算 `doubles_spacing`

#### Scenario: 旧版本兼容

- **WHEN** `AnalysisPipeline.run()` 被旧版本调用方调用且未传入 `match_context`
- **THEN** Pipeline SHALL 使用 doubles 的默认 MatchAnalysisContext（向后兼容）

### Requirement: 分析结果持久化 match_context

系统 SHALL 在分析结果和球员轨迹 artifact 中保存比赛的 expected/observed player count，使前端不依赖元数据即可判断赛制和识别完整性。

#### Scenario: Result 携带 match_context

- **WHEN** 单打分析完成
- **THEN** `AnalysisPipelineResult` SHALL 包含 `match_context` 及其 `match_format`、`expected_player_count`、`players_per_side`
- **AND** SHALL 包含 `observed_player_count`（实际出现在 tracking artifact 中的不同 player_id 数量）

#### Scenario: Player trajectory 携带 match_context

- **WHEN** 单打分析生成 `players_trajectory.json`
- **THEN** artifact SHALL 包含 `match_context` 节点
- **AND** SHALL 包含 `player_ids` 数组，列出实际存在的球员身份（如 `["Player_1", "Player_2"]`）

#### Scenario: 前端区分不同识别状态

- **WHEN** `expected_player_count=2` 且 `observed_player_count=2`
- **THEN** 前端 SHALL 判定为正常单打

- **WHEN** `expected_player_count=2` 且 `observed_player_count=1`
- **THEN** 前端 SHALL 判定为单打识别不完整并展示提示

- **WHEN** `expected_player_count=4` 且 `observed_player_count=2`
- **THEN** 前端 SHALL 判定为双打识别不完整并展示提示
