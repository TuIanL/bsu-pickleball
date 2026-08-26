## ADDED Requirements

### Requirement: Canonical Rally/Shot artifact paths and references

系统 SHALL 为 `shot-rally-events` 和 `metric-snapshot` 提供确定性的 artifact path、url、status 和 detail 引用。关联 CaptureTake 的任务 SHALL 将文件写入对应会话目录的 `analysis/<job_id>/` 下；旧任务或上传任务 SHALL 使用兼容的 `outputs/<job_id>/` 目录。`AnalysisPipelineResult.artifacts` 中的新增字段 SHALL 可选，以保持旧结果兼容。

#### Scenario: CaptureTake 任务生成事件产物

- **WHEN** 关联 CaptureTake 的 job `job-123` 生成 canonical 事件和指标快照
- **THEN** 两个文件 SHALL 位于该 take 的 `analysis/job-123/` 目录
- **AND** Pipeline result SHALL 暴露两个 artifact 的公开 url、状态和详情

#### Scenario: 旧任务保持兼容

- **WHEN** 没有 `capture_take_id` 的旧 job 生成或读取新 artifact
- **THEN** 系统 SHALL 使用 `outputs/job-123/` 下的兼容路径
- **AND** 缺少新 artifact SHALL NOT 破坏旧 tracking、pose、trajectory 或 report 请求

### Requirement: Canonical event artifact API

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受 `shot-rally-events` 和 `metric-snapshot`，并返回对应 JSON。已知但未生成的 artifact SHALL 返回 404；路径穿越、绝对路径和跨 job artifact 请求 SHALL 被拒绝。

#### Scenario: 读取可用事件产物

- **WHEN** 客户端请求已生成的 `shot-rally-events`
- **THEN** API SHALL 返回 200
- **AND** Content SHALL 是 `shot-rally-events.v1` JSON

#### Scenario: 读取未生成产物

- **WHEN** 客户端请求当前 job 尚未生成的 `metric-snapshot`
- **THEN** API SHALL 返回 404
- **AND** MUST NOT 返回 422 或模拟数据

### Requirement: Canonical event schema metadata

事件和指标 artifact SHALL 在文件和 Pipeline result 中保持 schema version、status、detail 和实际可用性一致。`available` 只允许用于文件已成功写入且 API 可读的情况；`skipped`、`unavailable` 或 `failed` 必须携带原因。

#### Scenario: 生成状态一致

- **WHEN** 事件组合阶段因缺少球员归属输入而降级
- **THEN** 文件 status、Pipeline result status 和 detail SHALL 表达同一个降级原因
- **AND** 不得仅因 path 存在就把 artifact 标记为 available

#### Scenario: 空事件结果

- **WHEN** 组合阶段成功完成但没有可确认的 Shot
- **THEN** `shot_rally_events.json` MAY 为 available 且包含空数组
- **AND** detail SHALL 说明没有确认事件，而不是省略该状态
