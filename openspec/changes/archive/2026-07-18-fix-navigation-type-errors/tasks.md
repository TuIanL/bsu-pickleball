## 1. 收敛 AppPath 为单一来源（根因 B）

- [x] 在 `src/app/navigationTypes.ts` 确认 `AppPath`、`ReportType`、`NavigateFn`、`RouteState` 为唯一权威定义（已含 `/workspace`）。
- [x] 修改 `src/types/report.ts`：删除独立的 `AppPath` 定义（line 56-74），改为 `export type { AppPath, NavigateFn, RouteState } from "../app/navigationTypes";`（若 `ReportType` 两边一致则一并 re-export，否则保留 report.ts 自有 `ReportType`）。
- [x] `grep` 全仓 `from "./types/report"` / `from "../types/report"` 的 `AppPath` 导入，确认 re-export 后仍编译通过，无文件依赖两份定义的差异。
- [x] 验证 `npx tsc -b` 中 `App.tsx:228` 的 `NavigateFn` 不匹配错误消失。

## 2. 修复 router.ts 字面量退化（根因 A）

- [x] 修改 `src/app/router.ts:1` 导入 `AppShellMode`、`NavigationSection`（若尚未导入）。
- [x] 将 `RouteMeta`（line 5-8）字段类型改为 `AppShellMode` 与 `NavigationSection | null`，不再使用 `RouteState["shellMode"]` 联合取法。
- [x] 给 `routeMeta` 表（line 10-29）加 `as const satisfies Record<string, RouteMeta>`，保留各路由字面量。
- [x] 确认 `parsePath` 18 条分支逻辑与返回值不变，仅类型精确化。
- [x] 验证 `npx tsc -b` 中 `router.ts` 的 32 个错误全部消失。

## 3. 清理 App.tsx 未使用导入（噪音消除）

- [x] 删除 `src/App.tsx` 中未被 `App()` 使用的导入：lucide 图标（line 2-27）、`useMemo`/`useRef`/`MouseEvent`/`ReactNode`（line 29）、`pages/*`（line 30-37，除被 AppRouter 间接使用外的直接导入）、`components/platform/*`（line 38-48）、`data/demoData`、`services/analysisClient`、`services/analysisDiagnostics`、`services/courtProjectionTracks`、`services/pipelineReportAdapter`、`services/timelineQuickEvents`、`types/report` 全部类型。
- [x] 仅保留 `AppShell`、`AppRouter`、`parseLocation`、本地 `navigate`/`useState`/`useEffect`/`useCallback`、`NavigateFn`、`RouteState`（及 `ReportType` 若仍需）。
- [x] 验证 `npx eslint .` 的 `no-unused-vars` 量级从约 290 降至接近 0，且 `App.tsx` 渲染行为不变。

## 4. 验证与收口

- [x] 运行 `npm run build`（`tsc -b && vite build`），确认零错误产出 `dist/`。
- [x] 运行现有 `router.ts` 相关表驱动测试，确认路由解析行为不变。
- [x] 在 `openspec/specs/frontend-architecture-boundaries/spec.md` 追加场景："`AppPath` MUST NOT 在 `types/report.ts` 独立重复定义，仅可从 `navigationTypes.ts` 再导出"；"`router.ts` 的 `RouteMeta` MUST 保留判别联合精确字面量，不得退化为联合类型"。
