## Why

双摄协同分析页面「跨视角恢复」区的恢复事件时间线（RecoveryTimeline）一直只显示 X/Y 坐标轴与底部 dataZoom 滑块，却没有任何数据点。根因已通过代码级排查确认：页面使用 `echarts/core` 按需注册模式，`src/components/platform/viz/EChart.tsx` 的注册列表缺少 `ScatterChart`，而 `RecoveryTimeline` 的 series 类型是 `scatter`，导致 ECharts 运行时静默跳过整个 series 渲染（坐标轴与 dataZoom 已注册，照常显示）。

进一步排查发现同一组件还有两个附带缺陷：(1) click handler 把 `params` 断言为 `{ data?: number[] }` 并读取 `params.data[2]`，但实际 `params.data` 是 `{ value: [...], itemStyle: {...} }`，点击事件永远取不到 episode index，无法定位 Debug Replay；(2) 时间范围筛选生效时，前端用 `allEpisodes` 近似重算恢复漏斗（把 episode 数当 opportunity / guidance 数、把 `guided+base` 当 candidate / expected-global-preserved 数），这与页面顶部「不重新计算算法结论」的声明冲突，也与 recovery funnel 各层是不同 runtime 事实的语义不符。

**补充背景（2026-08-19 复核）**：原引入这些问题的 change `multiview-observability-visualization` 已于 2026-08-18 归档，其 delta 已同步进主 spec `openspec/specs/observability-viz-layer/spec.md`，其中「时间范围筛选联动」requirement 已被错误写成「恢复漏斗计数 SHALL 按窗口内 episodes 重新统计」。因此本 change 不再「并回」原 change（已冻结），而是作为独立 change，通过 MODIFIED `observability-viz-layer` 把这条已进入主规范的错误 requirement **纠正回来**。

## What Changes

- **注册缺失的图表类型**：在 `EChart.tsx` 的按需注册列表中加入 `ScatterChart`，使 recovery episode 的 scatter 时间线能够渲染。导出 `REGISTERED_ECHART_MODULES` 常量，便于断言注册完整性。
- **修复点击事件定位**：`RecoveryTimeline` 的 click handler 改为兼容 ECharts 两种 event payload 入口（`params.value` 或 `params.data.value`），并做边界检查，从索引位取 episode index，点击可正确定位 Debug Replay。
- **点击高亮（debug 不可用时）**：`RecoveryTimeline` 内部维护 `selectedEpisodeIndex` 状态，点击任一 episode 始终更新选中样式；仅当 `debugAvailable` 时才调用 `onSeek`，否则仅高亮事件、不报错（对应主 spec「视频定位联动」的「仅高亮事件」要求）。
- **显式空/异常占位**：父组件不再用 `length > 0` 决定是否挂载 `RecoveryTimeline`，而是恒挂载组件，由 `RecoveryTimeline` 内部处理 `episodes` 为空时的占位说明。不要让 option 构造错误被伪装成无数据——程序 bug 应由测试炸出，而非 UI 静默吞掉。
- **移除前端伪漏斗聚合（P1）**：删除 `MultiviewObservabilityPage` 中的 `windowFunnel` 近似逻辑。时间范围筛选仅驱动 episodes 查询（`from_ms`/`to_ms`）与时间线展示的数据集合过滤，不再前端重算恢复漏斗。
- **恢复漏斗始终展示后端权威统计（P1）**：时间范围筛选生效时，恢复漏斗继续使用后端 `section.data.funnel` 的完整 run 统计，不再被窗口内 episode 替代。
- **时间范围语义改准（P1）**：明确「时间范围筛选」的语义为「过滤 episodes 查询与时间线展示的数据集合」，不保证 xAxis min/max 严格等于输入窗口；不再承诺「时间线缩放至指定窗口」。
- **UI 语义提示**：恢复漏斗区增加一行文案「恢复漏斗：全场权威统计 · 时间范围仅筛选下方恢复事件」，避免用户误以为筛选坏了漏斗。
- **测试契约拆分（P0 关键）**：拆分为两个独立 contract——(A) `RecoveryTimeline` 的 option 要求 `scatter`；(B) `EChart` 运行期确实注册了 `ScatterChart`（断言 `REGISTERED_ECHART_MODULES` 含 `ScatterChart`，或 mock `echarts.use` 验证参数）。这样即使有人从 `echarts.use()` 删除 `ScatterChart`，测试也会变红。
- **同步修正主 spec（P1）**：MODIFIED `observability-viz-layer` 的「时间范围筛选联动」requirement，纠正「恢复漏斗计数 SHALL 按窗口内 episodes 重新统计」为「过滤数据集」语义。

本 change **不包含** scatter → interval/Gantt 风格的恢复时间线视觉升级（即把单点表达为 `start_ms → end_ms` 区间条），该增强单独立项。

## Capabilities

### New Capabilities

<!-- 无新增 capability -->

### Modified Capabilities

- `observability-viz-layer`：修改「时间范围筛选联动」requirement——时间范围筛选不再驱动前端重算恢复漏斗，而是仅过滤 episodes 查询与时间线展示的数据集合；恢复漏斗始终展示后端已发布的完整 run 权威统计，呼应「页面不重新计算算法结论」的不变量。该 modification 同时纠正 2026-08-18 归档时已进入主规范的同一条错误 requirement。

## Impact

- **代码**：`src/components/platform/viz/EChart.tsx`（注册 ScatterChart + 导出 REGISTERED_ECHART_MODULES）、`src/components/platform/viz/recoveryTimeline.tsx`（click handler + 选中高亮 + 空状态）、`src/pages/MultiviewObservabilityPage.tsx`（移除 `windowFunnel`、恒挂载 RecoveryTimeline、漏斗始终用后端统计、UI 文案）。
- **测试**：新增 `recoveryTimeline` 的渲染契约测试（contract A/B）与点击定位/高亮测试；可能补充 `EChart` 注册完整性测试。
- **Spec**：`openspec/specs/observability-viz-layer/spec.md` 的「时间范围筛选联动」requirement 产生 MODIFIED delta（纠正已进入主规范的语义）。
- **依赖与体积**：`echarts` 仍使用 `^6.1.0`，仅补充已存在的按需注册项，**不改变按需加载原则**（不会退化为整体引入全量 echarts）；但加入 `ScatterChart` 会令 bundle 略有增加，建议在 `npm run build` 后记录增量，而非承诺体积不变。
- **行为变化**：时间范围筛选后恢复漏斗数字不再变化（之前是前端近似的错误数字），且时间线仅展示过滤后的 episodes。这是修正而非破坏；页面顶部「不重新计算算法结论」声明因此恢复自洽。
