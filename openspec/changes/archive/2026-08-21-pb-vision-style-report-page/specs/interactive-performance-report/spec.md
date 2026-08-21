## MODIFIED Requirements

### Requirement: 表现洞察面板适配 PB 风格容器与球员抽屉切换
原 PerformanceInsightsPanel 组件 SHALL 被整合进 PB Vision 风格报告页的模块卡片流中（可作为附加模块保留），且 SHALL 响应来自左侧球员抽屉栏的选中球员切换事件：切换后维度卡片、findings、recommendations 等所有球员相关内容 SHALL 即时刷新。

#### Scenario: 抽屉栏切换球员时表现洞察同步刷新
- **WHEN** 用户在 PB Vision 报告页的左侧抽屉栏切换选中球员
- **THEN** PerformanceInsightsPanel 内部展示的 dimensions（含 strength/stable 状态）、findings 列表、recommendations 列表 SHALL 同步切换到该球员
- **AND** 球员切换按钮（原 PerformanceInsightsPanel 内部自带的 T1/T2/T3/T4 按钮）可保留但 SHALL 与抽屉栏选中态保持双向同步

---

### Requirement: 表现洞察卡容器样式适配 PB 亮色主题
被整合进 PB 风格报告页时，PerformanceInsightsPanel 的外层卡片 SHALL 使用 PB 风格的白底+圆角+浅灰边框（而非原深绿风格）；内部 skill 进度条 SHALL 改为荧光亮绿 (#00FF41) 填充。

#### Scenario: 在 PB 风格页内渲染的样式适配
- **WHEN** PerformanceInsightsPanel 挂载在 PbVisionReportLayout 树下
- **THEN** 卡片 SHALL 使用 `.pb-card` CSS class（白底 + 圆角 + 1px #E5E7EB 边框）
- **AND** 进度条填充色 SHALL 覆盖为 `--pb-primary` (#00FF41)
- **WHEN** PerformanceInsightsPanel 在 legacy 报告页或其他页面渲染
- **THEN** 原有深绿风格样式 SHALL 保持不变
