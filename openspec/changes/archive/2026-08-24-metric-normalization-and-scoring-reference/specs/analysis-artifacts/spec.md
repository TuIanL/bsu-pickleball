## ADDED Requirements

### Requirement: Normalized metric artifact paths and references

系统 SHALL 为 `normalized-metrics` 提供确定性的 artifact path、url、status 和 detail 引用。关联 CaptureTake 的任务 SHALL 将文件写入对应会话目录的 `analysis/<job_id>/normalized_metrics.json`；旧任务或上传任务 SHALL 使用兼容的 `outputs/<job_id>/normalized_metrics.json`。`AnalysisPipelineResult.artifacts` 中的新增字段 SHALL 可选，以保持旧结果兼容。

#### Scenario: CaptureTake 任务生成 normalized artifact

- **WHEN** 关联 CaptureTake 的 job `job-123` 生成 normalized metric snapshot
- **THEN** 文件 SHALL 位于该 take 的 `analysis/job-123/normalized_metrics.json`
- **AND** Pipeline result SHALL 暴露公开 url、status、detail 和可选 path

#### Scenario: 旧任务保持兼容

- **WHEN** 没有 `capture_take_id` 的旧 job 读取或生成 normalized artifact
- **THEN** 系统 SHALL 使用 `outputs/job-123/normalized_metrics.json`
- **AND** 缺少该可选 artifact SHALL NOT 破坏旧 tracking、trajectory、report 或 insights 请求

### Requirement: Normalized metric artifact API

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受 `normalized-metrics`，并返回 `normalized-metric-snapshot.v1` JSON。已知但未生成的 artifact SHALL 返回 404；绝对路径、路径穿越和跨 job artifact 请求 SHALL 被拒绝。

#### Scenario: 读取可用 normalized artifact

- **WHEN** 客户端请求已生成的 `normalized-metrics`
- **THEN** API SHALL 返回 200
- **AND** response SHALL 是 `normalized-metric-snapshot.v1` JSON

#### Scenario: 读取未生成 normalized artifact

- **WHEN** 当前 job 没有生成 normalized artifact
- **THEN** API SHALL 返回 404
- **AND** MUST NOT 返回 422、默认分数或模拟数据

### Requirement: Normalized artifact state consistency

normalized artifact 文件、Pipeline result 和 API 可用性 SHALL 保持 schema version、status、detail 和实际文件状态一致。`available` 只允许用于文件成功写入且 API 可读的情况；`skipped`、`unavailable` 或 `failed` SHALL 携带原因。

#### Scenario: 参考 profile 缺失

- **WHEN** 输入 metric snapshot 可读但没有适用的 scoring reference profile
- **THEN** normalized artifact MAY 写入并标记为 `available`（包含 unsupported entries），或按实现选择 `unavailable`
- **AND** detail SHALL 明确说明 profile 缺失
- **AND** SHALL NOT 生成默认 utility 或 overall score

#### Scenario: 空 normalized 结果

- **WHEN** job 已完成但没有任何指标满足规范化条件
- **THEN** artifact MAY 为 `available` 且 `metrics` 为空或全为降级条目
- **AND** `score_coverage` 和 detail SHALL 说明没有 eligible metric
