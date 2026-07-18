## Context

两个已归档 Change 验收中暴露 7 个 bug，均为实现问题而非需求变更。涉及 AppSidebar 导航映射、AppShell 顶部栏、CaptureConsolePage 布局与错误处理。

## Goals / Non-Goals

**Goals:**
- 修复侧边栏三个导航项的路径映射
- 移除 standard 模式顶部栏，首页跳转放侧边栏 Logo
- 录制状态块整块可点击跳转
- 修复时钟计算逻辑
- 删除重复的存储位置行
- 改善控制区布局紧凑问题
- 录制失败时显示错误诊断信息

**Non-Goals:**
- 不改动任何后端 API
- 不改动业务 hooks（useCaptureRuntime / useLiveCoding 等）
- 不改动事件语义或数据模型
- 不做视觉 redesign

## Decisions

### D1: 导航映射修正

| 导航项 | 当前路径 | 修正路径 | navigationSection |
|--------|----------|----------|-------------------|
| 工作台 | `/capture` | 留空（后续补） | `capture` |
| 视频管理 | `/recording`（无此路由→首页） | `/analysis/tasks`（任务管理） | `videos` |
| 分析任务 | `/analysis/tasks` | `/capture`（采集任务列表） | `analysis` |

侧边栏品牌 Logo 区域增加 `onClick={() => onNavigate("/")}`。

### D2: 顶部栏移除

standard 模式不再渲染 Topbar。AppShell 中 `!isCapture` 条件改为 `isLanding`——只有 landing 模式显示顶栏。

```diff
- {!isCapture && (
+ {isLanding && (
    <header>...</header>
  )}
```

### D3: 状态块点击

`ActiveRecordingBlock` 的整块外层容器改为 `<button>`，点击调用 `onNavigate` 跳转到录制工作台。删除内部的「结束录制」按钮。

```diff
- <div className="border-t ...">
-   <button className="结束录制">...</button>
- </div>
+ <button className="border-t ... w-full text-left" onClick={() => onNavigate(...)}>
+   ...
+ </button>
```

### D4: 时钟修正

`computeElapsedMs` 中的 `serverClockOffset` 需要确保每次 API 响应都更新。当前问题可能是 `serverNow` 字段在轮询响应中没有被正确传递，导致时钟从错误基线计算。确保 `useActiveCaptureTake` 在轮询响应中将 `serverNow` 存入 ref 供 `computeElapsedMs` 使用。

### D5: 重复存储位置

删除 CaptureConsolePage 第 484-498 行的「录制保存位置」卡片。Header 中的文件夹图标已提供此入口。

### D6: 控制区布局

将「设备」「新录制」按钮移入 `RecordingControlPanel` 组件内部，避免 flex 容器挤压控制面板宽度。或改用 grid 布局。

### D7: 录制失败诊断

`RecordingControlPanel` 中新增 `error?: string` prop。当 `runtime.phase === "failed"` 时，在控制区下方显示红色错误信息卡片。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 顶部栏移除后 standard 页面失去返回首页的入口 | 侧边栏 Logo 增加首页跳转 |
| 导航映射改完后用户找不到之前的位置 | 所有变更都在同一 change 中，一次性改到位 |
| 时钟修正依赖后端 `serverNow` 字段准确 | hook 层增加防卫性检查：偏差超过 1 小时时不显示 |
