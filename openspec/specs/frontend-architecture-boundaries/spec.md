# frontend-architecture-boundaries

## Purpose

定义前端导航类型、路由解析、查询参数处理和页面边界的稳定契约，确保页面迁移后依赖方向清晰、导航入口兼容、路由行为可测试，并能持续验证前端架构不会重新产生循环依赖。
## Requirements
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
- **AND** 两个模块中的 `AppPath` SHALL 表示完全相同的路径集合（含 `/workspace` 和录制分析路径）

### Requirement: 路由解析必须可测试且行为稳定

前端 SHALL 将路由解析定义为不依赖 React state、DOM 或浏览器全局对象的纯函数，并用表驱动测试覆盖当前支持的主要路由，包括规范分析任务入口和录制到分析入口。

#### Scenario: 解析核心产品路由

- **WHEN** 测试调用路由解析函数并传入 `/`、`/upload`、`/tasks`、`/capture`、`/capture/new`、`/capture/fs-1`
- **THEN** 系统 SHALL 返回与当前页面渲染入口一致的 `RouteState`

#### Scenario: 解析规范分析任务路由

- **WHEN** 测试调用路由解析函数并传入 `/analysis/tasks`
- **THEN** 系统 SHALL 返回分析任务列表的 `RouteState`
- **AND** 该状态 SHALL 与 `/tasks` 兼容别名指向同一个页面入口

#### Scenario: 解析录制分析路由

- **WHEN** 测试调用路由解析函数并传入 `/capture/fs-1/analyze`
- **THEN** 系统 SHALL 返回 `recording-analyze` RouteState
- **AND** RouteState SHALL 包含 `sessionId = "fs-1"`
- **AND** `shellMode` 与 `navigationSection` SHALL 与 `RouteState` 联合类型一致

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

前端 SHALL 在 `src/app/router.ts` 中以精确字面量定义路由元数据，且所有已支持路由的返回值必须可精确赋值给对应 `RouteState` 分支。

#### Scenario: routeMeta 字面量不被拓宽

- **WHEN** 开发者查看 `src/app/router.ts` 的 `routeMeta` 表
- **THEN** 每个路由的 `shellMode` SHALL 为单一精确字面量
- **AND** 每个路由的 `navigationSection` SHALL 为单一精确字面量
- **AND** `parsePath` 的返回值 SHALL 可通过 TypeScript 严格编译

#### Scenario: 录制分析路由元数据一致

- **WHEN** `parsePath` 解析 `/capture/fs-1/analyze`
- **THEN** 返回对象的 `shellMode` 和 `navigationSection` SHALL 与 `recording-analyze` 分支声明完全一致
- **AND** 不得通过 `as any` 或强制类型断言绕过错误

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

#### Scenario: AppRouter 与页面模块保持单向依赖

- **WHEN** 构建前端应用并检查 `AppRouter.tsx`、`App.tsx` 与页面模块的导入关系
- **THEN** TypeScript 构建 SHALL 成功
- **AND** `AppRouter.tsx` SHALL 不得反向导入 `App.tsx`

### Requirement: Library 与 Workspace 路由契约
前端 Pathname/Search 解析 SHALL 保持纯函数、可测试，并新增对 Library 与 Workspace 路由的无歧义解析。

#### Scenario: Library 路由解析
- **WHEN** pathname 为 `/library/recording/r-1?view=analysis`
- **THEN** 解析器 SHALL 生成 `{ name: "library-item", kind: "recording", sourceId: "r-1", view: "analysis" }` 单一 RouteState
- **AND** 该解析 SHALL 与顺序敏感的兄弟 states（analysis-job / vision / report 等）无歧义
- **AND** 非法 kind / sourceId / view SHALL 安全回退，不抛解析异常

#### Scenario: Workspace view query 契约
- **WHEN** `view` 处于受支持枚举（overview / video / analysis / trajectory / report / segments / technical）
- **THEN** 系统 SHALL 渲染对应 View
- **WHEN** `view` 缺失或不支持
- **THEN** 系统 SHALL 回退到 `overview`

#### Scenario: 可刷新深链
- **WHEN** 用户直接打开某 LibraryItem 某 view 的完整 URL
- **THEN** 系统 SHALL 恢复到对应素材与 view，无需额外前置状态

### Requirement: view 历史语义契约
系统 SHALL 对 Workspace 内一级 view 切换使用 replace 历史语义（复用 `NavigateOptions.replace`），对 Library→Workspace 及 Workspace→外部对象跳转使用 push 语义。

#### Scenario: 层级跳转入栈
- **WHEN** 用户从 `/library` 进入某比赛
- **THEN** 系统 SHALL 新增历史项（push）

#### Scenario: view 切换不污染历史
- **WHEN** 用户在同一素材下切换 `?view`（含 `?view=video&t=...` 证据跳转）
- **THEN** 系统 SHALL 使用 replace 语义，不新增历史项

#### Scenario: 返回行为
- **WHEN** 用户在 `?view=analysis` 按一次浏览器 Back
- **THEN** 系统 SHALL 回到 `/library`，而非逐个 view 回退

#### Scenario: Legacy route 保留 sibling RouteState
- **WHEN** 用户访问旧 route `/analysis/job-123/vision`（不含 sourceType/sourceId）
- **THEN** 迁移期系统 SHALL 先以旧 sibling RouteState 直渲
- **AND** 由 `LegacyLibraryRouteResolver` 异步加载 job → `resolveLibraryItemRef(job)` → replace 到 `/library/...`

### Requirement: view capability gate 与 stable fallback

系统 SHALL 依据素材 availability/analysisState 门控 workspace 各 view，并在无可用结果时提供 stable fallback，不允许空白页。

#### Scenario: 无成功分析时深链结果 view
- **WHEN** 用户深链至 `?view=report`（或 trajectory/multiview）而素材无成功的 primary analysis
- **THEN** 系统 SHALL 落到 stable fallback（如 `overview` + 待分析提示）
- **AND** SHALL NOT 渲染空白页

### Requirement: 上传/采集默认落点

Library-first 后，上传与现场采集的完成落点 SHALL 指向对应 LibraryItem，而非回到任务列表。

#### Scenario: 上传创建分析后进入比赛详情
- **WHEN** 用户完成上传 + 四角标定 + 创建分析
- **THEN** 系统 SHALL 进入 `/library/upload/{videoId}?view=analysis`
- **AND** 直接展示该素材「正在分析」状态，而非导航回 `AnalysisTasksPage`

#### Scenario: 采集 durable 后进入库卡片
- **WHEN** 现场采集完成后素材 durable 化
- **THEN** 该素材 SHALL 以对应 LibraryItem 呈现在比赛库中

