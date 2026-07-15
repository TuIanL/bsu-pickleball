## 1. 基线与导航类型

- [x] 1.1 运行 `npm run test` 和 `npm run build`，记录当前基线
- [x] 1.2 新增 `src/app/navigationTypes.ts`
- [x] 1.3 将 `AppPath`、`ReportType`、`RouteState` 和 `NavigateFn` 迁入 `navigationTypes.ts`
- [x] 1.4 从 `src/types/report.ts` re-export `AppPath` 和 `ReportType`，保持旧导入兼容
- [x] 1.5 更新 `App.tsx` 中导航类型 import，确认不改变页面行为

## 2. 路由行为保护测试

- [x] 2.1 新增 `src/app/router.ts`，原样迁入当前 `parsePath(pathname)` 和 `supportedReportTypes`
- [x] 2.2 新增 `src/app/router.test.ts`，用表驱动测试覆盖 `/`、`/upload`、`/tasks`、`/capture`、`/capture/new`、`/capture/:id`
- [x] 2.3 为 `/capture/:fieldSessionId/takes/:takeId/segments` 增加 route parser 测试
- [x] 2.4 为 `/analysis/:jobId`、`/analysis/:jobId/details`、`/analysis/:jobId/vision`、`/analysis/:jobId/reports/movement` 增加 route parser 测试
- [x] 2.5 为 unsupported report fallback 和 unknown route fallback 增加测试
- [x] 2.6 运行 `npm run test -- src/app/router.test.ts`，确认原样提取后的路由测试通过

## 3. pathname/search 解析修复

- [x] 3.1 在 `src/app/router.ts` 中新增 `parseLocation(pathname, search)`，内部显式处理 query string
- [x] 3.2 为 `/upload?videoId=video-1&source=recording` 初始加载场景增加测试
- [x] 3.3 为内部 navigate 传入 `/upload?videoId=video-1&source=recording` 增加解析一致性测试
- [x] 3.4 更新 `App.tsx` 初始化逻辑，从 `parsePath(window.location.pathname)` 改为 `parseLocation(window.location.pathname, window.location.search)`
- [x] 3.5 更新 `popstate` handler，使用当前 `window.location.pathname` 和 `window.location.search`
- [x] 3.6 更新内部 `navigate()`，对传入 path 统一构造 URL 后调用 `parseLocation(url.pathname, url.search)`
- [x] 3.7 运行路由测试，确认 pathname/search 行为修复单独通过

## 4. App.tsx 页面依赖盘点

- [x] 4.1 盘点 `App.tsx` 内仍定义的页面组件：任务列表、上传/新建分析、分析状态、分析详情、视觉分析、报表、CameraHub、Training、Hardware 等
- [x] 4.2 盘点页面共享 helper：`PageFrame`、`errorToNotice`、`toneStyles`、日期/时长格式化函数等
- [x] 4.3 盘点上传/标定页面 helper：`calibrationPointOrder`、`isProbablyBlankFrame`、标定草稿类型等
- [x] 4.4 为每个待迁出页面记录闭包依赖，确认迁出后不需要从 `App.tsx` 反向导入 helper

## 5. 页面与 helper 迁出

- [x] 5.1 迁出低耦合共享 UI/helper 到合适的 `src/components/`、`src/utils/` 或页面本地模块
- [x] 5.2 迁出任务列表页面及其私有子组件到 `src/pages/AnalysisTasksPage.tsx`
- [x] 5.3 迁出上传/新建分析页面及标定 helper 到 `src/pages/NewAnalysisPage.tsx`
- [x] 5.4 迁出分析状态页、分析详情页、视觉分析页和报表页到 `src/pages/`
- [x] 5.5 迁出 CameraHub、Training、Hardware 等剩余页面实现
- [x] 5.6 每迁出一个页面或强相关页面组后运行 `npm run build`
- [x] 5.7 确认迁出后的页面不从 `src/App.tsx` 导入 helper、类型或组件

## 6. AppRouter 与 App 入口收缩

- [x] 6.1 新增 `src/app/AppRouter.tsx`
- [x] 6.2 将 route switch 迁入 `AppRouter`，props 定义为 `route`、`onNavigate`、`recentJob`
- [x] 6.3 更新 `src/App.tsx`，让它只负责 route state、recent job 监听、navigate、`AppShell` 和 `AppRouter`
- [x] 6.4 确认 `AppRouter.tsx` 不从 `src/App.tsx` 导入任何页面、helper 或组件（临时从 App.tsx 导入未迁出页面，待 5.2-5.4 完成后移除）
- [x] 6.5 确认 `AppShell activePath` 仍使用 RouteState 的 `path`，导航高亮行为不变

## 7. 范围保护

- [x] 7.1 确认本 change 不拆分 `src/services/analysisClient.ts`
- [x] 7.2 确认本 change 不拆分 `src/types/report.ts` 中除导航相关类型外的领域类型
- [x] 7.3 确认本 change 不修改 `CaptureConsolePage.tsx` 的 live coding handlers、effects、outbox 或状态机逻辑
- [x] 7.4 将 API/type 拆分记录为后续独立 change，不在当前任务中实现

## 8. 验证

- [x] 8.1 运行 `npm run test`
- [x] 8.2 运行 `npm run build`
- [x] 8.3 手动检查关键路由仍可由 parser 解析：`/`、`/upload`、`/tasks`、`/capture`、`/capture/new`、`/capture/:id`、`/analysis/:jobId`
- [x] 8.4 检查 `src/App.tsx` 行数和职责已明显收缩，不再作为多个大型页面实现的主文件
- [x] 8.5 检查 `src/services/analysisClient.ts` 和 `src/types/report.ts` 没有被本 change 大规模改写
