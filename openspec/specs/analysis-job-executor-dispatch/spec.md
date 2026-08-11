# analysis-job-executor-dispatch Specification

## Purpose
TBD - created by archiving change 2026-08-07-integrate-multiview-analysis-orchestration. Update Purpose after archive.
## Requirements
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

### Requirement: 取消令牌贯穿

`cancellation_token` MUST 贯穿 Executor 执行，`fusing` 阶段同样在安全检查点检查取消请求；Parent `cancelRequestedAt` 后 Executor SHALL 终止为 `canceled` 并清理临时产物。

#### Scenario: 融合中取消

- **WHEN** Parent 在 `fusing` 阶段收到取消请求
- **THEN** MultiViewExecutor SHALL 在下一个安全检查点抛出取消异常
- **AND** 任务最终置为 `canceled`，临时产物被清理

### Requirement: joint 长任务执行语义

`joint_tracking_v2` 的 Executor SHALL 按长任务执行:每 tick 检查 cancellation token;进度 SHALL 为 canonical clock processed / total;两个 capture SHALL 在 finally 中 release;临时产物 SHALL atomic finalize,避免前一次 crash 留下半个 `fused_player_trajectory.v2` 被误认完成。

#### Scenario: 取消与进度

- **WHEN** joint 任务执行中收到 cancellation
- **THEN** Executor SHALL 在下一个 tick 边界终止
- **AND** 释放两个视频 capture

#### Scenario: 原子产物

- **WHEN** joint run 完成
- **THEN** 临时产物 SHALL 经 atomic finalize 变为正式 `fused_player_trajectory.v2`
- **AND** 半成品 SHALL NOT 被后续读取误认为完成

### Requirement: joint 失败语义

`joint_tracking_v2` 的失败 SHALL 分级:Cam2 中途永久解码失败 → 该时刻起 cam_2 view `unavailable`,继续 Cam1,最终 diagnostics = `joint_degraded`;Cam1/reference 永久失败 → `MultiViewJointRun failed`(canonical clock 依赖 reference source)。

#### Scenario: Cam2 降级

- **WHEN** cam_2 中途永久解码失败
- **THEN** 系统 SHALL 从该时刻起将 cam_2 view 标记为 `unavailable`
- **AND** 继续以 cam_1 分析,最终 diagnostics SHALL 为 `joint_degraded`

#### Scenario: Cam1 失败

- **WHEN** cam_1/reference 永久失败
- **THEN** `MultiViewJointRun` SHALL 判定为 `failed`
- **AND** 不产出正式 fused artifact

### Requirement: 多视角执行体实际遵守分析窗口

所有 multiview executor MUST 实际消费 Parent 或 child 上的窗口字段。`late_fusion_v1` 的 child Pipeline 和派生叠加视频 MUST 只处理窗口范围；`joint_tracking_v2` MUST 只运行窗口内 canonical ticks，并通过既有同步 clock 取得 secondary source frame。缺少窗口时两种模式 SHALL 保持全场行为。

#### Scenario: late fusion child 执行窗口

- **WHEN** late fusion child 携带 `clipStartMs/clipEndMs` 被 SingleView executor 执行
- **THEN** executor SHALL 将窗口传递给 Pipeline
- **AND** Pipeline SHALL 只在 decode range 内读取帧，正式轨迹和指标 SHALL 只保留请求窗口

#### Scenario: late fusion overlay 执行窗口

- **WHEN** late fusion child 启用分析叠加视频且携带窗口
- **THEN** OverlayVideoWriter SHALL 从窗口对应的源帧开始读取并在窗口结束后停止
- **AND** SHALL NOT 为该 artifact 无条件重新读取完整源视频

#### Scenario: joint tracking 执行窗口

- **WHEN** `joint_tracking_v2` Parent 携带 `[start_ms, end_ms)` 被 claim
- **THEN** MultiViewJointExecutor SHALL 将窗口转换为 reference frame 边界和必要的预热范围
- **AND** MultiViewJointRun SHALL 只生成边界内的 canonical ticks
- **AND** secondary source frame SHALL 继续由 CanonicalAnalysisClock 按 sync mapping 配对

#### Scenario: joint 窗口外样本不进入正式结果

- **WHEN** joint tracking 为初始化读取了预热帧
- **THEN** 预热帧 MAY 更新 tracker 状态
- **BUT** 预热帧 SHALL NOT 进入正式融合 sample、指标分母或用户可见轨迹统计

#### Scenario: 无窗口兼容

- **WHEN** executor 收到未携带完整窗口的历史或新任务
- **THEN** late fusion 和 joint tracking SHALL 分别沿用各自现有的全场执行路径
- **AND** SHALL NOT 因窗口字段缺失而失败

### Requirement: 窗口执行取消与失败诊断

窗口执行 MUST 保持现有 cancellation、retry 和 terminal failure 语义，并在窗口非法、视频边界裁剪或 seek 失败时写入结构化诊断，不得静默退化为全视频执行。

#### Scenario: 非法窗口拒绝

- **WHEN** `clipStartMs < 0`、`clipEndMs <= clipStartMs` 或窗口无法映射为正向 frame range
- **THEN** executor SHALL 返回稳定的参数错误
- **AND** SHALL NOT 启动全视频分析作为回退

#### Scenario: 窗口超出视频边界

- **WHEN** 合法窗口部分超出源视频有效时长
- **THEN** executor SHALL 将实际 decode range 裁剪到视频边界
- **AND** 结果 SHALL 记录请求范围与实际范围的差异
