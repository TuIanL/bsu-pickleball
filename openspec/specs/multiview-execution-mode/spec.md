# multiview-execution-mode Specification

## Purpose
多视角分析执行模式:`late_fusion_v1 | joint_tracking_v2`,两模式的编排/执行差异、缺省规则与 A/B baseline 去重。
## Requirements
### Requirement: 执行模式字段与缺省规则

多视角创建请求 SHALL 在 `multiview.executionMode` 携带执行模式，取值为 `late_fusion_v1` 或 `joint_tracking_v2`；Parent 持久化字段 SHALL 为 `executionMode`。缺失或未知时 SHALL 缺省为 `late_fusion_v1`，以保持历史任务兼容。旧文档中的 `multiviewExecutionMode` SHALL 视为历史命名，不新增同名顶层字段。

#### Scenario: 历史任务缺省 late_fusion_v1

- **WHEN** 一个多视角 Parent 缺 `executionMode` 字段
- **THEN** 系统 SHALL 按 `late_fusion_v1` 处理
- **AND** 不触发任何数据或产物迁移

#### Scenario: 新建任务显式选择 joint

- **WHEN** 前端在 `multiview.executionMode` 发送 `joint_tracking_v2`
- **THEN** 系统 SHALL 将 Parent 标记为 `joint_tracking_v2`
- **AND** SHALL NOT 因字段命名差异回退为 late-fusion

#### Scenario: 未知模式安全缺省

- **WHEN** 请求携带未知 execution mode
- **THEN** 系统 SHALL 缺省为 `late_fusion_v1`
- **AND** SHALL 记录输入校验或兼容诊断

### Requirement: executionMode 进入输入签名

`executionMode` SHALL 进入 Parent 的 `inputSignature` / `configSignature`。同一 CaptureTake 的 `late_fusion_v1` 与 `joint_tracking_v2` 任务 SHALL 视为不同分析任务，SHALL NOT 被幂等或去重逻辑合并。

#### Scenario: A/B 不被去重

- **WHEN** 同一 CaptureTake 创建 `late_fusion_v1` 与 `joint_tracking_v2` 两个 Parent
- **THEN** 两者的 inputSignature SHALL 不同
- **AND** 系统 SHALL NOT 将二者判为重复任务而丢弃其一

### Requirement: 两模式编排差异

`late_fusion_v1` SHALL 保持“Parent → 2 个 dedicated AnalysisJob children → `MultiViewFusionRun` → artifact fusion”的所有权和执行关系；其 Parent 阶段图 MUST 依次表达素材检查、A 机位、B 机位、融合、指标重算、可视化输出和报告生成。`joint_tracking_v2` SHALL 在 Parent preflight passed 后直接 runnable，由内部 `ViewRun` A/B 驱动，SHALL NOT 创建 AnalysisJob children，且输入来自持久化 `jointViewInputs`；其 Parent 阶段图 MUST 依次表达素材检查、双摄协同跟踪、指标重算、可视化输出和报告生成。两种模式的阶段顺序和进度聚合 MUST 由后端状态机统一生成。

#### Scenario: late_fusion_v1 保持 child 编排

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** 系统 SHALL 创建两个 dedicated AnalysisJob children 并等待其完成
- **AND** Parent SHALL 按 A/B child 阶段聚合进度，再在两路完成后进入 `MultiViewFusionRun` 和后处理阶段

#### Scenario: joint_tracking_v2 直接 runnable

- **WHEN** Parent 的 `executionMode=joint_tracking_v2` 且 preflight passed
- **THEN** 系统 SHALL 直接将其置为 runnable，无需 AnalysisJob children
- **AND** 输入 SHALL 来自持久化 `jointViewInputs`，内部 SHALL 创建或维护 A/B `ViewRun`

#### Scenario: 两种模式都在后处理后生成报告

- **WHEN** 任一双摄模式完成其分析或融合阶段
- **THEN** 系统 SHALL 先完成指标重算和可视化输出，再将报告阶段置为 active
- **AND** 报告阶段 SHALL NOT 出现在双摄协同跟踪或融合阶段之前

### Requirement: A/B baseline 能力

同一 CaptureTake SHALL 可创建多个不同 `executionMode` 的 Parent,以支持 `late_fusion_v1` 与 `joint_tracking_v2` 的 A/B 对比。两者 SHALL 独立运行、独立产物、互不覆盖。

#### Scenario: 同一 take 双跑

- **WHEN** 对同一 CaptureTake 分别创建 late_fusion_v1 与 joint_tracking_v2 两个 Parent
- **THEN** 两者 SHALL 独立运行、独立产出、互不覆盖
- **AND** 对比指标(球场位置 RMSE / 缺失率 / 覆盖率等)SHALL 可基于两者产物计算

