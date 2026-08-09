# multiview-execution-mode Specification

## Purpose
多视角分析执行模式:`late_fusion_v1 | joint_tracking_v2`,两模式的编排/执行差异、缺省规则与 A/B baseline 去重。

## Requirements
### Requirement: 执行模式字段与缺省规则

多视角 Parent 任务 SHALL 携带 `multiviewExecutionMode`,取值为 `late_fusion_v1` 或 `joint_tracking_v2`。字段缺失或未知时 SHALL 缺省为 `late_fusion_v1`(历史任务零迁移)。

#### Scenario: 历史任务缺省 late_fusion_v1

- **WHEN** 一个多视角 Parent 缺 `executionMode` 字段
- **THEN** 系统 SHALL 按 `late_fusion_v1` 处理
- **AND** 不触发任何数据/产物迁移

#### Scenario: 新建双摄协同默认 joint_tracking_v2

- **WHEN** 创建新的双摄协同分析任务
- **THEN** 系统 SHALL 将其标记为 `joint_tracking_v2`(除非显式指定 late_fusion_v1)

### Requirement: executionMode 进入输入签名

`multiviewExecutionMode` SHALL 进入 Parent 的 `inputSignature` / `configSignature`。同一 CaptureTake 的 `late_fusion_v1` 与 `joint_tracking_v2` 任务 SHALL 视为不同分析任务,SHALL NOT 被幂等/去重逻辑合并。

#### Scenario: A/B 不被去重

- **WHEN** 同一 CaptureTake 创建 `late_fusion_v1` 与 `joint_tracking_v2` 两个 Parent
- **THEN** 两者的 inputSignature SHALL 不同
- **AND** 系统 SHALL NOT 将二者判为重复任务而丢弃其一

### Requirement: 两模式编排差异

`late_fusion_v1` SHALL 保持 P0 现状:Parent → 2 个 dedicated AnalysisJob children → `MultiViewFusionRun` → artifact fusion。`joint_tracking_v2` SHALL 在 Parent preflight passed 后直接 runnable,由内部 `ViewRun` A/B 驱动,SHALL NOT 创建 AnalysisJob children,且输入来自持久化 `jointViewInputs`。

#### Scenario: late_fusion_v1 保持 child 编排

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** 系统 SHALL 创建两个 dedicated AnalysisJob children 并等待其完成
- **AND** 融合在 `MultiViewFusionRun` 中基于两路 artifact 执行

#### Scenario: joint_tracking_v2 直接 runnable

- **WHEN** Parent 的 `executionMode=joint_tracking_v2` 且 preflight passed
- **THEN** 系统 SHALL 直接将其置为 runnable,无需 AnalysisJob children
- **AND** 输入来自持久化 `jointViewInputs`(非 child artifact),内部创建 `ViewRun` A/B

### Requirement: A/B baseline 能力

同一 CaptureTake SHALL 可创建多个不同 `executionMode` 的 Parent,以支持 `late_fusion_v1` 与 `joint_tracking_v2` 的 A/B 对比。两者 SHALL 独立运行、独立产物、互不覆盖。

#### Scenario: 同一 take 双跑

- **WHEN** 对同一 CaptureTake 分别创建 late_fusion_v1 与 joint_tracking_v2 两个 Parent
- **THEN** 两者 SHALL 独立运行、独立产出、互不覆盖
- **AND** 对比指标(球场位置 RMSE / 缺失率 / 覆盖率等)SHALL 可基于两者产物计算
