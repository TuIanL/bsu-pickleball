## Context

双摄协同分析页「跨视角恢复」区包含两个独立问题，均已通过代码级排查确认：

1. **恢复时间线空图（P0）**：`src/components/platform/viz/EChart.tsx` 使用 `echarts/core` 按需注册，已注册 `BarChart / FunnelChart / GaugeChart / HeatmapChart / LineChart / PieChart`，但 `RecoveryTimeline` 的 series 类型为 `scatter`，`ScatterChart` 未在 `echarts.use([...])` 中注册。ECharts 在运行时遇到未注册 series 会静默跳过渲染，而 `grid / xAxis / yAxis / dataZoom` 均已注册，因此用户看到「有坐标轴与滑块、但无数据点」的诡异画面。TS 类型检查与前端 build 均通过，因为 `"type": "scatter"` 是合法 option，TS 不校验运行时注册；现有测试也因 jsdom 无 canvas 直接 fallback，无法发现。

2. **点击事件失效（P0）**：`recoveryTimeline.tsx` 的 click handler 将 `params` 断言为 `{ data?: number[] }` 并读取 `params.data[2]`，但实际 ECharts 传入的 `params` 结构为 `{ value: [x, y, index], data: { value: [...], itemStyle } }`。因此 `index` 永远为 `undefined`，点击无法定位 Debug Replay。

3. **前端伪漏斗（P1）**：`MultiviewObservabilityPage` 在时间范围筛选生效时，用 `allEpisodes` 近似重算漏斗（`recovery_opportunity_count = episode 数`、`guided_candidate = guided + base` 等）。这与页面顶部「后端已发布事实分域展示，页面不重新计算算法结论」的声明冲突，也与 recovery funnel 各层是不同 runtime 事实的语义不符。

4. **主规范已污染**：原引入上述问题的 change `multiview-observability-visualization` 已于 2026-08-18 归档，其 delta 已同步进 `openspec/specs/observability-viz-layer/spec.md` 的「时间范围筛选联动」requirement（「恢复漏斗计数 SHALL 按窗口内 episodes 重新统计」）。本 change 作为独立 change，通过 MODIFIED 该 requirement 把错误语义纠正回来。

## Goals / Non-Goals

**Goals:**
- 让恢复事件时间线真正渲染出 episode 散点（注册 `ScatterChart`）。
- 让点击数据点能正确携带 episode index 并定位 Debug Replay；debug 不可用时仅高亮、不报错。
- 移除前端基于 episodes 近似重算的漏斗，恢复「漏斗始终展示后端权威统计」的自洽。
- 让 spec 与实现一致：时间范围筛选仅过滤 episodes 数据集合。
- 补充能发现「注册缺失 / 取参错误 / 空状态可达」的契约测试。

**Non-Goals:**
- 不把 scatter 升级为 interval/Gantt 风格的 `start→end` 区间时间线（视觉增强，单独立项）。
- 不改动 recovery 算法、episode 投影、funnel 后端聚合逻辑。
- 不整体引入全量 echarts。
- 不调整 `RecoveryTimeline` 的 outcome 分类、颜色或坐标轴语义。

## Decisions

**决策 1：补充注册 + 导出注册集合（同时解决测试盲区）**

`EChart.tsx` 在 `echarts.use([...])` 中追加 `ScatterChart`（从 `echarts/charts` 导入），并将注册数组抽成语义常量：

```ts
export const REGISTERED_ECHART_MODULES = [
  BarChart, FunnelChart, GaugeChart, HeatmapChart,
  LineChart, PieChart, ScatterChart,
  GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, TitleComponent, VisualMapComponent, CanvasRenderer,
];
echarts.use(REGISTERED_ECHART_MODULES);
```

保持按需注册原则（spec 要求 `MUST NOT` 整体引入全量 echarts），仅补齐缺失项。导出常量后，测试可显式断言 `REGISTERED_ECHART_MODULES.includes(ScatterChart)`，从而在「option 合法但运行时组件未注册」这类 bug 上给出真正的回归保护（单纯 `series[0].type === "scatter"` 在同一场景下仍会全绿，必须靠第二个 contract 兜底）。

**决策 2：click handler 兼容两种入口 + 边界检查**

ECharts scatter 点击事件的 `params` 可能是 `{ value: [...], data: {...} }`。修正为：

```ts
const rawValue = Array.isArray(params.value) ? params.value : params.data?.value;
const index = rawValue?.[2];
const episode = Number.isInteger(index) && index >= 0 && index < episodes.length
  ? episodes[index] : undefined;
```

这样不再依赖某一种 event payload 包装形式，且对越界/缺失做防御，避免下次 ECharts 事件结构变化再次踩坑。

**决策 3：点击高亮（而非「什么都不做」）**

当前代码 `if (episode && debugAvailable && onSeek) onSeek(episode)` 在 debug 不可用时什么都不做，与「仅高亮事件」的 spec 要求不一致。改为组件内维护 `selectedEpisodeIndex`：点击任意 episode 都更新选中样式（高亮边框/圆点），仅当 `debugAvailable` 时额外调用 `onSeek`。这样 spec 的「仅高亮事件」真正落地，无需改动「视频定位联动」requirement 文案。

**决策 4：空状态真正可达**

父组件当前 `timelineEpisodes.length > 0 ? <RecoveryTimeline/> : null`，`RecoveryTimeline` 永远不会在空时 mount，因此其内部空状态分支永远触发不了。改为：

```tsx
<div className="mt-4">
  {loadingTimeline ? <LoadingState/> : <RecoveryTimeline episodes={timelineEpisodes} .../>}
</div>
```

由 `RecoveryTimeline` 内部在 `episodes.length === 0` 时渲染占位说明。注意：option 构造纯函数若因程序 bug 抛错，应让测试炸出，不要被 catch 伪装成「无数据」——空数据类型分支只处理「确实无数据」，不吞程序异常。

**决策 5：移除 `windowFunnel`，时间范围仅过滤数据集**

删除 `MultiviewObservabilityPage` 中的 `windowFunnel` useMemo。`RecoveryPanel` 的 `funnel` 始终使用 `data.funnel`（后端权威）。时间范围筛选（`applyRange`）仅影响：
- `getMultiviewRecoveryEpisodes` 请求的 `from_ms`/`to_ms`（分页列表与全量拉取）；
- 传入 `RecoveryTimeline` 的 episodes（即时间线展示的数据集合）。

恢复漏斗不受窗口影响。`from_ms/to_ms` 的作用是「按窗口过滤数据集」，不保证 `xAxis.min/max` 严格等于输入；过滤后若仅剩 13s、16s 两个点，ECharts 自然显示约 13～16s。spec 文案相应改为「过滤 episodes 查询与时间线展示的数据集合」，不再使用「缩放至指定窗口」措辞。

**决策 6：UI 语义提示**

恢复漏斗下方增加一行小字：「恢复漏斗：全场权威统计 · 时间范围仅筛选下方恢复事件」，把「漏斗不随筛选变化」的正确语义显式告知用户，避免误判为筛选失效。

**决策 7：构建体积措辞**

加入 `ScatterChart` 会让 bundle 略有增加（不再承诺体积不变），但仍是按需加载、不会退化为全量 echarts。构建后在 `npm run build` 记录增量体积即可。

## Risks / Trade-offs

- **[风险] 恢复漏斗不再随窗口变化** → 部分用户可能期望「看某时间段里恢复成功多少」。缓解：时间线本身已按窗口过滤 episodes，足以回答「这段时间内发生了什么」；漏斗层保持全局权威统计更符合其「整 run 结论」语义。如需窗口漏斗，应由后端按正式 recovery event counters 按时间窗口聚合，而非前端近似（已在 spec 排除前端重算）。
- **[风险] 抽 option 构造为纯函数会改动组件导出面** → 缓解：仅导出 `buildRecoveryTimelineOption(episodes)` 之类的纯函数供测试，组件内部调用不变，不破坏现有导入。
- **[风险] 其他图表误依赖 `ScatterChart` 全局注册** → 缓解：按需注册已在一处集中管理，补充后不影响其他图表。
- **[权衡] 不在此次做 interval 时间线升级** → 接受短期仍是 scatter 表达（仅 start_ms、点大小表 duration），先解决「有没有、点了能不能动」的 P0 与「数据不能说谎」的 P1，视觉增强另立项，避免一次 change 过大。

## Migration Plan

1. 在 `EChart.tsx` 注册 `ScatterChart` 并导出 `REGISTERED_ECHART_MODULES`，部署后恢复时间线即出现散点。
2. 修正 `recoveryTimeline.tsx` 的 click handler 与选中高亮，点击定位立即生效。
3. 删除 `MultiviewObservabilityPage` 的 `windowFunnel`，时间范围筛选后漏斗数字恢复为后端全局统计。
4. 恒挂载 `RecoveryTimeline` 并补空状态占位 + UI 语义提示。
5. 合入 spec 修正（MODIFIED `observability-viz-layer` 纠正已进入主规范的错误 requirement）。

回滚：上述改动均为局部、可独立 revert；若注册或 click 修复引入回归，可单独 revert 对应文件而不影响其他部分。

## Open Questions

- 是否需要为「窗口内恢复统计」在后端新增按时间窗口聚合的正式接口？当前决策是前端不做，留待后续按 spec 走后端化路径。本 change 不实现。
- interval/Gantt 风格时间线增强的立项名称与范围，需另开 change 讨论。
