## Why

`npm run build`（即 `tsc -b`）当前失败，共 33 个 TypeScript 编译错误，全部集中在导航类型层：

- `src/app/router.ts` 32 处：`RouteState` 是判别联合类型，要求 `shellMode` / `navigationSection` 为精确字面量；但 `router.ts` 用 `RouteMeta` 把字段类型取成 `RouteState["shellMode"]`（联合 `"landing"|"standard"|"capture"`），摊回对象后字面量退化，每条路由都触发 "Type 'capture' is not assignable to type 'landing'" 一类报错。
- `src/App.tsx:228` 1 处：`navigate` 的参数类型来自 `src/types/report.ts` 的 `AppPath`（**不含** `/workspace`），而 `NavigateFn` / `AppShell` 期望的是 `src/app/navigationTypes.ts` 的 `AppPath`（**含** `/workspace`）。两个 `AppPath` 重复定义且已不一致，`navigate` 因函数参数逆变无法赋给 `NavigateFn`。

`vite dev` 仍可运行（不做类型检查），但 `build` 已阻断，CI 与产物无法产出。同时 `App.tsx` 存在约 290 个 `no-unused-vars` 噪音（导入了约 90 个未被使用的符号），掩盖了真实问题。

`openspec/specs/frontend-architecture-boundaries/spec.md` 已规定"导航类型必须从 App 实现中分离"，并且 `AppPath` 的权威定义位于 `src/app/navigationTypes.ts`，`src/types/report.ts` 的 `AppPath` 仅为兼容遗留导入而存在。本次问题正是该契约被重复定义破坏所致。

## What Changes

- 收敛 `AppPath` 为单一权威来源：`src/app/navigationTypes.ts` 保留完整定义（含 `/workspace`）；`src/types/report.ts` 改为从该模块**再导出**（re-export），不再维护独立副本，消除两份定义漂移。
- 修正 `router.ts` 的 `RouteMeta` 类型标注，使其字段保留判别联合所需的精确字面量（用 `as const` 或收窄为 `AppShellMode` / `NavigationSection | null`），不再把字面量提升为联合。
- 清理 `src/App.tsx` 中约 90 个未被使用的导入（图标、页面、组件、services、mock 数据与类型），仅保留 `AppShell` / `AppRouter` / `parseLocation` / `navigate` 实际依赖的符号，消除 `no-unused-vars` 噪音。
- 不改变任何运行时行为：`parsePath` / `parseLocation` 的 18 条路由分支逻辑、`navigate` 的 `history.pushState` 行为、页面渲染入口均保持不变。

## Capabilities

### Modified Capabilities

- `frontend-architecture-boundaries`: 强化"导航类型单一来源"与"RouteState 判别联合字面量不被退化"的契约要求，补充 `AppPath` 不能重复定义、`router.ts` 的 `RouteMeta` 必须保留精确字面量的场景。

## Impact

- 仅影响前端导航类型层与 `App.tsx` 导入：
  - `src/app/navigationTypes.ts`（确认 `AppPath` 为唯一权威定义）
  - `src/types/report.ts`（改为 re-export `AppPath` / `ReportType`，删除独立副本）
  - `src/app/router.ts`（`RouteMeta` 类型标注）
  - `src/App.tsx`（删除未使用导入）
- 不改动路由解析逻辑、页面组件、后端接口、录制/分析流程。
- 修复后 `npm run build`（`tsc -b && vite build`）应零错误通过；ESLint `no-unused-vars` 噪音量级从约 290 降至接近 0（仅保留真实问题）。
