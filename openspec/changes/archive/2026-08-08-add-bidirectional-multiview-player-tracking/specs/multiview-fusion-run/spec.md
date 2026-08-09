# multiview-fusion-run Delta

## ADDED Requirements

### Requirement: MultiViewJointRun 运行实体

`joint_tracking_v2` SHALL 使用 `MultiViewJointRun` 作为运行实体(区别于 `late_fusion_v1` 的 `MultiViewFusionRun`)。`MultiViewJointRun` SHALL 拥有 `JointViewRuntime` cam_1/cam_2、`CanonicalAnalysisClock`、`GlobalPlayerState` 集合与 fused artifact 产物归属。运行标识为 `jointRunId`(不复用 `fusionRunId`)。

#### Scenario: joint run 所有权

- **WHEN** 一个 `joint_tracking_v2` Parent 运行
- **THEN** `MultiViewJointRun` SHALL 拥有两个 `JointViewRuntime` 与全局状态
- **AND** 产物 SHALL 归属 JointRun,而非任一 ViewRun 或 CaptureTake

#### Scenario: 不等待 child job

- **WHEN** joint run 启动
- **THEN** SHALL NOT 等待 AnalysisJob children(无 children)
- **AND** 直接按 CanonicalAnalysisClock 推进双 view perception

### Requirement: jointRunId 持久化与原子 finalize

`jointRunId` SHALL 持久化于 Parent(`fusionRunId` 仅属 late_fusion_v1)。Parent 被 claim 后 SHALL 先持久化 `jointRunId`,再打开视频/模型。失败重试 SHALL 复用 `jointRunId`、清理 incomplete temp outputs、从头安全重跑(第一版无 checkpoint resume)。临时产物 SHALL atomic finalize,避免半成品被误认完成。

#### Scenario: 先持久化再执行

- **WHEN** joint Parent 被 claim
- **THEN** 系统 SHALL 先持久化 `jointRunId`
- **AND** 再打开视频/加载模型

#### Scenario: 重启复用幂等

- **WHEN** joint run 失败后同一 Parent 重试
- **THEN** 系统 SHALL 复用 `jointRunId`
- **AND** 清理 incomplete temp outputs 后从头安全重跑

### Requirement: MultiViewFusionRun 仅属 late_fusion_v1

`MultiViewFusionRun` SHALL 仅用于 `executionMode=late_fusion_v1`(等待两个 source AnalysisJob → artifact fusion)。`joint_tracking_v2` SHALL NOT 使用 `MultiViewFusionRun` 的等待/artifact-fusion 语义。

#### Scenario: late_fusion 保持 FusionRun

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** 系统 SHALL 使用 `MultiViewFusionRun` 等待两个 source job 并执行 artifact fusion
- **AND** 行为与 P0 完全一致
