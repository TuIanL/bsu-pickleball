## MODIFIED Requirements

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
