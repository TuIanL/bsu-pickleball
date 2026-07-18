## Context

当前应用由 AppShell（sticky header + footer）包裹所有页面，无侧边导航。CaptureConsolePage 743 行，内联 5 个主要渲染函数。MiniTimeline 时间刻度只显示 3 个窗口边界标签。

## Goals / Non-Goals

**Goals:**
- 全局侧边栏导航，LandingPage 无侧边栏
- CaptureConsolePage 按新骨架（方案 A）重构
- MiniTimeline 等距刻度 + 重点标记轨道
- 侧边栏录制状态块通过独立 API 获取
- 视觉系统迁移（页面底色 #F7F8FA，绿色为品牌色）

**Non-Goals:**
- 不修改现有事件语义和后端业务模型
- 不修改双摄录制、停止恢复、Outbox 等核心逻辑
- 不做响应式手机端适配
- 不做复杂的缩放编辑器

## Decisions

### D1: AppShell 路由感知方式

**决策**: AppShell 通过 `routeName` prop 判断是否显示侧边栏。LandingPage (`routeName === "landing"`) 时不渲染 Sidebar。

```
AppShell
  ├── header (始终显示)
  ├── Sidebar (routeName !== "landing" 时显示)
  └── main content
```

**替代方案**: AppShell 始终渲染侧边栏，LandingPage 内部用 CSS 覆盖。不选原因：LandingPage 是全屏营销页，CSS 覆盖会导致不必要的重绘和样式泄漏。

**副作用**: AppShell 目前只接收 `activePath: string`，需要新增 `routeName: string` prop。

### D2: 侧边栏活跃录制状态获取

**决策**: 侧边栏使用独立 hook `useActiveCaptureTake`，内部轮询 `GET /api/capture-takes/active`。

```
Sidebar
  └── useActiveCaptureTake()
        └── GET /api/capture-takes/active
              → { takeId, startedAt, elapsedMs, status } | null
```

轮询间隔 5 秒。页面不可见时（`document.hidden`）暂停轮询。侧边栏自己维护时钟动画（`requestAnimationFrame`），不依赖控制台页面。

**替代方案**: React Context 共享 runtime 状态。不选原因：引入不必要的耦合，离开控制台页面后状态过时。

**后端接口规格**:
- `GET /api/capture-takes/active`
- 返回当前用户有且仅有一个活跃录制时的 CaptureTake 简略信息
- 没有活跃录制时返回 `null` / 204

### D3: CaptureConsolePage 重构策略（方案 A）

**第一阶段（骨架优先）**:
1. 在 `src/components/capture/` 下创建 `CaptureWorkspaceLayout.tsx`，定义新布局结构
2. 所有子组件插槽先用 `<CaptureWorkspaceLayout.Slot name="xxx">` 占位
3. 把现有 `CaptureConsolePage` 的顶级 `div` 替换为 `<CaptureWorkspaceLayout>`，内联渲染函数原封不动移入对应 slot
4. 此时页面功能完全不变，但已经在新骨架里

**第二阶段（提取组件）**:
1. 提取 `CameraPreviewGrid` / `CameraPreviewCard`
2. 提取 `RecordingControlPanel`
3. 提取 `LiveCodingPanel` → 内含 `EventActionToolbar`
4. 提取 `CaptureSidebar`（如果侧边栏尚未在 AppShell 中完成）
5. 提取 `RecentEventsCard` / `CaptureHealthCard` / `QuickActionsCard`
6. 每个提取步骤后验证功能无回归

**第三阶段（视觉迁移）**:
1. 引入 capture theme tokens（颜色、圆角、阴影变量）
2. 逐个组件切换样式：去绿色背景 → 白卡片 + 浅灰页底
3. 装置完成面板和合并状态提示到新位置

### D4: AppShell 与 CaptureWorkspaceLayout 的关系

**决策**: AppShell 提供全局壳（header + sidebar），CaptureWorkspaceLayout 只负责主区域内的布局。二者不嵌套耦合。

```
AppShell (全局壳)
  ├── header
  ├── Sidebar (全局导航)
  └── <main>
       └── CaptureWorkspaceLayout (仅 /capture/:id 页面使用)
            ├── CaptureWorkspaceHeader
            ├── CameraPreviewGrid
            ├── RecordingControlPanel
            ├── LiveCodingPanel
            └── BottomCards (RecentEvents / Health / QuickActions)
```

其他内部页面（如分析任务、报告中心）直接使用 AppShell 的 main 区域，不需要 CaptureWorkspaceLayout。

### D5: MiniTimeline 等距刻度算法

**决策**: 时间刻度从窗口范围计算整洁间隔，而非硬编码 3 个标签。

```
function computeTicks(windowStartMs, windowEndMs):
  1. 计算窗口宽度 = windowEndMs - windowStartMs
  2. 根据宽度选择间隔单位:
     < 30s  → 5s
     < 60s  → 10s
     < 5min → 30s
     else   → 1min
  3. 从 windowStartMs 向上取整到间隔单位的整数倍
  4. 生成刻度列表，直到 windowEndMs
  5. 如果窗口起点 > 0，在最左侧补一个刻度值（不一定是整洁值，保持参考）
```

刻度和像素位置一一对应，使用 `scale()` 映射函数。

### D6: 重点标记轨道

**决策**: MiniTimeline 新增第四根轨道，位于最底部，只显示 `highlight: true` 的 `add_note` / `session_note` 事件。

```
盘        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
局        ━━━━━━━━━━━━━━━━
分        [1]  [2]  [3]  [4]  [5]  [6]
重点标记         ◆              ◆
```

每个事件用菱形节点（现有 `svg` 星星形状可复用或改为实心菱形），位于轨道中线位置。轨道高度 20px。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 侧边栏轮询 API 不存在，阻塞侧边栏开发 | 先 mock 数据，后端接口作为独立任务跟进 |
| 方案 A Step 1 中旧代码填入新骨架时布局错乱 | 先用 max-w 限制主区域宽度，所有旧代码保持原 CSS class 不变，在骨架调试完成后再改样式 |
| MiniTimeline 刻度重写可能引入回归（播放头定位等） | 保留旧刻度渲染路径（通过 `staticMode` 开关切换），新刻度通过 feature flag 上线 |
| Sidebar 底部录制状态块在非录制页显示"无活跃录制"显得空旷 | 无录制时隐藏整个状态块，只显示导航项 |
