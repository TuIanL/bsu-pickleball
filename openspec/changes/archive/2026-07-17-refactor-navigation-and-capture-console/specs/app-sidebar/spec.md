## ADDED Requirements

### Requirement: 全局侧边栏导航

系统 MUST 在所有内部页面（非 LandingPage）左侧显示固定侧边栏导航。

#### Scenario: 侧边栏布局

- **WHEN** 用户处于 LandingPage (`/`)
- **THEN** 侧边栏 SHALL 不渲染
- **WHEN** 用户处于任何内部页面（`/capture`、`/analysis/*`、`/camera` 等）
- **THEN** 侧边栏 SHALL 固定在左侧，宽度 216px
- **AND** 侧边栏 SHALL 从顶部延伸到视口底部
- **AND** 侧边栏右侧 SHALL 有一条 `#E6E9EE` 1px 边框与主区域分隔

#### Scenario: 导航项高亮

- **WHEN** 当前页面路径匹配某个导航项
- **THEN** 该导航项 SHALL 以浅绿色背景（`#EAF7EE`）和绿色文字（`#3BAA62`）高亮
- **AND** 其他导航项 SHALL 使用默认文字色（`#667085`）

#### Scenario: 导航项点击跳转

- **WHEN** 用户点击导航项
- **THEN** 系统 SHALL 调用 `onNavigate()` 跳转到对应路径
- **AND** 高亮状态 SHALL 随之更新

### Requirement: 侧边栏当前录制状态块

系统 MUST 在侧边栏底部显示当前活跃录制的小部件。

#### Scenario: 有活跃录制

- **WHEN** `GET /api/capture-takes/active` 返回活跃录制数据
- **THEN** 侧边栏底部 SHALL 显示录制状态块
- **AND** 状态块 SHALL 包含：录制状态指示灯（红色脉冲圆点）、已录制时长（实时递增）、会话名称、场地、录制模式、视频规格
- **AND** 时长 SHALL 使用 `requestAnimationFrame` 实现连续平滑更新
- **AND** 底部 SHALL 显示弱化的"结束录制"按钮

#### Scenario: 无活跃录制

- **WHEN** `GET /api/capture-takes/active` 返回 null
- **THEN** 侧边栏底部 SHALL 不显示录制状态块
- **AND** 侧边栏 SHALL 只显示导航项

### Requirement: 侧边栏轮询与生命周期

系统 MUST 使用独立 hook 管理侧边栏的活跃录制查询，不依赖 CaptureConsolePage。

#### Scenario: 轮询间隔

- **WHEN** 侧边栏可见且已挂载
- **THEN** 系统 SHALL 每 5 秒调用 `GET /api/capture-takes/active`
- **AND** 系统 SHALL 监听 `document.visibilitychange`
- **WHEN** 页面隐藏
- **THEN** 系统 SHALL 暂停轮询
- **WHEN** 页面重新可见
- **THEN** 系统 SHALL 恢复轮询
