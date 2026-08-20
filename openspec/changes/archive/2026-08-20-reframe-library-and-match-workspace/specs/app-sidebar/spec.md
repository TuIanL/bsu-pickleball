## ADDED Requirements

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

#### Scenario: 视频管理名称消除
- **WHEN** 侧边栏渲染
- **THEN** 不再以「视频管理」命名跳转 `/capture`；「现场采集」指向 `/capture`，避免名称与对象不一致

### Requirement: 工作台路由收敛
`/workspace` 路由 SHALL 保留以兼容，但本工作区暂以 alias/redirect 到 `/library` 呈现，不展示「建设中」占位主导航。

#### Scenario: 访问 /workspace
- **WHEN** 用户或历史链接访问 `/workspace`
- **THEN** 系统 SHALL 路由到 `/library`（内容等价呈现）
- **AND** SHALL NOT 展示「工作台（建设中）」空占位

### Requirement: 侧边栏活跃录制状态块保留
侧边栏底部 SHALL 保留跨页面显示当前活跃录制状态的能力（红色脉冲圆点、已录制时长、会话/场地/模式/规格、「结束录制」、孤儿强制终止），规则维持原引擎语义。

#### Scenario: 有活跃录制
- **WHEN** `GET /api/capture-takes/active` 返回录制数据且可正常操作
- **THEN** 侧边栏底部 SHALL 显示录制状态块并每秒更新时长

#### Scenario: 无活跃录制
- **WHEN** 活跃录制接口返回 null
- **THEN** 侧边栏底部 SHALL 隐藏录制状态块