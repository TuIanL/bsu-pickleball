## ADDED Requirements

### Requirement: CaptureWorkspaceLayout 新骨架

系统 MUST 为 CaptureConsolePage 提供 CaptureWorkspaceLayout 作为新的顶级布局壳。

#### Scenario: 骨架结构

- **WHEN** CaptureConsolePage 渲染
- **THEN** 顶级容器 SHALL 使用 CaptureWorkspaceLayout
- **AND** 布局区域 SHALL 按顺序排列为：页面标题栏、摄像机预览、录制控制栏、事件标注时间线、底部信息行
- **AND** 页面内容左右 SHALL 有 24—32px padding
- **AND** 页面背景色 SHALL 为 `var(--surface-page)`
- **AND** 卡片 SHALL 使用 `var(--surface-card)` + `var(--shadow-card)`

#### Scenario: 组件树关系

- **WHEN** CaptureWorkspaceLayout 渲染子组件
- **THEN** 子组件关系 SHALL 如下：
  - `CaptureWorkspaceLayout` 直接渲染 `CaptureWorkspaceHeader`、`CameraPreviewGrid`、`RecordingControlPanel`、`LiveCodingPanel`、底部行
  - `LiveCodingPanel` 包含 `EventActionToolbar` + `CaptureTimeline`（内含 MiniTimeline）
  - 底部行包含 `RecentEventsCard` + `CaptureHealthCard` + `QuickActionsCard`

#### Scenario: 响应式布局

- **WHEN** 窗口宽度 >= 1280px
- **THEN** 双摄模式摄像机预览 SHALL 并排等宽
- **AND** 底部三栏 SHALL 并排等宽
- **WHEN** 窗口宽度在 1024—1280px
- **THEN** 底部三栏 SHALL 变 2+1 排列
- **AND** 控制栏次要字段 SHALL 隐藏
- **WHEN** 窗口宽度 < 1024px
- **THEN** 双摄 SHALL 上下排列
- **AND** 底部卡片 SHALL 单列排列

### Requirement: ViewModel 模式

系统 MUST 使用 ViewModel 模式分离页面层与展示组件。

#### Scenario: ViewModel 构造

- **WHEN** CaptureConsolePage 渲染 CaptureWorkspaceLayout
- **THEN** 页面层 SHALL 构造 `CaptureWorkspaceViewModel`
- **AND** ViewModel SHALL 在 `useMemo` 中派生
- **AND** 每个子组件 SHALL 只接收自己需要的 ViewModel 片段
- **AND** 子组件 SHALL NOT 直接调用业务 hooks
- **AND** 子组件 SHALL NOT 直接调用 API

### Requirement: 真实数据策略

系统 MUST 使用真实数据源驱动底部健康指标卡，禁止硬编码运行指标。

#### Scenario: 数据状态渲染

- **WHEN** 有可靠数据
- **THEN** CaptureHealthCard SHALL 显示数值 + 状态标签
- **WHEN** API 数据加载中
- **THEN** CaptureHealthCard SHALL 显示 skeleton 占位符
- **WHEN** 当前后端不支持该指标
- **THEN** 该项 SHALL 不渲染（非隐藏占位符）
- **WHEN** 数据获取失败
- **THEN** 该项 SHALL 显示"暂不可用"
