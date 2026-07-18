## ADDED Requirements

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
- **THEN** 导航项 SHALL 包含：工作台、视频管理、分析任务、报告中心、设备管理、设置
- **AND** 每个导航项 SHALL 有对应图标和文字标签
- **AND** 当前活跃导航项 SHALL 以浅绿背景（`#EAF7EE`）和绿色文字（`#3BAA62`）高亮
- **AND** 非活跃项 SHALL 使用 `#475467` 文字色

#### Scenario: 导航跳转

- **WHEN** 用户点击导航项
- **THEN** 系统 SHALL 调用 `onNavigate()` 跳转到对应路径
- **AND** 高亮状态 SHALL 跟随当前路由更新

### Requirement: 侧边栏当前录制状态块

系统 MUST 在侧边栏底部显示当前活跃录制信息。

#### Scenario: 有活跃录制

- **WHEN** `GET /api/capture-takes/active` 返回录制数据
- **THEN** 侧边栏底部 SHALL 显示录制状态块
- **AND** 状态块 SHALL 包含：红色脉冲圆点、已录制时长（每秒更新）、会话名称、场地、录制模式、视频规格
- **AND** 底部 SHALL 显示弱化的「结束录制」按钮
- **AND** 点击状态块 SHALL 跳转到录制工作台（`primaryRoute`）

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
