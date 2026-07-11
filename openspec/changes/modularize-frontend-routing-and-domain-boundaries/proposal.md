## Why

当前前端核心代码存在明显的文件膨胀和边界混杂：`src/App.tsx` 同时承载路由解析、App shell、多个页面实现和工具函数。随着采集、分析可视化和 live coding 继续迭代，这个入口文件会持续放大维护成本，也会让后续重构难以判断是“搬迁导致的问题”还是“行为修改导致的问题”。

本 change 收缩为第一阶段低风险前端架构小改：只拆 `App.tsx` 的路由解析、导航类型、AppRouter 和页面模块边界，并通过路由测试和构建检查保证现有行为不变。`analysisClient.ts` 和 `report.ts` 的领域拆分推迟到后续独立 change，避免和正在进行的 `fix-live-coding-pipeline` 同时修改 live coding API/type 区域。

## What Changes

- 提取 App 导航类型和路由解析为可测试模块：`navigationTypes.ts` 定义类型契约，`router.ts` 定义解析行为。
- 原样迁移当前 `parsePath(pathname)` 并用表驱动测试锁定现状。
- 单独添加 `parseLocation(pathname, search)`，修复刷新带 query string 的 `/upload` 路由时参数丢失的问题。
- 将 App router / shell 与页面实现逐步分离，减少 `src/App.tsx` 的职责，使其主要负责应用装配。
- 先盘点 `App.tsx` 中页面及其闭包依赖，再逐个迁出页面和页面私有 helper，避免 `AppRouter.tsx` 与 `App.tsx` 形成循环依赖。
- 保持 `src/services/analysisClient.ts` 和 `src/types/report.ts` 现状，不在本 change 中拆分 API 或领域类型。
- 使用 `npm run test` 和 `npm run build` 作为安全门，确保路由行为、页面迁出后的 import 和导航类型兼容继续成立。
- 不修改后端 API 路由、不改变用户可见路由、不改变页面布局、不引入 React Router 或新的运行时依赖。

## Capabilities

### New Capabilities

- `frontend-architecture-boundaries`: 定义前端导航类型、路由解析、AppRouter 和页面模块边界要求，确保 `App.tsx` 模块化迁移期间用户可见路由行为保持稳定。

### Modified Capabilities

无。本 change 不改变现有产品行为规格；现有 `layered-product-navigation`、`video-analysis-job-flow`、`capture-workflow` 等能力的路由和页面行为必须保持兼容。

## Impact

| 影响范围 | 内容 |
|---------|------|
| `src/App.tsx` | 提取 route state、route parser、App router/page wiring，逐步瘦身 |
| `src/app/**` | 新增导航类型、路由解析、AppRouter 等应用层模块 |
| `src/pages/**` | 承接从 `App.tsx` 迁出的页面实现和页面私有 helper |
| `src/components/**` | 承接从 `App.tsx` 迁出的可复用页面子组件 |
| `src/**/*.test.ts` | 新增路由解析表驱动测试 |
| `src/services/analysisClient.ts` | 本 change 不拆分，仅作为页面迁移时的现有依赖保留 |
| `src/types/report.ts` | 本 change 仅允许迁出导航类型；其他领域类型拆分推迟到后续 change |
| 构建与依赖 | 不新增运行时依赖；使用现有 `vitest` 和 `npm run build` 验证 |
