# Design: 导航类型编译错误收口

## 背景与根因

两类红色错误，根因都在"导航类型契约被重复/退化定义"：

### 根因 A — `router.ts` 字面量退化

`navigationTypes.ts` 中 `RouteState` 是判别联合，每个分支的 `shellMode` / `navigationSection` 是**精确字面量**：

```ts
type RouteState =
  | { name: "landing";       shellMode: "landing";  navigationSection: null }
  | { name: "workspace";     shellMode: "standard"; navigationSection: "capture" }
  | { name: "captureConsole"; shellMode: "capture";  navigationSection: "capture" }
  ...
```

`router.ts` 当前的 `RouteMeta`：

```ts
type RouteMeta = {
  shellMode: RouteState["shellMode"];          // 取成联合 "landing"|"standard"|"capture"
  navigationSection: RouteState["navigationSection"];
};
```

`RouteState["shellMode"]` 是**整个联合**，摊进 `{ ...routeMeta.landing }` 后，`shellMode` 类型退化为联合，无法窄化回 `"landing"`，于是每条 `return {...routeMeta.x}` 都报 "Type 'capture' is not assignable to type 'landing'"。18 条路由 × 多处 = 32 个错误。

### 根因 B — `AppPath` 双定义漂移

| 文件 | `AppPath` 内容 |
|------|---------------|
| `src/app/navigationTypes.ts:13` | 含 `/workspace` |
| `src/types/report.ts:56` | **不含** `/workspace` |

`App.tsx` 从 `./types/report` 取 `AppPath` 用于 `navigate`（line 199），但 `AppShell` / `AppRouter` / `NavigateFn` 期望 `navigationTypes.AppPath`。函数参数逆变下，`navigate` 接受的路径集合比 `NavigateFn` 要求的更窄（缺 `/workspace`），导致 `App.tsx:228` 的 "Type '/workspace' is not assignable" 报错。

`frontend-architecture-boundaries/spec.md` 已声明 `navigationTypes.ts` 为权威来源，`types/report.ts` 仅为兼容遗留导入保留，不应独立维护副本。

## 方案

### 修复 A：`RouteMeta` 保留精确字面量

将 `router.ts:5-8` 改为收窄类型，并用 `as const` 让 `routeMeta` 表对象的字面量不被拓宽：

```ts
import type { AppShellMode, NavigationSection, RouteState } from "./navigationTypes";

type RouteMeta = {
  shellMode: AppShellMode;
  navigationSection: NavigationSection | null;
};

const routeMeta = {
  landing: { shellMode: "landing", navigationSection: null },
  ...
} as const satisfies Record<string, RouteMeta>;
```

`as const` 使 `routeMeta.landing.shellMode` 保持 `"landing"` 字面量，`parsePath` 返回值即可精确匹配 `RouteState` 各分支。逻辑（18 条分支）一行不改。

### 修复 B：收敛 `AppPath` 单一来源

`src/types/report.ts` 删除独立 `AppPath` 定义（line 56-74），改为：

```ts
export type { AppPath, NavigateFn, ReportType, RouteState } from "../app/navigationTypes";
```

`navigationTypes.ts` 的 `AppPath` 已是含 `/workspace` 的权威定义。这样：
- `App.tsx` 从 `./types/report` 取到的 `AppPath` 与 `NavigateFn` 期望的完全一致，根因 B 消除。
- 遗留 `import { AppPath } from "./types/report"` 仍编译通过（满足 spec 的兼容要求）。

> 注意：`report.ts` 原本也导出 `ReportType`，而 `navigationTypes.ts` 也导出 `ReportType`。统一 re-export 时需确认两边 `ReportType` 语义一致（均为 `"movement" | "diagnosis"`），否则保留 `report.ts` 自有 `ReportType`，仅 re-export `AppPath`。

### 清理 C：`App.tsx` 未使用导入

删除以下未使用导入组（经 ESLint `no-unused-vars` 确认约 90 个符号从未被 `App()` 使用）：
- `lucide-react` 的全部图标（line 2-27）
- React 钩子 `useMemo / useRef` 与类型 `MouseEvent / ReactNode`（line 29 部分）
- `./pages/*`、`components/platform/*`、`data/demoData`、`services/analysisClient` 全部、`services/analysisDiagnostics`、`services/courtProjectionTracks`、`services/pipelineReportAdapter`、`services/timelineQuickEvents`、`types/report` 全部类型
- 保留：`AppShell`、`AppRouter`、`parseLocation`、本地 `navigate` / hooks、`NavigateFn`、`RouteState`、`ReportType`（若仍需）

清理纯属消除噪音，不改行为。

## 风险与权衡

- **`as const satisfies`**：`routeMeta` 字段值必须是合法 `AppShellMode` / `NavigationSection`，若某路由写错字面量，`satisfies` 会立即报错——这是期望的强约束。
- **re-export 兼容性**：`report.ts` 被大量文件 import，改为 re-export 后类型身份与 `navigationTypes` 完全一致，比当前"各不相同"更安全。需 `grep` 确认没有文件依赖 `report.ts` 版 `AppPath` 与 `navigationTypes` 版的差异（本就不该有）。
- **不引入行为变更**：三处修改均为类型层 / 导入层，运行时代码零改动。

## 验证

- `npx tsc -b`：错误数从 33 → 0。
- `npx eslint .`：`no-unused-vars` 量级从约 290 → 接近 0。
- `npm run build`：成功产出 `dist/`。
- 现有 `router.ts` 表驱动测试（`parsePath` 各路由）仍通过。
