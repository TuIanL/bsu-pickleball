## Why

当前应用缺少专业级站点应有的导航层次——所有页面由 AppShell 的顶部 header 承载，无侧边导航，用户在不同功能模块（采集、分析、设备）之间切换缺乏一致的导航上下文。同时 LandingPage 承载了过多功能入口（上传、历史任务、进入录制），与营销落地页的定位模糊。

## What Changes

- **AppShell 升级为 Shell Mode**: 定义 `landing` / `standard` / `capture` 三种布局模式，控制 Sidebar、Header、Footer 的渲染规则
- **AppSidebar 全局侧边栏导航**: 216px 固定左侧，所有内部页面共享
- **LandingPage**: 保留现有品牌展示和营销内容；隐藏 Sidebar；补充明显的「进入平台」CTA 按钮；移除历史任务、上传视频等操作入口（这些应在内部导航中完成）
- **活跃录制查询**: 新增 `GET /api/capture-takes/active` 接口，供 Sidebar 底部状态块独立消费
- **useActiveCaptureTake hook**: 封装轮询逻辑，`setInterval` 计时，与服务器时钟校准，避免漂移

## Capabilities

### New Capabilities
- `app-sidebar`: 全局侧边栏导航组件，含导航项高亮、品牌标识、底部活跃录制状态块

### Modified Capabilities
- `frontend-capture-runtime`: 新增活跃录制查询 API 端点（`GET /api/capture-takes/active`）及对应前端 hook

## Impact

- **AppShell.tsx**: 从 static header 升级为 multi-mode 布局壳，根据 mode 切换 sidebar/header/footer
- **App.tsx**: 路由系统传递 shellMode 到 AppShell
- **router.ts / navigationTypes.ts**: 路由元数据新增 shellMode 字段
- **LandingPage.tsx**: 移除操作入口，保留营销内容，增加 CTA
- **analysisClient.ts**: 新增 `getActiveCaptureTake()` 方法
- **后端**: 新增 `GET /api/capture-takes/active` 端点及测试
