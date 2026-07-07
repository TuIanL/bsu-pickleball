## MODIFIED Requirements

### Requirement: Engine remains disconnected from current pipeline
The ball trajectory and bounce engine SHALL remain independently testable while also being callable from the real analysis pipeline when ball analysis is enabled.

#### Scenario: Current analysis job runs with ball analysis disabled
- **WHEN** a real analysis job runs without ball detection enabled
- **THEN** the system MUST NOT automatically generate ball trajectory, cleaned ball trajectory, or bounce events artifacts
- **AND** existing player, pose, tracking, serve, and court-view behavior MUST remain unchanged

#### Scenario: Current analysis job runs with ball analysis enabled
- **WHEN** a real analysis job runs with ball detection enabled and usable ball candidate samples are available
- **THEN** the pipeline SHALL invoke the ball trajectory engine to produce raw trajectory samples
- **AND** the pipeline SHALL invoke trajectory cleaning before bounce detection when bounce detection is enabled

#### Scenario: Engine is used in unit tests or standalone code
- **WHEN** tests or standalone callers directly instantiate the ball trajectory and bounce engine
- **THEN** the engine SHALL run core processing logic without starting FastAPI, creating an analysis job, accessing frontend code, or loading a concrete detector model

## ADDED Requirements

### Requirement: Pipeline artifact emission
球轨迹与弹跳点引擎 SHALL 在真实 pipeline 调用时写入与 shared artifact contract 兼容的 JSON payload，并返回可供 `AnalysisPipelineResult` 引用的状态摘要。

#### Scenario: Raw and cleaned trajectory are emitted
- **WHEN** pipeline 通过引擎生成 raw samples 和 cleaned samples
- **THEN** 系统 SHALL 写入 `ball_trajectory.json` 和 `cleaned_ball_trajectory.json`
- **AND** 两个 artifact SHALL 包含 `schema_version`、`job_id`、`status`、`detail` 和坐标单位 metadata

#### Scenario: Bounce detection is enabled
- **WHEN** cleaned trajectory 可用且弹跳检测配置启用
- **THEN** 系统 SHALL 写入 `bounce_events.json`
- **AND** 没有弹跳候选时 `events` MUST 为空数组并保留 no-candidates 状态或 detail

#### Scenario: Bounce detection is disabled
- **WHEN** ball trajectory 可用但弹跳检测配置未启用
- **THEN** 系统 SHALL 跳过弹跳检测阶段
- **AND** MUST NOT 把缺失 `bounce_events.json` 解释为弹跳检测失败
