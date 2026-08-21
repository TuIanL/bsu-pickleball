# app-sidebar Specification

## Purpose
TBD - created by archiving change add-app-sidebar-and-active-capture-presence. Update Purpose after archive.
## Requirements
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

### Requirement: 侧边栏当前录制状态块

系统 MUST 在侧边栏底部显示当前活跃录制信息。

#### Scenario: 有活跃录制

- **WHEN** `GET /api/capture-takes/active` 返回录制数据
- **AND** 对应录制 session 可正常操作（非孤儿）
- **THEN** 侧边栏底部 SHALL 显示录制状态块
- **AND** 状态块 SHALL 包含：红色脉冲圆点、已录制时长（每秒更新）、会话名称、场地、录制模式、视频规格
- **AND** 底部 SHALL 显示弱化的「结束录制」按钮
- **AND** 点击状态块 SHALL 跳转到录制工作台（`primaryRoute`）

#### Scenario: 活跃录制为孤儿

- **WHEN** `getActiveCaptureTake()` 返回活跃录制
- **AND** 前端检测到该录制的控制台无法正常操作（hydrate 返回 `NO_ACTIVE_SESSION` 或 `HYDRATE_FAILED`）
- **THEN** `ActiveRecordingBlock` SHALL 额外展示「强制终止」按钮
- **AND** 点击「强制终止」SHALL 调用 `cancelRecording(takeId)` 或 `cancelSyncRecording(takeId)` 清理 session 和 CaptureTake
- **AND** 终止成功后 SHALL 清除活跃录制状态
- **AND** 终止成功后 SHALL 允许用户开始新录制（409 解除）

#### Scenario: 无活跃录制

- **WHEN** `GET /api/capture-takes/active` 返回 null
- **THEN** 侧边栏底部 SHALL 隐藏录制状态块

### Requirement: 侧边栏时钟校准

系统 MUST 使用服务器对齐的时钟计算，不依赖本地持续累加。

#### Scenario: 时钟计算

- **WHEN** 侧边栏显示录制时长
- **THEN** 系统 SHALL 使用 `setInterval` 每秒更新一次
- **AND** 计算公式 SHALL 为：`elapsedMs = Date.now() - startedAt.getTime() + serverClockOffset`
- **AND** `serverClockOffset` SHALL 在每次 API 响应时重新计算
- **AND** 系统 SHALL NOT 使用 `requestAnimationFrame` 驱动时钟

#### Scenario: 页面可见性

- **WHEN** `document.hidden` 为 true
- **THEN** 系统 SHALL 暂停轮询和时钟更新
- **WHEN** 页面恢复可见
- **THEN** 系统 SHALL 立即发起 API 请求
- **AND** 系统 SHALL 重新建立 5 秒轮询和 1 秒时钟
- **AND** 系统 SHALL 使用最新 `serverNow` 重新计算时钟

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

