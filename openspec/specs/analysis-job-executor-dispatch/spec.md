# analysis-job-executor-dispatch Specification

## Purpose

定义分析任务的执行体分派契约：Executor Protocol 与单摄、多视角执行体的职责边界，取消令牌贯穿长任务，以及执行体遵守分析窗口的取消与失败诊断语义。
## Requirements
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
