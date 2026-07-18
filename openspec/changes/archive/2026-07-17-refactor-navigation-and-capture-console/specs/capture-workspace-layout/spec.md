## ADDED Requirements

### Requirement: CaptureWorkspaceLayout 骨架

系统 MUST 提供 CaptureWorkspaceLayout 组件作为录制工作台的布局壳。

#### Scenario: 整体结构

- **WHEN** CaptureConsolePage 渲染
- **THEN** 页面 SHALL 使用 CaptureWorkspaceLayout 作为顶级容器
- **AND** 布局 SHALL 包含以下区域按顺序排列：页面标题栏、摄像机实时预览、录制控制栏、事件标注时间线卡片、底部三栏信息卡片
- **AND** 布局 SHALL NOT 被 AppShell 的 header 或 footer 遮挡内容

#### Scenario: 布局区域定义

- **WHEN** 窗口宽度 >= 1280px
- **THEN** 以下布局规则 SHALL 生效：
  - 双摄模式下摄像机预览并排等宽
  - 底部三栏并排等宽
  - 页面内容左右各有 24—32px padding

#### Scenario: 布局响应式

- **WHEN** 窗口宽度在 1024—1280px
- **THEN** 侧边栏宽度 SHALL 缩减到 180px
- **AND** 控制栏次要字段 SHALL 隐藏
- **WHEN** 窗口宽度 < 1024px
- **THEN** 双摄 SHALL 改为上下排列
- **AND** 底部卡片 SHALL 单列排列

### Requirement: 视觉 Token 系统

系统 MUST 使用统一的视觉 Token 驱动 CaptureConsolePage 的样式。

#### Scenario: Token 定义

- **THEN** 系统 SHALL 定义以下颜色 Token：
  - `pageBg`: `#F7F8FA`
  - `cardBg`: `#FFFFFF`
  - `border`: `#E6E9EE`
  - `textPrimary`: `#18212F`
  - `textSecondary`: `#667085`
  - `textMuted`: `#98A2B3`
  - `brand`: `#3BAA62`
  - `brandSoft`: `#EAF7EE`
  - `danger`: `#E5484D`
  - `info`: `#4F7DF3`
  - `warning`: `#F59E42`
- **AND** 系统 SHALL 使用圆角 Token：`sm: 8px`、`md: 12px`、`lg: 16px`
- **AND** 卡片阴影 SHALL 统一为 `0 1px 2px rgba(16,24,40,0.04), 0 4px 12px rgba(16,24,40,0.03)`

#### Scenario: Token 作用范围

- **WHEN** Token 生效
- **THEN** 页面背景色 SHALL 为 `pageBg`
- **AND** 卡片背景 SHALL 为 `cardBg`
- **AND** 卡片间边框 SHALL 使用 `border`
- **AND** 绿色 Token 仅用于品牌标识、正常状态和强调元素
- **AND** 页面 SHALL NOT 使用大面积绿色渐变背景

### Requirement: 组件树

系统 MUST 按以下组件树拆分 CaptureConsolePage。

#### Scenario: 组件提取

- **WHEN** 实现完成
- **THEN** 以下组件 SHALL 存在且职责清晰：
  - `CaptureWorkspaceHeader`：页面标题、状态标签、存储空间、设置入口
  - `CameraPreviewGrid`：摄像机预览网格容器
  - `CameraPreviewCard`：单路摄像机预览卡片（含状态覆盖标签）
  - `RecordingControlPanel`：录制控制与信息条
  - `LiveCodingPanel`：事件标注时间线卡片容器
  - `EventActionToolbar`：事件按钮分组工具栏
  - `CaptureTimeline`：多层事件时间线（含 MiniTimeline）
  - `RecentEventsCard`：最近事件列表
  - `CaptureHealthCard`：系统状态信息
  - `QuickActionsCard`：快捷操作入口

#### Scenario: 组件数据流

- **WHEN** 上述组件渲染
- **THEN** 每个展示组件 SHALL 通过 props 接收数据
- **AND** 组件 SHALL NOT 直接调用 API 或 hooks（业务 hooks 集中在 CaptureConsolePage 调用）
- **AND** 组件 SHALL NOT 内部维护业务状态
