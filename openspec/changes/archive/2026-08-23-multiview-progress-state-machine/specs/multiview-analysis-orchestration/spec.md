## MODIFIED Requirements

### Requirement: AnalysisJob 编排字段

系统 MUST 为 `AnalysisJobSummary` 增加编排字段：`analysisKind`（`single_view` / `multiview`，历史 job 缺省 `single_view`）、`visibility`（`public` / `internal`，缺省 `public`）、`parentJobId`（缺省 None）、`analysisScope`（`full` / `perception`，缺省 `full`；**Parent 不适用为 None**）、`orchestrationStatus`（独立编排维度）、`fusionRunId`（缺省 None）、`sourceJobs`（数组 `[{cameraSlot, jobId}]`，Parent 的所有权映射）、`viewRuns`（各机位 `status / stage / progress` 聚合）。`canonicalStatus` 五态 `queued / running / succeeded / failed / canceled` MUST 保持不变，等待 child 的 Parent 在 canonical 上仍属 `queued`。任务摘要的 `stages` MUST 根据 `executionMode` 使用规范化阶段图；`viewRuns` 只有在存在真实 dedicated child 或内部 `ViewRun` 时才返回非空内容。

#### Scenario: 历史任务读取兼容

- **WHEN** 读取不含新字段的历史 `AnalysisJobSummary`
- **THEN** 系统 SHALL 按 `analysisKind=single_view`、`visibility=public`、`orchestrationStatus=none` 缺省解析
- **AND** 不得因缺字段而解析失败或改变既有渲染

#### Scenario: 双摄任务创建

- **WHEN** 用户发起一次双摄协同分析
- **THEN** 系统 SHALL 创建一个 `analysisKind=multiview` 的 public Parent，初始 `canonicalStatus=queued, orchestrationStatus=waiting_sources`
- **AND** Parent SHALL 根据其 `executionMode` 选择对应的顶层阶段图，而不是复用单摄阶段后追加双摄阶段

#### Scenario: joint tracking 暴露内部子进度

- **WHEN** `joint_tracking_v2` Parent 通过素材检查并开始处理 A/B 机位
- **THEN** Parent SHALL 在 `viewRuns` 中返回内部 A/B `ViewRun` 的 `status / stage / progress`
- **AND** 在内部子运行尚未创建前，系统 SHALL 省略 `viewRuns` 或返回明确的未开始语义，不得使用空对象冒充实时进度

