## ADDED Requirements

### Requirement: 工作区提供落点子视图

LibraryItemWorkspace SHALL 将 `landing` 纳入工作区 view 与 URL query 契约，顶部 Tab 顺序 SHALL 为“概览 / 视频 / 数据分析 / 球路 / 落点 / 报告 / 片段 / 技术详情”。

#### Scenario: 切换到落点视图
- **WHEN** 用户在工作区点击“落点”Tab
- **THEN** 系统 SHALL 以 replace 语义将 URL 切换为 `?view=landing`
- **AND** SHALL 保留当前有效的 selected `analysisJob`

#### Scenario: 落点视图作为 embedded content
- **WHEN** 工作区渲染 `landing` view
- **THEN** 系统 SHALL 渲染落点 Content 而不是独立页面 shell
- **AND** loading、empty、failed 和 success 状态 SHALL NOT 渲染旧任务导航或“返回任务管理”控件

### Requirement: 落点 capability 使用独立 artifact 门控

工作区 SHALL 仅根据 selected completed Job 的 result manifest 中是否存在可读 `shot_landings_url` 判定 `landing` view 可用性，MUST NOT 复用球路 capability 或仅根据 job ID 判定。

#### Scenario: 落点有效但球路不可用
- **WHEN** selected Job 发布 `shot_landings_url` 但没有可用 reconstructed trajectory view
- **THEN** `landing` view SHALL 可用
- **AND** `trajectory` view MAY 保持不可用

#### Scenario: 球路有效但落点未生成
- **WHEN** selected Job 有球路 artifact 但没有 `shot_landings_url`
- **THEN** `trajectory` view MAY 可用
- **AND** `landing` view SHALL 禁用或显示明确缺产物空态

#### Scenario: 再次分析期间保留旧落点结果
- **WHEN** 素材存在已完成且有落点 artifact 的 selected Job，同时新 Job 正在运行
- **THEN** `landing` view SHALL 继续读取 selected completed Job
- **AND** active Job 的空 manifest MUST NOT 覆盖已有落点 capability

### Requirement: 落点视图遵守 selected Job 结果边界

工作区 SHALL 将与其他 Job-bound 结果视图相同的 selected Job 用于落点数据，且 SHALL NOT 跨素材、跨历史版本或从 internal child 借用落点 artifact。

#### Scenario: 切换历史分析版本
- **WHEN** 用户将 selected Job 从 Job A 切换为属于同一素材的 Job B
- **THEN** `landing` view SHALL 读取 Job B 的 `shot-landings.v1`
- **AND** SHALL NOT 继续显示 Job A 的落点

#### Scenario: 历史版本缺失落点产物
- **WHEN** 用户选中的历史 completed Job 没有 `shot_landings_url`
- **THEN** 落点 view SHALL 显示该版本自身的不可用原因
- **AND** MUST NOT 显示更新 Job 的落点

#### Scenario: 无效 selected Job
- **WHEN** URL 中的 `analysisJob` 不属于当前素材、为 internal child 或已删除
- **THEN** 工作区 SHALL 在请求 Shot Landing artifact 前拒绝该选择
- **AND** SHALL 回退到当前素材的有效 primary result 或无结果态
