## MODIFIED Requirements

### Requirement: Executor Protocol

系统 MUST 提供 AnalysisJobExecutor Protocol，其 execute(job, token, progress_callback) 返回可区分的 AnalysisPipelineResult 或 ModularRunManifest。resolve_executor MUST 为唯一静态分派入口，先按 analysisEngine 选择 legacy_v1 或 modular_v1；legacy 分支再按 analysisKind、multiviewExecutionMode 和既有 job role 选择现有执行体。缺省 engine SHALL 为 legacy_v1。Worker MUST 通过 registry 调用 execute，不得在主循环硬编码具体能力或算法。新增 ModularAnalysisExecutor MUST 只运行冻结计划；系统 MUST NOT 引入动态插件发现、通用 factory 或第三方插件 API。

#### Scenario: Worker 按类型分发

- **WHEN** Worker 领取一个 job
- **THEN** 系统 SHALL 用 analysisEngine 解析分支，并在 legacy 分支按 job.analysisKind 及既有模式/角色从 registry 解析 executor
- **AND** 调用该 executor 的 `execute(job, token, progress_callback)`

#### Scenario: 未知类型稳定失败

- **WHEN** registry 无法解析 analysisEngine 或该 engine 的任务类型
- **THEN** 系统 SHALL 抛出稳定错误并走既有失败兜底路径
- **AND** 不得静默按单摄执行

#### Scenario: 模块任务独立分派
- **WHEN** Worker 领取 analysisEngine=modular_v1 且计划有效的任务
- **THEN** registry SHALL 返回 ModularAnalysisExecutor
- **AND** 该执行体 SHALL 返回 ModularRunManifest，而不为满足旧类型补造 metrics 或报告

### Requirement: SingleViewAnalysisExecutor

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

系统 MUST 提供 `SingleViewAnalysisExecutor`，其 `execute` 行为等于现有 `AnalysisPipeline.run()` 路径（重建 `AnalysisJobCreate`、调用 `pipeline_factory`、传递 `progress_callback` 与 `cancellation_token`、处理重试/超时/取消）。现有单摄 AnalysisJob 的行为 MUST 保持不变。

#### Scenario: 单摄 job 行为不变

- **WHEN** 一个 `analysisKind=single_view` 的任务被执行
- **THEN** 其结果、阶段、进度、取消/重试语义 SHALL 与改造前一致
- **AND** 现有单摄回归测试 SHALL 全部通过

### Requirement: MultiViewAnalysisExecutor

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

系统 MUST 提供 `MultiViewAnalysisExecutor`,其 `execute` 流程按 `multiviewExecutionMode` 分发:

- **`late_fusion_v1`**(P0 现状):读取两个 child 的单摄产物 → 构建/复用 `MultiViewFusionRun`(`fusionRunId` 已在 Parent 持久化)→ 执行融合 → `MultiViewResultComposer` 生成 Parent 结果。该模式下 Executor 在 `resource_limiter` 内的计算是**纯 artifact 数学(不解码视频)**。
- **`joint_tracking_v2`**:持久化 `jointRunId` → 同步解码两路视频 + 双 view tracking(内部 `JointViewRuntime` A/B)→ global fusion → `MultiViewResultComposer`。该模式 SHALL 直接消费源视频与标定,不依赖 child `player_render_trajectory` artifact。

Executor MUST 在 compose 完成后将 Parent 的 `AnalysisPipelineResult` 落盘到 `result.json`。`resolve_executor` 仍为唯一分发入口,按 `analysisKind=multiview` + `executionMode` 选择执行体,不硬编码分支。

#### Scenario: late_fusion_v1 纯 artifact 数学

- **WHEN** Parent 的 `executionMode=late_fusion_v1` 且被 claim
- **THEN** MultiViewExecutor SHALL 消费两路 child 的 `player_render_trajectory` 产物构建 `MultiViewViewInput`
- **AND** 不解码视频,执行 artifact 融合并产出 Parent-owned 报告

#### Scenario: joint_tracking_v2 同步解码

- **WHEN** Parent 的 `executionMode=joint_tracking_v2` 且 preflight passed
- **THEN** MultiViewExecutor SHALL 先持久化 `jointRunId`,再同步解码两路视频并执行双 view tracking + global fusion
- **AND** 不依赖 child artifact,产物来自 Parent-owned JointRun

## ADDED Requirements

### Requirement: 模块执行结果独立发布且保持旧结果兼容
Worker SHALL 根据带 engine 判别的返回类型选择发布路径。legacy AnalysisPipelineResult SHALL 继续调用现有结果组合和产品完成回调；ModularRunManifest SHALL 直接登记计划、节点和 ArtifactRef，不触发 metrics/insights/report 完成回调。新类型 MUST NOT 改写历史 result.json、AnalysisArtifacts 或报告 API 的字段含义。

#### Scenario: 模块清单成功发布
- **WHEN** 原始球检测完成且发布 ModularRunManifest
- **THEN** Worker SHALL 按模块目标策略更新 Job
- **AND** SHALL 不调用 legacy 的 on_completed 或固定阶段重建

#### Scenario: 读取历史结果
- **WHEN** 查询没有 analysisEngine 的已完成 Job
- **THEN** API SHALL 继续按 legacy schema 读取结果和报告
- **AND** SHALL 不要求存在计划或模块清单

### Requirement: 模块执行沿用控制面控制信号
ModularAnalysisExecutor MUST 使用既有 cancellation token、lease 和安全检查点，并按节点策略处理算法重试；取消、超时和 lease 丢失 MUST 穿透至 Worker 的控制分支，不能被包装成普通失败清单而吞掉。

#### Scenario: 节点推理中取消
- **WHEN** token 在节点安全检查点报告取消
- **THEN** Executor SHALL 释放本次资源并把取消信号交回 Worker
- **AND** Worker SHALL 保留已发布部分产物并写入 canceled
