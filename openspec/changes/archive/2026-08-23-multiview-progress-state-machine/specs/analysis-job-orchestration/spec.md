## MODIFIED Requirements

### Requirement: Stage telemetry

阶段遥测 MUST 保持既有 `AnalysisStage` 结构，并由当前分析模式的规范化阶段图生成。`single_view` MUST 继续使用既有单摄稳定阶段；`late_fusion_v1` 的 `AnalysisPipelineResult.stages` MUST 按“素材与同步检查 / A 机位视觉分析 / B 机位视觉分析 / 多视角融合 / 指标重算 / 可视化输出 / 报告生成”顺序表达聚合阶段；`joint_tracking_v2` MUST 按“素材与同步检查 / 双摄协同跟踪 / 指标重算 / 可视化输出 / 报告生成”顺序表达聚合阶段。双摄子阶段进度 MUST 经 `viewRuns` 暴露，运行中应反映最近可用的 child 或内部 `ViewRun` 状态；双摄专用阶段 MUST NOT 被追加到单摄阶段列表末尾。

总体进度 MUST 使用当前阶段图的稳定权重和阶段进度聚合，保持单调递增；MUST NOT 通过包含未来 `pending` 阶段的数量平均值覆盖真实的当前阶段进度。报告阶段 MUST 只能在前置分析和后处理阶段完成后开始。

#### Scenario: Parent 聚合阶段

- **WHEN** 前端轮询 multiview Parent 摘要
- **THEN** Parent `stages` SHALL 展示与 `executionMode` 对应的聚合阶段和真实顺序
- **AND** `viewRuns`（`cam_1` / `cam_2` 各自的 `status / stage / progress`）在有子运行时 SHALL 提供两路子进度，运行中也反映 child 或内部 `ViewRun` 的最近状态

#### Scenario: joint tracking 不显示报告先于协同跟踪

- **WHEN** `joint_tracking_v2` 的协同跟踪阶段上报进度 95
- **THEN** `multiview-joint` SHALL 为 active，指标、可视化和报告 SHALL 仍按图保持 pending
- **AND** 总体进度 SHALL 按 joint 阶段权重聚合，而不是按单摄阶段数量平均

#### Scenario: 报告生成是终末阶段

- **WHEN** 双摄任务进入报告生成
- **THEN** 只有在融合或协同跟踪、指标重算和可视化输出完成后，报告阶段才 SHALL 变为 active
- **AND** 报告完成后总体进度 SHALL 为 100
