# analysis-job-executor-dispatch Delta

## MODIFIED Requirements

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
