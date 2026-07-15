## MODIFIED Requirements

### Requirement: Deterministic artifact paths

系统 SHALL 为新增分析产物提供确定性的本地存储路径。对于关联 CaptureTake 的录制任务，路径 MUST 位于对应会话目录的 `analysis/<job_id>/` 下；对于无 CaptureTake 的旧任务或上传任务，继续使用兼容的 `outputs/<job_id>/` 目录。

#### Scenario: Resolve capture analysis artifact paths
- **WHEN** 后端为关联 capture_take_id 的任务 `job-123` 解析分析产物路径
- **THEN** `ball-overlay`、`detections`、`ball-trajectory`、`bounce-events` 和可视化产物 MUST 位于该 take 目录的 `analysis/job-123/` 对应子路径
- **AND** 路径解析 SHALL 使用 SQLite 索引中的会话目录，不得重新猜测默认目录

#### Scenario: Preserve legacy artifact paths
- **WHEN** 后端为没有 capture_take_id 的旧任务解析 artifact 路径
- **THEN** 系统 SHALL 继续使用 `outputs/job-123/`
- **AND** 现有 API artifact 名称和读取行为 SHALL 保持兼容

### Requirement: Pipeline result references new artifacts

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中描述会话目录内新增分析产物的 path、url、status 和 detail 字段，且所有新增字段 MUST 可选以保持旧结果兼容。

#### Scenario: Capture analysis result references session artifacts
- **WHEN** 录制会话的分析任务生成 artifact 文件
- **THEN** `AnalysisPipelineResult.artifacts` MUST 包含该 artifact 的逻辑引用和实际文件状态
- **AND** artifact API SHALL 通过 job_id 和 SQLite 索引解析到对应 capture 会话目录

#### Scenario: Missing capture artifact remains compatible
- **WHEN** 录制会话没有生成某个可选 artifact
- **THEN** 对应 artifact 字段 MUST 允许为 `null`
- **AND** API MUST 返回 404 而不是暴露绝对路径或返回 422
