## MODIFIED Requirements

### Requirement: Video workspace report actions

系统 SHALL 在视频分析工作区提供紧凑的下级结果入口，并且报告入口必须复用统一的 report capability。无有效报告证据时不得暴露可点击的报告导航，也不得通过嵌入式 view 切换或程序化导航绕过禁用状态；系统不得把已移除的落点或球捕获分析暴露为当前真实 job 报告。

#### Scenario: User views report actions with valid evidence

- **WHEN** 用户查看包含有效报告证据的 completed job-specific video analysis workspace
- **THEN** status rail 或相邻二级导航 SHALL 显示分析详情及当前支持的 movement/diagnosis 报告动作
- **AND** 点击支持的报告动作 SHALL 导航到匹配的 job-specific report detail page 或等价 workspace tab

#### Scenario: User views report actions without valid evidence

- **WHEN** completed job 没有有效球员空间、运动指标或结构化可视化证据
- **THEN** 报告动作 SHALL 保持可见但置灰、设置 `disabled` 或显示 unavailable 状态
- **AND** 点击、`onSelectView("report")` 或等价程序化导航 SHALL 不得打开报告内容
- **AND** SHALL 显示“暂无有效报告数据”或明确缺失原因

#### Scenario: User selects analysis details

- **WHEN** 用户从 completed job 结果中点击分析详情
- **THEN** 系统 SHALL 导航到 `/analysis/:jobId/details`

#### Scenario: Direct report URL has no evidence

- **WHEN** 用户直接访问没有有效报告证据的 `/analysis/:jobId/reports/:type`
- **THEN** 系统 SHALL 显示稳定的无有效报告空态并提供返回当前素材/任务的路径
- **AND** SHALL NOT 回退到 demo 报告或使用其他 Job 的产物
