## Context

当前前端最大的维护热点是 `src/App.tsx`：它约 5381 行，同时包含路由解析、App shell、任务列表、上传分析、报表页面、页面私有 helper 和若干 UI 子组件。`src/services/analysisClient.ts` 与 `src/types/report.ts` 也偏大，但其中包含正在进行的 live coding 修复会触碰的 API/type 区域；如果本 change 同时拆 API 和类型，容易和 `fix-live-coding-pipeline` 形成冲突。

因此本 change 收缩为第一阶段：只处理 `App.tsx` 的路由与页面模块边界。API client 和领域类型拆分作为后续独立 change 处理。

## Goals / Non-Goals

**Goals:**

- 建立清晰的应用层边界：`navigationTypes.ts` 定义类型契约，`router.ts` 定义解析行为，`AppRouter.tsx` 定义 JSX 分发。
- 将路由解析从 `App.tsx` 中提取为可测试纯函数。
- 用表驱动测试保护当前主要路由，包括旧路由兼容和 unsupported report fallback。
- 单独修复 `pathname`/`search` 分离导致的 `/upload?videoId=...` 刷新参数丢失问题。
- 逐个迁出 `App.tsx` 中的大型页面实现和页面私有 helper，使 `App.tsx` 收缩为应用入口。
- 保持用户可见路由、页面布局、导航入口和业务流程不变。

**Non-Goals:**

- 不拆分 `src/services/analysisClient.ts`。
- 不拆分 `src/types/report.ts` 中除导航相关类型之外的领域类型。
- 不重构 `CaptureConsolePage` 的 hooks、副作用状态机、handlers 或 live coding outbox 流程。
- 不引入 React Router 或新的路由运行时依赖。
- 不修改后端 API URL、请求/响应 schema 或数据库模型。
- 不重构 `analysis_pipeline.py` 或后端视觉 pipeline。

## Decisions

### 1. 类型契约、解析行为、JSX 分发三层分离

**决策**：使用如下边界：

```text
src/app/navigationTypes.ts
├── AppPath
├── NavigateFn
├── ReportType
└── RouteState

src/app/router.ts
├── supportedReportTypes
├── parsePath
└── parseLocation

src/app/AppRouter.tsx
└── 根据 RouteState 渲染页面
```

**原因**：这样可以避免 `router.ts` 同时成为类型中心和行为中心，也能让页面组件只依赖稳定的导航类型。

**替代方案**：把所有导航类型和 parser 都放在 `router.ts`。暂不采用，因为后续 AppRouter、AppShell、页面 props 都会引用导航类型，类型文件独立更清楚。

### 2. 先原样提取 `parsePath`，再修复 `parseLocation`

**决策**：路由提取分两步：

1. 原样移动当前 `parsePath(pathname)` 行为，并用测试记录现状。
2. 单独新增 `parseLocation(pathname, search)`，让初始加载、内部导航和 `popstate` 都正确处理 query string。

**原因**：当前代码初始化时使用 `parsePath(window.location.pathname)`，但 `parsePath()` 内部又试图处理 `/upload?videoId=...`。刷新带 query 的 `/upload` 时，query string 实际不会进入 parser。这个问题值得修，但必须和文件移动分开，避免回归时难以定位。

### 3. 先迁出页面依赖，再创建 `AppRouter`

**决策**：不要先创建 `AppRouter.tsx` 并让它从 `App.tsx` 导入页面。正确顺序是：

```text
盘点 App.tsx 页面及闭包依赖
→ 迁出共享 helper 和页面私有 helper
→ 逐个迁出页面实现
→ 创建 AppRouter
→ App.tsx 改为应用壳
```

**原因**：如果 `AppRouter.tsx` 先导入仍定义在 `App.tsx` 中的页面，而 `App.tsx` 又导入 `AppRouter`，会形成循环依赖。`App.tsx` 中的 `PageFrame`、`calibrationPointOrder`、`isProbablyBlankFrame`、`errorToNotice`、`toneStyles` 等 helper 也必须跟随页面依赖拆出。

### 4. 页面迁移按“闭包依赖”分批

**决策**：迁移每个页面前先列出它依赖的 helper、子组件、类型和 API。迁出后的页面禁止反向从 `App.tsx` 导入 helper。

**原因**：页面函数在 `App.tsx` 中天然共享文件作用域变量。直接剪切页面函数容易遗漏隐式依赖，或者制造反向 import。

建议顺序：

```text
1. 迁出低耦合页面或组件
2. 迁出任务列表相关页面与子组件
3. 迁出上传/新建分析页面及标定 helper
4. 迁出报表/视觉相关页面
5. 最后创建 AppRouter 并瘦身 App.tsx
```

实际实施时可根据依赖盘点微调。

### 5. API/type 拆分推迟到后续 change

**决策**：本 change 不拆 `analysisClient.ts` 和 `report.ts` 的领域 API/type。只允许将 `AppPath`、`NavigateFn`、`ReportType`、`RouteState` 等导航相关类型迁入 `src/app/navigationTypes.ts`，并由 `report.ts` 继续 re-export 必要兼容类型。

**原因**：`analysisClient.ts` 不只是 HTTP API，还包含 LocalStorage demo repository 和 recent job store/event；`captureApi` 也可能继续变大，需要更细的 API 设计。更关键的是，live coding change 可能正在修改 CodingAction API 和类型。把 API/type 拆分留到下一条 change，可以降低冲突面。

后续 API/type change 可考虑：

```text
src/api/
├── httpClient.ts
└── apiError.ts

src/features/analysis/
├── analysisApi.ts
├── analysisTypes.ts
├── analysisDemoRepository.ts
└── recentAnalysisJobStore.ts

src/features/capture/api/
├── recordingApi.ts
├── syncRecordingApi.ts
├── fieldSessionApi.ts
├── captureTakeApi.ts
├── codingActionApi.ts
└── index.ts
```

### 6. 不重命名 `AnalysisApiError`

**决策**：本 change 不移动或重命名共享错误类。

**原因**：`AnalysisApiError` 虽然未来可以演进为通用 `ApiClientError`，但本阶段不拆 API client。即使后续拆分，也应先原样移动，后续再单独重命名，避免错误识别逻辑和模块迁移混在一起。

## Risks / Trade-offs

- [Risk] 当前 change 名称仍包含 `domain-boundaries`，但实施范围收缩到路由与 App 页面边界。→ Mitigation：proposal/design/tasks 明确 API/type 拆分是后续 change，当前只做第一阶段。
- [Risk] 页面迁移时遗漏文件作用域 helper。→ Mitigation：先做闭包依赖盘点，迁出页面禁止反向 import `App.tsx`。
- [Risk] 路由 parser 的 query 修复改变 `/upload?videoId=...` 刷新行为。→ Mitigation：先提交原样 parser 测试，再单独添加 `parseLocation(pathname, search)` 测试和实现。
- [Risk] 迁出页面产生大 diff。→ Mitigation：每次只迁出一个页面或强相关页面组，并运行 `npm run build`。
- [Risk] 后续仍需要拆 `analysisClient.ts` 和 `report.ts`。→ Mitigation：将其作为后续独立 change，不在当前分支拖成长尾。

## Migration Plan

1. 运行现有 `npm run test` 和 `npm run build`，记录基线。
2. 新增 `src/app/navigationTypes.ts`，迁入导航相关类型。
3. 新增 `src/app/router.ts`，原样迁入 `parsePath` 和 `supportedReportTypes`。
4. 新增 `src/app/router.test.ts`，表驱动覆盖当前路由行为。
5. 单独新增 `parseLocation(pathname, search)`，更新初始化、`popstate` 和内部 `navigate()`。
6. 盘点 `App.tsx` 中页面和 helper 的闭包依赖。
7. 逐个迁出页面实现、页面私有 helper 和可复用子组件。
8. 创建 `src/app/AppRouter.tsx`，迁入 route switch。
9. 收缩 `src/App.tsx` 为应用入口。
10. 运行 `npm run test` 和 `npm run build`。

## Open Questions

- 本 change 是否需要改名为 `extract-app-routing-and-page-modules`？当前不强制改目录名，避免制造额外 OpenSpec 迁移；但后续实施和 PR 标题可以使用更准确的短名。
- 是否在本轮迁出全部 `App.tsx` 内页面，还是只迁出到 `App.tsx` 明显收缩为止？建议任务中列出全部迁出，但实施时保持每个页面组独立提交。
