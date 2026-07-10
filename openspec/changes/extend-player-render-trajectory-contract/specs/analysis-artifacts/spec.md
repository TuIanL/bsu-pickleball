## MODIFIED Requirements

### Requirement: Artifact API accepts new artifact names

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受新增 artifact name，并按照产物类型返回合适响应。

#### Scenario: Read generated JSON artifact

- **WHEN** 客户端请求已存在的 `ball-overlay`、`ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events`、`position-heatmaps`、`position-scatter-plots` 或 `player-render-trajectories`
- **THEN** API MUST 返回 200
- **AND** 响应 MUST 是 JSON

### Requirement: Pipeline result references new artifacts

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中描述新增分析产物的 path、url、status 和 detail 字段，且所有新增字段 MUST 可选以保持旧结果兼容。

#### Scenario: Completed result can reference player render trajectory artifact

- **WHEN** 分析任务生成 `player_render_trajectory.json`
- **THEN** `AnalysisPipelineResult.artifacts` MUST 包含 `player_render_trajectory_url` 字段
- **AND** MUST 包含 `player_render_trajectory_status` 字段
- **AND** MUST 包含 `player_render_trajectory_detail` 字段

#### Scenario: Completed result remains compatible without render trajectory

- **WHEN** 分析任务未生成 `player_render_trajectory.json`
- **THEN** `player_render_trajectory_url` MUST 允许为 null
- **AND** 现有 artifact 字段 MUST 不被移除或重命名

## ADDED Requirements

### Requirement: Deterministic render trajectory artifact path

系统 SHALL 为 `player_render_trajectory.json` 提供确定性的本地存储路径。

#### Scenario: Resolve render trajectory artifact path

- **WHEN** 后端为任务 `job-123` 解析 render trajectory artifact 路径
- **THEN** `player-render-trajectories` MUST 映射到 `outputs/job-123/player_render_trajectory.json`
