## MODIFIED Requirements

### Requirement: 报告详情页默认渲染 PB Vision 风格新布局
当用户访问 `/report/:id` 或通过 `getReportRoute` 进入报告详情页时，页面 SHALL 默认采用 PB Vision 风格的新布局（左侧抽屉栏 + 亮色主题 + 模块卡片区）；原深绿风格 ReportPage 组件 SHALL 保留为可开关的 fallback 分支（通过 localStorage 或 query parameter `?legacy=1` 手动切回），但默认对所有用户显示新风格。

#### Scenario: 默认路由直接走 PB Vision 风格
- **WHEN** 用户以无 query 参数方式访问 `/report/:id`
- **THEN** 渲染管线 SHALL 挂载 `PbVisionReportLayout` 组件
- **AND** 页面 SHALL 加载荧光亮绿主题 CSS 变量
- **AND** 各模块 SHALL 按新 spec 依次渲染（球员信息卡→3D 球场→Filter→Skill Rating→Court Coverage→Serves/Returns→Coach Insight→Legal Thirds）

#### Scenario: 传 legacy=1 切回旧布局
- **WHEN** 用户以 `/report/:id?legacy=1` 方式访问
- **THEN** 页面 SHALL 回退渲染原 ReportPage 组件（保留既有行为）
- **AND** 主题 SHALL 恢复深绿配色，不渲染左侧抽屉栏

---

### Requirement: 报告页路由不影响分析工作区和其他页面
本修改 SHALL 仅作用于 `/report/:id` 路由对应的组件树；首页、录制控制台、`/analysis` 分析工作区、`/training` 训练页等其他页面的布局和配色 SHALL 保持不变。

#### Scenario: 其他页面保持原样
- **WHEN** 用户从报告页跳出到 `/sessions` 或 `/analysis`
- **THEN** 全局 AppShell、侧边栏、顶部导航 SHALL 与改造前完全一致
- **AND** PB Vision 亮色主题 SHALL 仅在报告页内生效（通过 scoped class 或局部包裹），不得泄漏到全局
