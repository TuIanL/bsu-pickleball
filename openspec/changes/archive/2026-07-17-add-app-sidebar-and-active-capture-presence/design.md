## Context

当前 AppShell 只有 sticky header + footer，不渲染任何侧边导航。路由系统通过 `parsePath` 将 URL 映射为 `RouteState`，但 `RouteState` 不包含布局模式信息。LandingPage 混合了品牌营销和功能入口（录制、上传、历史任务）。

## Goals / Non-Goals

**Goals:**
- AppShell 支持 `landing` / `standard` / `capture` 三种布局模式
- AppSidebar 在所有内部页面显示，LandingPage 不显示
- 活跃录制 API 可供 Sidebar 和其他独立组件消费
- LandingPage 保留营销内容，增加「进入平台」CTA

**Non-Goals:**
- 不修改现有录制状态机、事件标注、Outbox 等核心业务逻辑
- 不做 CaptureConsolePage 内部布局或视觉重构（属于 Change B）
- 不做页面级别的权限控制

## Decisions

### D1: AppShellMode 路由元数据

路由元数据中新增 `shellMode` 字段，替代简单的字符串对比。

```ts
// navigationTypes.ts
type AppShellMode = "landing" | "standard" | "capture";

interface RouteState {
  name: string;
  path: AppPath;
  shellMode: AppShellMode;  // 新增
  // ... 其他字段
}
```

映射规则：
- `landing` → shellMode: "landing"（无 sidebar，营销 footer）
- `capture*` 路由 → shellMode: "capture"（sidebar，无全局 header，无 footer）
- 其余内部页面（analysis, camera, training 等）→ shellMode: "standard"（sidebar，简洁 topbar，无 footer）

内部页面是后台工作环境，营销 Footer 不应出现。

AppShell 根据 `shellMode` 控制渲染：

```
landing:     [Header(营销)]  [Main]  [Footer(营销)]
standard:    [Sidebar]  [Topbar]  [Main]
capture:     [Sidebar]  [Main]  ← 无 Topbar，无 Footer
```

### D2: 侧边栏活跃录制时钟

**不**使用 `requestAnimationFrame`。改为 `setInterval(1000)` + 服务器对齐公式：

```ts
elapsedMs = Date.now() - new Date(startedAt).getTime() + serverClockOffset;
serverClockOffset = new Date(serverNow).getTime() - Date.now();
```

`serverNow` 来自 API 响应中的 `serverNow` 字段。时钟独立于轮询周期——轮询每 5 秒一次，时钟每秒更新一次。

页面隐藏时暂停 `setInterval`，重新可见时：
1. 立即发起一次 API 请求
2. 重新建立 5 秒轮询
3. 重新计算时钟

### D3: 活跃录制 API 设计

接口规格：

```
GET /api/capture-takes/active
```

成功 (200):

```json
{
  "takeId": "uuid",
  "fieldSessionId": "uuid",
  "captureTakeId": "uuid",
  "startedAt": "2026-07-17T10:30:00Z",
  "serverNow": "2026-07-17T10:42:15Z",
  "status": "recording",
  "title": "训练记录_2026-07-16",
  "courtName": "标准场地 1 号",
  "captureMode": "dual",
  "videoSpec": {
    "width": 1920,
    "height": 1080,
    "fps": 60
  }
}
```

无活跃录制 (200):

```json
null
```

唯一性约束：系统从业务上禁止同一用户同时拥有两个活跃 CaptureTake。活跃定义为 status ∈ {starting, recording, stopping, recovering, finalizing}。completed / partial / failed / canceled 不算活跃。

原子性约束：检查和创建必须在一个原子操作中完成（SQLite 事务或应用层锁），防止并发请求创建两个活跃 Take。
- `startRecording` 和 `startSyncRecording` 入口统一执行活跃检查 + 创建的事务
- 恢复中的 Take 和 stopping/finalizing 中的 Take 均视为活跃，阻止新录制启动

用户作用域：当前系统为单机部署，没有用户认证。因此采用全局约束——整个系统最多一个活跃 CaptureTake。如果未来引入多用户，约束可升级为按 user_id 限制。

`fieldSessionId` + `captureTakeId` 供前端构造导航路径，前端持有导航函数和路由表，不依赖后端返回拼接好的 `primaryRoute`。

### D6: 侧边栏导航高亮

路由新增 `navigationSection` 字段，类型为联合：

```ts
type NavigationSection =
  | "capture"
  | "videos"
  | "analysis"
  | "reports"
  | "devices"
  | "settings";
```

Sidebar 的导航高亮根据 `route.navigationSection` 匹配，而非 `routeName` 字符串。capture-home / capture-console / segment-manager 都映射到 `"capture"` 段，高亮「工作台」项。

### D7: useActiveCaptureTake 的请求竞争保护

hook 内部使用 request sequence id 或 AbortController 防止过期请求覆盖新状态。重新可见时先 abort 正在进行的请求再发起新请求。组件卸载时清理所有 interval 和 abort 控制器。

### D8: 滚动容器契约

capture 模式下，AppShell 指定滚动容器为 `window`（浏览器窗口滚动），而非 shell-main 内部滚动。这样 CaptureWorkspaceLayout 的 sticky 元素（录制控制栏、标题栏）和 DeviceDrawer 的 fixed 定位在与 window 滚动配合时行为一致，避免双滚动条。两个 Change 都基于此契约。

### D4: LandingPage 处理

LandingPage 保持现有品牌展示、产品介绍等营销内容。移除：
- 历史任务入口
- 上传视频入口
- 进入实时拍摄按钮（迁移至 Sidebar 导航中）

增加：

```
┌─────────────────────────────────────┐
│       品牌/产品介绍（保留）           │
│                                     │
│  其他营销区块（保留）                 │
│                                     │
│   ┌─────────────────────────┐       │
│   │   进入开始使用           │       │
│   └─────────────────────────┘       │
└─────────────────────────────────────┘
```

CTA 按钮跳转至 `/capture`（CaptureHomePage）。

### D5: 旧 change 的迁移

原 `refactor-navigation-and-capture-console` change 中的 `app-sidebar` 和 `frontend-capture-runtime` delta spec 迁移至此 change。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| AppShellMode 新增字段需要同步更新所有 RouteState 创建点 | 所有路由通过 `parsePath` 集中创建，只需在 `router.ts` 中一次性补充 |
| Sidebar 底部录制块在切换页面时闪烁 | useActiveCaptureTake 使用稳定的 loading/error/empty 状态驱动渲染 |
| LandingPage 移除操作入口后，新用户不知道如何开始 | Sidebar 导航中「工作台」项与 CTA 指向同一入口 |
| 服务器时间与客户端时间偏差 | serverClockOffset 在每次 API 响应时重新计算，5 秒轮询间隔内偏差可控 |
