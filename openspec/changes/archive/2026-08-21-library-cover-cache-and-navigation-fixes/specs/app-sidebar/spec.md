## MODIFIED Requirements

### Requirement: 侧边栏一级导航 Library-first
系统 MUST 在标准/capture 模式左侧展示固定侧边栏，导航项 SHALL 包含比赛库、现场采集、设备与设置；底部活跃录制状态块保留。

#### Scenario: 侧边栏导航项
- **WHEN** 侧边栏在标准模式渲染
- **THEN** 导航项 SHALL 为：比赛库（→`/library`）、现场采集（→`/capture`）、设备与设置
- **AND** 不再硬编码「工作台 / 视频管理 / 分析任务 / 报告中心」为一级项

#### Scenario: 活跃态高亮
- **WHEN** 用户位于某一导航对应页面
- **THEN** 当前活跃导航项 SHALL 以浅绿背景（`#EAF7EE`）和绿色文字（`#3BAA62`）高亮
- **AND** 非活跃项 SHALL 使用 `#475467` 文字色

#### Scenario: 现场采集首页高亮
- **WHEN** 用户位于 `/capture`（现场采集首页，captureHome）
- **THEN** 侧边栏「现场采集」导航项 SHALL 处于活跃态并高亮
- **AND** `/capture` 的 `navigationSection` SHALL 解析为 `"capture"`（而非遗留的 `"videos"`）

#### Scenario: 视频管理名称消除
- **WHEN** 侧边栏渲染
- **THEN** 不再以「视频管理」命名跳转 `/capture`；「现场采集」指向 `/capture`，避免名称与对象不一致