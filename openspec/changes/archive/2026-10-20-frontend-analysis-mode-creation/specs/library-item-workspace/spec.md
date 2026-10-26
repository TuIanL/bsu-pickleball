## MODIFIED Requirements

### Requirement: 工作区支持选择历史分析版本

素材工作区 SHALL 允许用户从当前素材所属的公开 legacy_v1（含缺省 engine）历史分析任务中选择要查看的完整结果版本。modular_v1 SHALL 在同一素材历史中列出，但通过“查看专项结果”打开模块任务路由，不作为完整结果 Tab 的 selected Job。工作区 SHALL 将同一 selected Job 用于数据分析、球路、报告和技术详情，MUST NOT 在不同结果 Tab 间混用不同 Job 的产物。

#### Scenario: 选中已完成历史任务
- **WHEN** 用户对属于当前素材的 completed 公开 legacy_v1（含缺省 engine）Job 点击“查看结果”
- **THEN** 工作区 SHALL 将该 Job 标记为当前选中版本
- **AND** 数据分析、球路、报告和技术详情 SHALL 全部读取该 Job

#### Scenario: 选中版本在 Tab 切换中保持
- **WHEN** 用户已选中 Job A，并在数据分析、球路、报告或技术详情间切换
- **THEN** 每个 Job-bound 结果 Tab SHALL 继续读取 Job A
- **AND** 工作区 MUST NOT 因 Tab 切换恢复到最新 Job

#### Scenario: 无显式选择时使用最新结果
- **WHEN** 工作区 URL 未指定 analysisJob
- **THEN** 结果视图 SHALL 使用 primaryResultAnalysisJobId 指向的最新 completed 公开 legacy_v1（含缺省 engine）完整 Job
- **AND** 现有无 analysisJob 的 Library 深链 SHALL 保持可用

#### Scenario: 显式选择不被新任务顶掉
- **WHEN** 用户显式选中 Job A 后另一个 Job B 完成并成为新的 primary result
- **THEN** 当前工作区 SHALL 继续显示 Job A
- **AND** 系统 MAY 提示有新版本可用，但 MUST NOT 自动改变用户选择

#### Scenario: 打开专项历史结果
- **WHEN** 用户点击当前素材模块历史的“查看专项结果”
- **THEN** 系统 SHALL 导航到该模块 Job 并携带素材 return，保留其原始目标与结果
- **AND** SHALL NOT 将该模块 Job 设置为完整报告版本

### Requirement: 历史版本的结果边界按 Job 自身确定

工作区 SHALL 依据 selected Job 自身的 analysisEngine、status、analysisKind 和对应 engine 的结果 manifest 决定可打开的结果视图与技术详情类型。以下 Workspace 内结果场景适用于 legacy_v1（含缺省 engine）；modular_v1 SHALL 转入独立模块结果并仅消费模块清单。

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

#### Scenario: 模块失败仍可查看独立成功产物
- **WHEN** 用户查看属于当前素材的失败模块任务且有成功节点产物
- **THEN** 页面 SHALL 打开其模块状态与可用产物，不借用完整分析或其他 Job 的结果

## ADDED Requirements

### Requirement: 素材历史覆盖模块任务及真实归属

素材历史 SHALL 包含其已验证归属的公开模块任务，并显示专项目标/模式、状态和机位信息。历史计数 SHALL 包含模块任务，active→terminal SHALL 定向重投影；完整结果缺失 MUST NOT 使已完成专项任务被标记失败。归属 SHALL 来自持久化视频/录制/take 关联，不能由 return 或标题推断。

#### Scenario: 刷新模块历史
- **WHEN** 用户刷新上传、单摄录制或双摄录制素材页面
- **THEN** 对应专项 Job SHALL 可重新查询并显示，不依赖创建页内存
- **AND** 双摄专项和 A/B 单摄专项 SHALL 标注实际分析范围，不互相伪装

#### Scenario: 新任务完成保留用户选择
- **WHEN** 用户选中完整版本 A 后模块任务 B 完成
- **THEN** 历史 SHALL 新增或更新 B，但当前完整版本选择及结果证据 SHALL 仍为 A
