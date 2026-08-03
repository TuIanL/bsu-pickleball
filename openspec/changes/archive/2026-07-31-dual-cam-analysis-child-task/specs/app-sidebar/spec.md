## MODIFIED Requirements

### Requirement: 全局侧边栏导航

系统 MUST 在所有内部页面（非 landing 模式）左侧显示固定侧边栏导航。

#### Scenario: 布局模式控制

- **WHEN** shellMode 为 `landing`
- **THEN** 侧边栏 SHALL 不渲染
- **WHEN** shellMode 为 `standard` 或 `capture`
- **THEN** 侧边栏 SHALL 固定在左侧，宽度 216px，从顶部延伸至视口底部
- **AND** 侧边栏右侧 SHALL 有 `#E4E7EC` 1px 边框与主区域分隔

#### Scenario: 导航项

- **WHEN** 侧边栏渲染
- **THEN** 导航项 SHALL 包含：工作台、视频管理（→`/capture`）、分析任务（→`/analysis/tasks`）、报告中心、设备管理、设置
- **AND** 每个导航项 SHALL 有对应图标和文字标签
- **AND** 当前活跃导航项 SHALL 以浅绿背景（`#EAF7EE`）和绿色文字（`#3BAA62`）高亮
- **AND** 非活跃项 SHALL 使用 `#475467` 文字色

#### Scenario: 导航跳转

- **WHEN** 用户点击导航项
- **THEN** 系统 SHALL 调用 `onNavigate()` 跳转到对应路径
- **AND** 高亮状态 SHALL 跟随当前路由更新
- **AND**「视频管理」SHALL 跳转到 `/capture`（录制管理 / 现场采集）
- **AND**「分析任务」SHALL 跳转到 `/analysis/tasks`（分析任务列表）
