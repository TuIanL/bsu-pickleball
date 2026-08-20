## 1. 注册 ScatterChart（P0）

- [x] 1.1 在 `src/components/platform/viz/EChart.tsx` 从 `echarts/charts` 导入 `ScatterChart`
- [x] 1.2 将注册数组抽为导出常量 `REGISTERED_ECHART_MODULES`（含 BarChart / FunnelChart / GaugeChart / HeatmapChart / LineChart / PieChart / ScatterChart 及现有 components / renderer），并以 `echarts.use(REGISTERED_ECHART_MODULES)` 注册；保持按需加载原则，不整体引入全量 echarts

## 2. 修复点击定位与高亮（P0）

- [x] 2.1 修正 `src/components/platform/viz/recoveryTimeline.tsx` 的 `handleClick`：兼容 `{ value }` 与 `{ data.value }` 两种入口（`const rawValue = Array.isArray(params.value) ? params.value : params.data?.value; const index = rawValue?.[2];`），并做 `Number.isInteger(index) && index >= 0 && index < episodes.length` 边界检查
- [x] 2.2 `RecoveryTimeline` 内部维护 `selectedEpisodeIndex`：点击任一 episode 始终更新选中样式（高亮边框/圆点）；仅当 `debugAvailable` 时才调用 `onSeek`，否则仅高亮、不报错（兑现主 spec「视频定位联动」的「仅高亮事件」要求）

## 3. 显式空/异常状态（P0）

- [x] 3.1 父组件 `MultiviewObservabilityPage` 不再用 `timelineEpisodes.length > 0 ? <RecoveryTimeline/> : null`，改为恒挂载；`loadingTimeline` 时显示 LoadingState，否则渲染 `<RecoveryTimeline episodes={timelineEpisodes} .../>`
- [x] 3.2 `RecoveryTimeline` 在 `episodes.length === 0` 时渲染明确占位说明（沿用 SectionBadge 语义），但 option 构造若为程序异常应抛出由测试捕获，不得伪装成无数据

## 4. 渲染契约测试（P0 关键，拆分）

- [x] 4.1 将 `RecoveryTimeline` 的 option 构造抽成可导出纯函数 `buildRecoveryTimelineOption(episodes)`，组件内部调用不变
- [x] 4.2 Contract A（option 需要 scatter）：断言生成的 option 含 `series[0].type === "scatter"` 且 `series[0].data.length === episodes.length`
- [x] 4.3 Contract B（运行时真的注册了 scatter）：断言 `REGISTERED_ECHART_MODULES` 含 `ScatterChart`（或 mock `echarts.use`，验证传参包含 `ScatterChart`）——用于捕获「option 合法但运行时组件未注册」类回归
- [x] 4.4 点击 handler 测试：构造 `{ value: [12.3, 0, 57] }`，断言 `onSeek` 以 `episodes[57]` 调用；构造 `params.data.value` 形态再测一次覆盖兼容性；构造越界 index 断言不报错且不选

## 5. 移除前端伪漏斗聚合（P1）

- [x] 5.1 删除 `src/pages/MultiviewObservabilityPage.tsx` 中的 `windowFunnel` useMemo 及其对 `allEpisodes` 的近似统计逻辑
- [x] 5.2 `RecoveryPanel` 的 `funnel` 始终使用 `data.funnel`（后端权威统计），移除 `windowFunnel ?? funnel` 回退
- [x] 5.3 验证时间范围筛选仍驱动 episodes 查询（`from_ms`/`to_ms`）与时间线数据集合过滤，但恢复漏斗数字不再随窗口变化

## 6. 时间范围语义与 UI 文案（P1）

- [x] 6.1 已写入 `specs/observability-viz-layer/spec.md` 的 MODIFIED requirement（漏斗 MUST NOT 随窗口前端重算、语义改为「过滤数据集合」）；archive 时需与 `openspec/specs/observability-viz-layer/spec.md` 合并
- [x] 6.2 恢复漏斗区增加文案「恢复漏斗：全场权威统计 · 时间范围仅筛选下方恢复事件」

## 7. 验证

- [x] 7.1 运行 `npm run build`（tsc -b && vite build）通过，记录 bundle 体积增量（基线 1,414.83 kB / gzip 440.83 kB → 含 ScatterChart 1,421.21 kB / gzip 442.59 kB，增量 +6.38 kB / gzip +1.76 kB，约 +0.4%，仍为按需加载）
- [x] 7.2 运行现有 `MultiviewObservabilityPage.test.tsx` 与新增 recoveryTimeline 测试，全部通过（全套 59 文件 / 420 测试通过）
- [x] 7.3 在真实浏览器（非 jsdom）确认：恢复时间线出现散点、点击数据点可定位 Debug Replay、debug 不可用时点击仅高亮、时间范围筛选仅过滤时间线且漏斗保持后端全局统计（Chrome + vite dev + 本地后端 job-d828b23bd4：canvas 散点绘制确认；点击绿点 video.currentTime 0→54.733s 与 re_000127 的 debug_video_seek_ms=54733.333 精确吻合；选中点出现 #14241B 描边像素；[100s,200s] 空窗口渲染占位、[50s,700s] 窗口时间线缩至 42 事件，limit=100/limit=8 两类查询均携带 from_ms/to_ms，漏斗两次筛选前后均保持 1682/59/82/59 不变；「debug 不可用仅高亮」路径无本地数据，由 recoveryTimeline.test.tsx 组件测试覆盖）
