## Context

项目当前状态：
- 前端技术栈：React 18 + TypeScript + Vite + TailwindCSS + ECharts 5 + Three.js 0.160
- 报告页路由：`/report/:id` 挂载 `ReportPage.tsx`，从 `useAnalysisReport()` / demoData 读取报告数据
- 已有可视化基础：
  - `BallTrajectoryScene.tsx`：Three.js 3D 球场 + 球轨迹 + 4 视角切换（斜视/俯视/侧视/端线）+ 全屏
  - `SkillRatings.tsx` / `RadarChart.tsx`：六维能力卡片 + SVG 六轴雷达图
  - `displayHeatmap.tsx` / `StructuredZoneHeatmap.tsx`：ECharts 球场热力图
  - `PerformanceInsightsPanel.tsx`：表现洞察 + findings + recommendations
- 主题系统：`index.css` 以深绿 `#168A34` 为主色，有 `--green-*` 一系列自定义变量
- 数据来源：`types/report.ts` 定义的 `AnalysisReportResponse`（含 session / match / teams / subjects / shotRows / serve_events / movementPath / skillRatings / performanceInsights / metrics / progressPoints / findings / recommendations / trainingRecommendations / coachNotes）

约束：
- **不修改全局 AppShell 和其他页面**：抽屉栏必须是报告页局部渲染，不能侵入 `/sessions`、`/analysis` 等路由
- **不新增第三方依赖**：饼图、环形图、滑块全部用已有 ECharts / 原生 / Tailwind 实现
- **不重写 Three.js 逻辑**：球场景直接复用组件，只改外围外观
- **无历史数据时 Δ 和对比线必须静默隐藏**，但保留 DOM 占位
- **演示数据用 mock**：Serves/Returns Depth、百分位、In% 等后端尚无字段必须有合理前端 mock，且 mock 数据来源函数要独立，便于未来替换为真实 API

## Goals / Non-Goals

**Goals:**
1. 在 `/report/:id` 上完整呈现 PB Vision 风格（抽屉栏 + 亮色 + 8 大模块）
2. 所有已有的真实报告字段（shotRows、skillRatings、metrics 等）直接对接真实数据；缺失字段用独立 mock 函数填充
3. 球员切换、Filter 过滤等交互行为响应敏捷，3D 球场轨迹即时更新
4. 保证新旧布局可无缝切换（`?legacy=1`），降低回归风险
5. PB 主题严格作用域化，不泄漏到其他页面

**Non-Goals:**
1. 不接入真实球员档案/历史赛季对比（只预留 DOM 和 hook 占位）
2. 不修改首页、录制控制台、分析工作区等非报告页
3. 不重写 BallTrajectoryScene 内部 Three.js 渲染逻辑
4. 不真实跳转 Shot Explorer / 训练视频链接（href 留空占位）
5. 不做移动端精细适配（保证大尺寸展示可用即可，小屏不崩溃为最低标准）

## Decisions

### D1. 布局架构：PbVisionReportLayout 包裹 + Context 管理选中球员/过滤器
**方案**：新增 `PbVisionReportLayout.tsx` 作为整页容器组件，内部通过 React Context（`PbReportContext`）暴露：
- `selectedPlayerId: string` + `setSelectedPlayerId(id)`
- `stageFilter: string` + `setStageFilter`
- `typeFilter: string` + `setTypeFilter`
- `qualityThreshold: number` + `setQualityThreshold`
- `drawerOpen: boolean` + `toggleDrawer`
- `report: AnalysisReportResponse`（从父级传入，只读取不修改）

所有子组件（抽屉栏、球员卡、Filter、Court Coverage、Serves/Returns 等）都通过 `usePbReport()` hook 读取状态。

**为什么选择 Context 而非层层 props 透传**：子组件数量多（抽屉栏+9个内容卡），跨层传递 props 太繁琐；而状态读取者多、写入者少，Context 非常适合。

**备选方案**：Zustand store → 项目暂无 Zustand，为保持零新增依赖而放弃。

### D2. 抽屉栏：`position: fixed` + 页面 padding 补偿，不改动全局 AppShell
**方案**：抽屉栏用 `fixed left-0 top-0 h-screen w-[260px] z-40` 独立定位；其显示/隐藏完全由 PbVisionReportLayout 内部状态控制；主内容根 div 根据 drawerOpen 布尔动态加 `pl-[260px]` 或 `pl-0`。

**为什么不插入全局 AppShell 的侧边栏插槽**：AppShell 是所有页面共用的，插入后必然影响 `/sessions` 等其他页。用 fixed + padding 方案副作用最小、完全隔离。

### D3. 主题作用域化：`.pb-vision-theme` class + `--pb-*` CSS 变量
**方案**：在 `index.css` 中新增一套以 `--pb-` 前缀命名的完整亮色变量（主色、页底、卡片色、6 维色、热力图三段等），并声明它们仅在 `.pb-vision-theme` 作用域下有定义。PbVisionReportLayout 根节点挂 `className="pb-vision-theme"`，其余任何页面不挂。

**为什么不用 Tailwind config 改全局 colors**：会影响所有页面的 green 色板，造成其他页面颜色跑偏。前缀变量 + 作用域 class 是最小副作用方案。

### D4. 饼图/环形图：使用已有 ECharts 依赖
**方案**：PbSkillPieChart（6 分技能饼图）、PbDepthDonut（Serve Depth / Return Depth 双环形图）都使用项目已有的 `echarts` 和 `echarts-for-react` 组件。

**备选**：纯 SVG 手绘 → 可行，但 ECharts 现成、自带 tooltip + hover 高亮、代码量少一半，故弃。

### D5. Court Coverage 热力图：复用 StructuredZoneHeatmap + 新增 colorScheme prop
**方案**：给 StructuredZoneHeatmap 增加可选 prop `colorScheme?: 'default' | 'pb-vision'`（默认 default），传入 pb-vision 时把 ECharts visualMap 改成 `[#FBBF24, #00FF41, #EC4899]`。displayHeatmap 等其他热力图组件同步支持该 prop 保持一致。

**为什么不另起一个组件**：逻辑完全相同，仅颜色数组不同；扩展 prop 比重复一份组件更可维护。

### D6. 无真实字段的数据封装在独立 mock 文件中
**方案**：新建 `src/utils/pbMockData.ts`，导出纯函数：
- `mockInPercent(playerId): number` — In% 进度条
- `mockSpeedPercentile(speedValue, kind: 'ball' | 'paddle'): { percentile: number; label: string }`
- `mockServeReturnStats(playerId)` — Serves/Returns In/Out/Net/Total
- `mockServeReturnDepth(playerId)` — Serve Depth 和 Return Depth 的 Deep/Medium/Shallow 占比数组

所有 UI 组件读取这些 mock 时统一走此文件。未来真实 API 就绪时只需修改该文件内部实现即可，无需改动组件。

**为什么不直接在组件里写死数值**：mock 分布会随时调整，统一入口好维护，也便于未来单元测试。

### D7. Legacy 兼容：ReportPage 内加条件分支，而不是双路由
**方案**：在原 `ReportPage.tsx` 顶部读取 `searchParams.legacy` 或 `localStorage.getItem('reportLegacy')`，为真时渲染原来的 `<div className="min-h-screen bg-green-50">…` 树，否则挂载 `<PbVisionReportLayout report={report} />`。

**备选**：新增 `/report-pb/:id` 路由 → 会让外部链接（训练页、分析工作区跳转报告）变得混乱，需要改多个调用点。单路由内条件分支零成本，且方便通过 query parameter 快速 AB 对比。

## Risks / Trade-offs

- **[Risk] 作用域主题如果意外泄漏会让其他页面变绿色**
  → Mitigation：CSS 变量全部写在 `.pb-vision-theme & { … }` 作用域选择器下；Tailwind 不修改 theme.extend.colors；提 PR 时必须用 `?legacy=1` 对比验证其他页面视觉无差异。

- **[Risk] 抽屉栏 fixed 遮挡了报告页原有的顶部导航 breadcrumb**
  → Mitigation：PbVisionReportLayout 主内容区不仅加 `pl-[260px]`，还要和原 AppShell header 高度对齐（检查 header 高度变量），必要时给 drawer 自身加 `pt-[headerH]` 避开顶部栏。

- **[Risk] 3D 球场组件 + 饼图 + 双环形图 + 热力图，一页内 ECharts/Three 实例多，低端机卡顿**
  → Mitigation：所有可视化组件包一层 `<Suspense fallback={<CardSkeleton />}>`；热力图只在滚动到可视区时用 `IntersectionObserver` 延迟初始化；3D 场景维持现状不复用 WebGL 上下文（已够用，不提前做过度优化）。

- **[Risk] 球员切换时，所有子组件都重新计算 mock 数据，可能抖动**
  → Mitigation：在 `usePbReport()` 里用 `useMemo` 根据 selectedPlayerId 计算 mock 值，保证切换相同球员不触发重新计算。

- **[Trade-off] Legal Thirds 和 Coach 链接占位**：href 写成 "#" 会跳页顶。改进：在按钮 `onClick` 中 `e.preventDefault()` 并 `console.warn('Legal Thirds 链接占位待接')`，避免误触跳动。

## Migration Plan

1. **部署步骤**
   - 本地开发：`npm run dev` → 访问 `/report/demo-double` 默认看到 PB Vision 风格
   - 加 `?legacy=1` 验证旧页面是否完全保留
   - 视觉检查：从报告页跳去首页/分析页，确认这些页面主题没有变绿
   - 跑 `npm run lint && npm run typecheck` 确保无 TS/ESLint 错误
   - 合入后演示环境：默认 PB 风格展示给评委

2. **回滚策略**
   - 轻量回滚：在 PbVisionReportLayout 挂载前读 `localStorage`，设置 `reportLegacy=1` 即可对本机退回旧版
   - 完全回滚：若出现关键 bug，在 ReportPage 的条件分支里把默认值改回 legacy=true，一行代码即可全站回退

3. **未来接真实数据**
   - 球员历史档案上线时：修改 `usePbReport()` 中 `longTermAverage` 和 `deltaValues` 的取值来源，并移除空占位 class 的 `display: none` 样式
   - Serves/Returns 真实统计：修改 `src/utils/pbMockData.ts` 内对应函数，改为从 report 数据里读取计算

## Open Questions

1. 演示当天是否需要让评委手动切换「旧版 vs PB 新版」对比？——如果需要，可以在抽屉栏底部加一个小 toggle 按钮而不是靠改 URL
2. Legal Thirds 区域的跳转按钮，未来是否接入 Shot Explorer 页面（目前该页面叫 Shot Explorer 但项目里还没这个路由）
