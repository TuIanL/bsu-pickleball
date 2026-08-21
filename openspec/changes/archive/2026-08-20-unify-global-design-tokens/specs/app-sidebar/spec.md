# app-sidebar

## MODIFIED Requirements

### Requirement: 全局侧边栏导航

系统 MUST 在所有内部页面（非 landing 模式）左侧显示固定侧边栏导航。

#### Scenario: 布局模式控制

- **WHEN** shellMode 为 `landing`
- **THEN** 侧边栏 SHALL 不渲染
- **WHEN** shellMode 为 `standard` 或 `capture`
- **THEN** 侧边栏 SHALL 固定在左侧，宽度 216px，从顶部延伸至视口底部
- **AND** 侧边栏右侧 SHALL 有 `var(--capture-border-default)`（`#D9E3DD`）1px 边框与主区域分隔

#### Scenario: 导航项

- **WHEN** 侧边栏渲染
- **THEN** 导航项 SHALL 包含：工作台、视频管理（→`/capture`）、分析任务（→`/analysis/tasks`）、报告中心、设备管理、设置
- **AND** 每个导航项 SHALL 有对应图标和文字标签
- **AND** 当前活跃导航项 SHALL 采用「左侧 3px 强调条 `var(--capture-brand-primary)`（#23985B）+ 浅绿底 `var(--capture-nav-active-bg)`（#E6F3EA）+ 深绿字 `var(--capture-nav-active-text)`（#1B824C）」高亮，而非整块浅绿按钮
- **AND** 非活跃项 SHALL 使用 `var(--capture-text-secondary)`（`#64736C`）文字色

#### Scenario: 导航跳转

- **WHEN** 用户点击导航项
- **THEN** 系统 SHALL 调用 `onNavigate()` 跳转到对应路径
- **AND** 高亮状态 SHALL 跟随当前路由更新
- **AND**「视频管理」SHALL 跳转到 `/capture`（录制管理 / 现场采集）
- **AND**「分析任务」SHALL 跳转到 `/analysis/tasks`（分析任务列表）

### Requirement: 侧边栏一级导航 Library-first
系统 MUST 在标准/capture 模式左侧展示固定侧边栏，导航项 SHALL 包含比赛库、现场采集、设备与设置；底部活跃录制状态块保留。

#### Scenario: 侧边栏导航项
- **WHEN** 侧边栏在标准模式渲染
- **THEN** 导航项 SHALL 为：比赛库（→`/library`）、现场采集（→`/capture`）、设备与设置
- **AND** 不再硬编码「工作台 / 视频管理 / 分析任务 / 报告中心」为一级项

#### Scenario: 活跃态高亮
- **WHEN** 用户位于某一导航对应页面
- **THEN** 当前活跃导航项 SHALL 采用「左侧 3px 强调条 `var(--capture-brand-primary)`（#23985B）+ 浅绿底 `var(--capture-nav-active-bg)`（#E6F3EA）+ 深绿字 `var(--capture-nav-active-text)`（#1B824C）」高亮
- **AND** 非活跃项 SHALL 使用 `var(--capture-text-secondary)`（`#64736C`）文字色

#### Scenario: 视频管理名称消除
- **WHEN** 侧边栏渲染
- **THEN** 不再以「视频管理」命名跳转 `/capture`；「现场采集」指向 `/capture`，避免名称与对象不一致
