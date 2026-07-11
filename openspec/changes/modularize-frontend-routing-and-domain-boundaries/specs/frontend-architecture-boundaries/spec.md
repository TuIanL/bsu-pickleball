## ADDED Requirements

### Requirement: 导航类型必须从 App 实现中分离
前端 SHALL 将应用导航相关类型定义为独立类型契约，使路由解析、AppRouter、AppShell 和页面 props 可以共享同一组稳定类型。

#### Scenario: 导航类型模块存在
- **WHEN** 开发者查看 `src/app/navigationTypes.ts`
- **THEN** 该模块 SHALL 导出 `AppPath`、`NavigateFn`、`ReportType` 和 `RouteState`
- **AND** 该模块 MUST NOT 导入 React 页面组件或浏览器运行时对象

#### Scenario: 旧类型导入保持兼容
- **WHEN** 现有代码仍从 `src/types/report.ts` 导入 `AppPath` 或 `ReportType`
- **THEN** TypeScript 编译 SHALL 继续通过
- **AND** 旧导出名称 SHALL 保持可用

### Requirement: 路由解析必须可测试且行为稳定
前端 SHALL 将路由解析定义为不依赖 React state、DOM 或浏览器全局对象的纯函数，并用表驱动测试覆盖当前支持的主要路由。

#### Scenario: 解析核心产品路由
- **WHEN** 测试调用路由解析函数并传入 `/`、`/upload`、`/tasks`、`/capture`、`/capture/new`、`/capture/fs-1`
- **THEN** 系统 SHALL 返回与当前页面渲染入口一致的 RouteState

#### Scenario: 解析采集分段管理路由
- **WHEN** 测试调用路由解析函数并传入 `/capture/fs-1/takes/take-1/segments`
- **THEN** 系统 SHALL 返回 segment manager RouteState
- **AND** RouteState SHALL 包含 `fieldSessionId = "fs-1"` 和 `takeId = "take-1"`

#### Scenario: 解析分析任务路由
- **WHEN** 测试调用路由解析函数并传入 `/analysis/job-1`、`/analysis/job-1/details`、`/analysis/job-1/vision`、`/analysis/job-1/reports/movement`
- **THEN** 系统 SHALL 返回对应的 job status、analysis details、visual analysis、report RouteState
- **AND** RouteState SHALL 保留 `jobId = "job-1"`

#### Scenario: unsupported report 路由降级
- **WHEN** 测试调用路由解析函数并传入 `/analysis/job-1/reports/unsupported`
- **THEN** 系统 SHALL 返回 analysis details RouteState
- **AND** 系统 MUST NOT 返回破损 report RouteState

#### Scenario: unknown route 降级
- **WHEN** 测试调用路由解析函数并传入未知路径
- **THEN** 系统 SHALL 返回 landing RouteState

### Requirement: 路由解析必须显式处理 pathname 和 search
前端 SHALL 使用同时接收 `pathname` 和 `search` 的解析入口处理浏览器初始加载、前进后退和内部导航，避免 query string 在刷新时丢失。

#### Scenario: 刷新 upload query 路由
- **WHEN** 浏览器在 `/upload?videoId=video-1&source=recording` 初始加载
- **THEN** 路由解析 SHALL 使用 `pathname = "/upload"` 和 `search = "?videoId=video-1&source=recording"` 生成 upload RouteState
- **AND** RouteState SHALL 包含 `videoId = "video-1"` 和 `source = "recording"`

#### Scenario: popstate 保留 query 解析
- **WHEN** 用户通过浏览器前进或后退回到带 query string 的 upload 路由
- **THEN** popstate handler SHALL 使用当前 `window.location.pathname` 和 `window.location.search` 更新 RouteState

#### Scenario: 内部导航统一解析 query
- **WHEN** 应用内部调用 navigate 并传入 `/upload?videoId=video-1&source=recording`
- **THEN** navigate SHALL 通过 pathname 和 search 解析 RouteState
- **AND** RouteState SHALL 与刷新同一路径时一致

### Requirement: 页面迁出必须避免 App 循环依赖
前端 SHALL 在创建 AppRouter 前迁出被 AppRouter 引用的页面实现和页面依赖，避免 `AppRouter.tsx` 与 `App.tsx` 互相导入。

#### Scenario: 迁出页面前识别闭包依赖
- **WHEN** 开发者准备从 `App.tsx` 迁出某个页面组件
- **THEN** 该页面依赖的 helper、子组件、类型和 API SHALL 被识别并随页面迁移到合适模块
- **AND** 迁出后的页面 MUST NOT 反向从 `App.tsx` 导入 helper

#### Scenario: AppRouter 不导入 App
- **WHEN** 开发者查看 `src/app/AppRouter.tsx`
- **THEN** 该模块 SHALL NOT 从 `src/App.tsx` 导入页面、helper 或组件

#### Scenario: App 不再承载多个大型页面实现
- **WHEN** 开发者查看 `src/App.tsx`
- **THEN** 文件 SHALL 主要负责 route state、recent job 监听、navigate、`AppShell` 和 `AppRouter`
- **AND** 文件 MUST NOT 继续作为多个大型页面组件的主要实现位置

### Requirement: AppRouter 必须保持页面分发行为不变
前端 SHALL 使用 AppRouter 根据 RouteState 渲染页面，并保持现有路由到页面的映射和 props 传递行为。

#### Scenario: AppRouter 渲染采集页面
- **WHEN** AppRouter 接收 capture home、capture new、capture console 或 segment manager RouteState
- **THEN** AppRouter SHALL 渲染对应采集页面
- **AND** AppRouter SHALL 传递 `onNavigate`、`sessionId`、`fieldSessionId` 或 `takeId` 等现有必需 props

#### Scenario: AppRouter 渲染分析页面
- **WHEN** AppRouter 接收 analysis job、analysis details、vision 或 report RouteState
- **THEN** AppRouter SHALL 渲染对应分析页面
- **AND** AppRouter SHALL 保留 `jobId`、`reportType`、`recentJob` 和 `onNavigate` 等现有 props

#### Scenario: AppShell active path 保持稳定
- **WHEN** App 使用 AppShell 渲染当前页面
- **THEN** AppShell 的 `activePath` SHALL 继续来自当前 RouteState 的 `path`
- **AND** 导航高亮行为 SHALL 与迁移前保持一致

### Requirement: 模块化迁移必须通过现有安全门验证
前端模块化迁移 SHALL 使用现有测试和构建命令验证行为保护与类型兼容。

#### Scenario: 路由测试运行
- **WHEN** 开发者运行前端测试命令
- **THEN** 路由解析表驱动测试 SHALL 执行并通过

#### Scenario: 构建兼容检查运行
- **WHEN** 开发者运行 `npm run build`
- **THEN** TypeScript project build 和 Vite build SHALL 通过
- **AND** 构建 MUST NOT 因页面迁出、导航类型迁出或路由模块拆分失败
