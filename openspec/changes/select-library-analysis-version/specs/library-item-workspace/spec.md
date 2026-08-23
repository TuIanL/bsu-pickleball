## ADDED Requirements

### Requirement: 工作区支持选择历史分析版本

素材工作区 SHALL 允许用户从当前素材所属的公开历史分析任务中选择要查看的版本。工作区 SHALL 将同一 selected Job 用于数据分析、球路、报告和技术详情，MUST NOT 在不同结果 Tab 间混用不同 Job 的产物。

#### Scenario: 选中已完成历史任务
- **WHEN** 用户对属于当前素材的 completed 公开 Job 点击“查看结果”
- **THEN** 工作区 SHALL 将该 Job 标记为当前选中版本
- **AND** 数据分析、球路、报告和技术详情 SHALL 全部读取该 Job

#### Scenario: 选中版本在 Tab 切换中保持
- **WHEN** 用户已选中 Job A，并在数据分析、球路、报告或技术详情间切换
- **THEN** 每个 Job-bound 结果 Tab SHALL 继续读取 Job A
- **AND** 工作区 MUST NOT 因 Tab 切换恢复到最新 Job

#### Scenario: 无显式选择时使用最新结果
- **WHEN** 工作区 URL 未指定 analysisJob
- **THEN** 结果视图 SHALL 使用 primaryResultAnalysisJobId 指向的最新 completed 公开 Job
- **AND** 现有无 analysisJob 的 Library 深链 SHALL 保持可用

#### Scenario: 显式选择不被新任务顶掉
- **WHEN** 用户显式选中 Job A 后另一个 Job B 完成并成为新的 primary result
- **THEN** 当前工作区 SHALL 继续显示 Job A
- **AND** 系统 MAY 提示有新版本可用，但 MUST NOT 自动改变用户选择

### Requirement: selected Job 必须通过素材归属校验

工作区 SHALL 仅允许将当前 LibraryItem 所属的公开 Job 解析为 selected Job。跨素材 Job、internal child、不存在或已删除 Job MUST NOT 被用于加载结果产物。

#### Scenario: URL 指向其他素材的 Job
- **WHEN** analysisJob 指向一个存在但不属于当前 LibraryItem 的 Job
- **THEN** 工作区 SHALL 拒绝将其解析为 selected Job
- **AND** SHALL 回退到当前素材的 primary result 或无结果态
- **AND** SHALL NOT 请求该跨素材 Job 的报告或 artifact

#### Scenario: URL 指向 internal child
- **WHEN** analysisJob 指向 multiview Parent 的 internal source child
- **THEN** 工作区 SHALL 将该选择视为无效
- **AND** 历史版本选择器 SHALL NOT 列出该 internal child

#### Scenario: 选中任务被删除
- **WHEN** 当前 selected Job 被删除或刷新后已无法解析
- **THEN** 工作区 SHALL 定向重投影当前素材
- **AND** SHALL 回退到最新 completed 结果或无结果态
- **AND** SHALL 以 replace 语义清理失效 analysisJob

### Requirement: 历史版本的结果边界按 Job 自身确定

工作区 SHALL 依据 selected Job 自身的 status、analysisKind 和 AnalysisResult manifest 决定可打开的结果视图与技术详情类型。

#### Scenario: 历史 Job 缺少球路产物
- **WHEN** selected completed Job 未生成可用球路 artifact
- **THEN** 球路 view SHALL 显示“该版本未生成球路”类明确空态
- **AND** MUST NOT 显示最新 Job 或其他历史 Job 的球路

#### Scenario: 双摄素材选中 A/B 单摄 Job
- **WHEN** sync_recording 素材中 selected Job 的 analysisKind 为单摄分析
- **THEN** 技术详情 SHALL 打开该 Job 的单摄 AnalysisDetails
- **AND** SHALL NOT 仅因素材类型是 sync_recording 而打开 MultiviewObservability

#### Scenario: 选中失败或取消任务
- **WHEN** 用户查看 failed 或 canceled 历史 Job
- **THEN** 工作区 SHALL 显示该 Job 自身的状态、失败阶段和可用诊断
- **AND** 数据分析、球路与报告 MUST NOT 借用任何 completed Job 的产物
