# analysis-job-executor-dispatch Specification

## Purpose

定义 Worker 执行分发层：`AnalysisJobExecutor` Protocol、按 `analysisKind` 的 executor registry、`SingleViewAnalysisExecutor` 与 `MultiViewAnalysisExecutor`。它解决"Worker 主循环按任务类型选择执行体"的扩展性问题，避免 `_execute()` 因新增分析类型（`segment / multimodal / IMU`）不断变胖。

## ADDED Requirements

### Requirement: Executor Protocol

系统 MUST 提供 `AnalysisJobExecutor` Protocol：`execute(job, token, progress_callback) -> AnalysisPipelineResult`。`AnalysisWorkerRuntime._execute` MUST 通过 registry 解析 `analysisKind` 对应的 executor 并调用其 `execute`，不得在 Worker 主循环内按 `analysisKind` 硬编码分支。第一版 registry MUST 只含 SingleView / MultiView 两个执行体，MUST NOT 引入插件发现、通用 factory 或第三方扩展 API（"Worker 不知道不同类型任务怎么跑"是真实需求，"建立通用执行平台"不是）。

#### Scenario: Worker 按类型分发

- **WHEN** Worker 领取一个 job
- **THEN** 系统 SHALL 用 `job.analysisKind` 从 registry 解析 executor
- **AND** 调用该 executor 的 `execute(job, token, progress_callback)`

#### Scenario: 未知类型稳定失败

- **WHEN** registry 无法解析 `analysisKind`
- **THEN** 系统 SHALL 抛出稳定错误并走既有失败兜底路径
- **AND** 不得静默按单摄执行

### Requirement: SingleViewAnalysisExecutor

系统 MUST 提供 `SingleViewAnalysisExecutor`，其 `execute` 行为等于现有 `AnalysisPipeline.run()` 路径（重建 `AnalysisJobCreate`、调用 `pipeline_factory`、传递 `progress_callback` 与 `cancellation_token`、处理重试/超时/取消）。现有单摄 AnalysisJob 的行为 MUST 保持不变。

#### Scenario: 单摄 job 行为不变

- **WHEN** 一个 `analysisKind=single_view` 的任务被执行
- **THEN** 其结果、阶段、进度、取消/重试语义 SHALL 与改造前一致
- **AND** 现有单摄回归测试 SHALL 全部通过

### Requirement: MultiViewAnalysisExecutor

系统 MUST 提供 `MultiViewAnalysisExecutor`，其 `execute` 流程为：读取两个 child 的单摄产物 → 构建/复用 `MultiViewFusionRun`（`fusionRunId` 已在 Parent 持久化）→ 执行融合 → `MultiViewResultComposer` 生成 Parent 结果 → 返回 `AnalysisPipelineResult`（completed + 聚合 stages）。该 Executor 在 `resource_limiter` 内的计算是纯 artifact 数学（不解码视频）。

#### Scenario: 双摄执行链路

- **WHEN** Parent（`orchestrationStatus=fusion_ready`）被 claim
- **THEN** MultiViewExecutor SHALL 消费两路 child 的 `player_render_trajectory` 产物构建 `MultiViewViewInput`
- **AND** 执行融合并产出 Parent-owned 报告

#### Scenario: job-level fallback 不生成 fused artifact

- **WHEN** 任一 view `court_orientation=None` 或 sync authority unavailable（P0 job-level gate）
- **THEN** MultiViewExecutor SHALL NOT 生成 fused artifact
- **AND** 按确定性单视角降级规则 compose Parent 报告

### Requirement: 取消令牌贯穿

`cancellation_token` MUST 贯穿 Executor 执行，`fusing` 阶段同样在安全检查点检查取消请求；Parent `cancelRequestedAt` 后 Executor SHALL 终止为 `canceled` 并清理临时产物。

#### Scenario: 融合中取消

- **WHEN** Parent 在 `fusing` 阶段收到取消请求
- **THEN** MultiViewExecutor SHALL 在下一个安全检查点抛出取消异常
- **AND** 任务最终置为 `canceled`，临时产物被清理
