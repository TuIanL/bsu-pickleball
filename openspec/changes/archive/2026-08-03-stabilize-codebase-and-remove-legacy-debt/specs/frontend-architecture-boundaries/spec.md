## MODIFIED Requirements

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
