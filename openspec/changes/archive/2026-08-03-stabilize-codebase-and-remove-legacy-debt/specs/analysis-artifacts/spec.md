## MODIFIED Requirements

### Requirement: Pipeline result references new artifacts

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中描述会话目录内新增分析产物的 path、url、status 和 detail 字段，且所有新增字段 MUST 可选以保持旧结果兼容。可选 artifact 即使没有文件，也 SHALL 保留可解释的状态。

#### Scenario: Capture analysis result references session artifacts

- **WHEN** 录制会话的分析任务生成 artifact 文件
- **THEN** `AnalysisPipelineResult.artifacts` MUST 包含该 artifact 的逻辑引用和实际文件状态
- **AND** artifact API SHALL 通过 job_id 和 SQLite 索引解析到对应 capture 会话目录

#### Scenario: Missing capture artifact remains compatible

- **WHEN** 录制会话没有生成某个可选 artifact
- **THEN** 对应 artifact 字段 MUST 允许为 `null`
- **AND** API MUST 返回 404 而不是暴露绝对路径或返回 422
- **AND** 结果 SHALL 继续返回该 artifact 的 `status` 和 `detail`（若调用方支持）

#### Scenario: Optional artifact status is explicit

- **WHEN** pipeline 处理一个可选 artifact
- **THEN** `status` SHALL 为 `available`、`skipped`、`unavailable` 或 `failed` 之一
- **AND** `detail` SHALL 说明跳过原因、能力不可用原因或执行错误
- **AND** `available` SHALL 仅用于文件已成功写入并可通过 artifact API 读取的情况

#### Scenario: Artifact state survives missing file

- **WHEN** artifact status 为 `skipped`、`unavailable` 或 `failed` 且没有对应文件
- **THEN** `path` 和 `url` MAY 为 `null`
- **AND** `status` 与 `detail` MUST NOT 被清空或根据 `path` 重新推导为 `null`

### Requirement: Artifact API accepts new artifact names

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受新增 artifact name，并按照产物类型返回合适响应。

#### Scenario: Read generated JSON artifact

- **WHEN** 客户端请求已存在的 `ball-overlay`、`ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events`、`position-heatmaps`、`position-scatter-plots` 或 `player-render-trajectories`
- **THEN** API MUST 返回 200
- **AND** 响应 MUST 是 JSON

#### Scenario: Known artifact is not generated

- **WHEN** 客户端请求已知但当前任务未生成的新增 artifact
- **THEN** API MUST 返回 404
- **AND** MUST NOT 返回 422

#### Scenario: Existing artifact behavior is preserved

- **WHEN** 客户端请求现有 artifact name，例如 `tracking-overlay`、`pose-overlay`、`player-trajectories`、`serve-events` 或 `court-view-roi`
- **THEN** API MUST 保持现有成功和缺失文件行为
