## MODIFIED Requirements

### Requirement: 依据素材状态门控 view

工作区各 view SHALL 依据素材状态可用/禁用，符合“先素材后分析”的生命周期；结果类 view 的可开性须同时满足 `mediaState=ready`、`analysisState=succeeded`、存在该 view 所需真实产出物，并且报告 view 还必须存在至少一类有效报告证据。仅有 completed Job、jobId 或空 result manifest 不得判定报告可用。

#### Scenario: 素材未分析时不可用分析结果

- **WHEN** 素材 `mediaState` 为 `recording` / `processing` 或 `analysisState` 为 `not_started`
- **THEN** “数据分析”“球路”“报告”等结果类 view SHALL 置灰、禁用或提示待分析

#### Scenario: 分析完成且报告有有效证据

- **WHEN** `mediaState=ready`、`analysisState=succeeded`、selected Job 的 result manifest 可读取，且至少存在有效 canonical 场地轨迹点、有效运动指标条目或 available structured visualization artifact
- **THEN** “报告”Tab SHALL 可用并可进入

#### Scenario: 分析完成但没有有效报告证据

- **WHEN** selected completed Job 的 tracks、运动指标和 structured visualization artifact 均为空、无效、失败或跳过
- **THEN** 顶部“报告”Tab SHALL 保持可见但置灰并设置原生 `disabled`
- **AND** 点击或程序化 view 切换 SHALL 不得进入报告内容
- **AND** SHALL 提供“暂无有效报告数据”或等价原因

#### Scenario: 有任务但缺该 view 产出物

- **WHEN** 素材存在分析与 `primaryAnalysisJobId` 但未产出球路/报告等特定 artifact
- **THEN** 该结果类 view SHALL 不可用或显示明确空态，不得渲染空白结果，亦不得仅凭 jobId 判定可用

#### Scenario: 再次分析期间旧结果保持有效性

- **WHEN** 素材存在 completed 结果且用户触发再次分析
- **THEN** 结果 view SHALL 继续由旧 completed Job 的有效证据供给
- **AND** active Job 的空结果或处理中状态 SHALL NOT 覆盖旧结果的 capability
