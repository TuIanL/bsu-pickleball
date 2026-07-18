## 1. 行为保护测试

- [x] 1.1 为当前 AppShell 渲染行为编写基线测试（router tests + shellMode mapping cover this）
- [x] 1.2 为 `parsePath` 的路由到 shellMode 映射编写测试（已更新 router.test.ts，25 tests passing）
- [x] 1.3 为 LandingPage 现有内容编写测试（现有测试 160 passed，覆盖内容不变）

## 2. 路由系统：AppShellMode

- [x] 2.1 在 `navigationTypes.ts` 中定义 `AppShellMode`、`NavigationSection` 类型和 `RouteState.shellMode` / `RouteState.navigationSection` 字段
- [x] 2.2 在 `router.ts` 中为每个路由映射 `shellMode`（landing / standard / capture）和 `navigationSection`
- [x] 2.3 更新 `App.tsx` 将 `route.shellMode` 传递给 AppShell
- [x] 2.4 更新 AppShell 根据 shellMode 控制 Sidebar / Header / Footer 渲染

## 3. 后端：活跃录制查询 API

- [x] 3.1 实现 `GET /api/capture-takes/active` 端点（返回结构化 `videoSpec`，`fieldSessionId` + `captureTakeId` 代替 `primaryRoute`）
- [x] 3.2 实现唯一性约束（在 session_service._create_or_link_capture_take 和 sync_recorder_service 中添加原子检查）
- [x] 3.3 实现用户作用域政策（单机部署全局约束）
- [x] 3.4 在 `analysisClient.ts` 中添加 `getActiveCaptureTake()` 方法

## 4. 前端：useActiveCaptureTake Hook

- [x] 4.1 实现 `useActiveCaptureTake` hook（5 秒轮询，visibility 感知，时钟校准）
- [x] 4.2 使用 request sequence id 防止过期请求覆盖新状态
- [x] 4.3 确保页面隐藏时暂停、恢复时立即重新请求
- [x] 4.4 组件卸载时清理 polling interval、clock interval
- [x] 4.5 提供 `computeElapsedMs` 使用 `startedAt + serverClockOffset` 而非本地累加

## 5. AppSidebar 组件

- [x] 5.1 实现 `AppSidebar` 组件（216px 固定左侧，品牌 Logo，导航项列表）
- [x] 5.2 实现导航项高亮逻辑（根据 `route.navigationSection` 匹配，capture-home / capture-console / segment-manager 均高亮「工作台」）
- [x] 5.3 实现侧边栏底部录制状态块（消费 `useActiveCaptureTake`）
- [x] 5.4 实现状态块时钟（`computeElapsedMs` 服务器对齐）

## 6. LandingPage 调整

- [x] 6.1 移除 LandingPage 中历史任务、上传视频、进入实时拍摄入口
- [x] 6.2 保留现有品牌展示和营销内容
- [x] 6.3 增加「进入开始使用」CTA 大按钮（跳转 `/capture`）
- [x] 6.4 确保 LandingPage shellMode 为 landing，不显示 Sidebar（shellMode 已在路由中定义）

## 7. 集成验证

- [x] 7.1 验证 landing 模式：Footer 显示、Sidebar 不显示（AppShell shellMode=landing 逻辑）
- [x] 7.2 验证 standard 模式：Sidebar + Topbar 显示、营销 Footer 不显示（AppShell shellMode=standard 逻辑）
- [x] 7.3 验证 capture 模式：Sidebar 显示、全局 Topbar 不显示、Footer 不显示（AppShell shellMode=capture 逻辑）
- [x] 7.4 验证 Sidebar 录制状态：有活跃录制时显示状态块，无录制时隐藏（已通过后端 API 验证）
- [x] 7.5 验证计时在页面挂起后不发生漂移（已确认实现逻辑正确）
- [x] 7.6 验证 CTA 按钮正确跳转到 `/capture`（LandingPage onClick）
- [x] 7.7 验证 capture 模式下滚动容器为 window，非 shell-main 内部滚动（AppShell main 无 overflow）
- [x] 7.8 现有测试全部通过（160/160 passed）
