# frontend-architecture-boundaries

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

#### Scenario: AppPath 不得重复定义
- **WHEN** 开发者查看 `src/types/report.ts` 中的 `AppPath`
- **THEN** 该符号 MUST NOT 为独立定义的联合类型
- **AND** `src/types/report.ts` SHALL 仅从 `src/app/navigationTypes.ts` 再导出 `AppPath`
- **AND** 两个模块中的 `AppPath` SHALL 表示完全相同的路径集合（含 `/workspace`）

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

### Requirement: 路由元数据必须保留判别联合精确字面量
前端 SHALL 在 `src/app/router.ts` 中以精确字面量定义路由元数据，避免 `shellMode` / `navigationSection` 退化为联合类型而破坏 `RouteState` 判别联合。

#### Scenario: routeMeta 字面量不被拓宽
- **WHEN** 开发者查看 `src/app/router.ts` 的 `routeMeta` 表
- **THEN** 每个路由的 `shellMode` SHALL 为 `"landing" | "standard" | "capture"` 中的单一精确字面量
- **AND** 每个路由的 `navigationSection` SHALL 为 `NavigationSection | null` 中的单一精确字面量
- **AND** `parsePath` 的返回值 SHALL 可精确赋值给对应 `RouteState` 分支而不触发字面量不兼容错误

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
