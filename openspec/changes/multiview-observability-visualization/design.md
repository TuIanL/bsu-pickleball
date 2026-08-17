# Design: multiview-observability-visualization

## Context

「联合运行状态」页面（`src/pages/MultiviewObservabilityPage.tsx`）由后端 `MultiviewObservabilityProjector` 投影 `multiview_observability_summary.v1` 驱动，展示 SYNC / FUSION / RECOVERY / REFINEMENT / DEBUG 五个分域的事实。当前全部指标用 `MetricRow`（标签-数值）平铺，信息丰富但缺少层级；受众为竞赛评委（非算法背景），需要在 30 秒内建立"这次双摄协同分析是否可信"的直觉。

既有约束（沿用 `multiview-joint-observability` spec）：前端 MUST NOT 重算 authoritative eligibility、sync quality、Safety Gate 或 `final_source`；各分域 availability 独立。

数据现状（已核实）：
- `getMultiviewObservability(jobId)` 一次返回完整 summary，字段覆盖全部可视化所需数据；
- `getPlayerDisplayDiagnostics(jobId, playerId, timestampMs, windowMs=500)` 已支持时间窗口查询，热力图可基于此分段拉取，无需改产物语义；
- Recovery episodes 接口已支持 `from_ms`/`to_ms` 过滤，时间刷选可直接复用。

## Goals / Non-Goals

**Goals:**
- 面向评委的"一眼看懂"：L1 概览（一句话结论 + 健康度 + 流水线状态灯）在无滚动时即可理解。
- 四大域全部图表化（对比柱 / 环形+堆叠 / 漏斗 / 门控流程），恢复漏斗与显示诊断热力图为展示重点。
- 专业细节零丢失：L3 明细默认折叠但完整保留，所有悬停可下钻原文。
- 引入 ECharts 并按需加载，控制包体增量。

**Non-Goals:**
- 不修改后端投影语义、不重算任何算法结论（既有 MUST NOT 约束不变）。
- 不做多任务对比视图（跨 job 聚合不在本次范围）。
- 不做实时轮询刷新（现有手动刷新机制保留）。
- 不重构 Recovery episodes 分页/筛选后端逻辑。

## Decisions

### D1: 图表库选型 ECharts（按需引入）
- **选择**：`echarts/core` + 按需注册（`BarChart`、`PieChart`、`LineChart`、`HeatmapChart`、`FunnelChart`、`GaugeChart`、`GridComponent`、`TooltipComponent`、`DataZoomComponent` 等），不整体引入 `echarts` 全量包。
- **理由**：漏斗图、热力图、桑基图为原生支持；竞赛展示需要高质量 tooltip 与 dataZoom 交互；文档成熟。
- **备选**：Recharts（漏斗/热力图支持弱）、手写 SVG（零依赖但开发量大、交互成本高）。被否。

### D2: 三层信息架构（L1 / L2 / L3）
- 页面按 `L1 概览 → L2 图形 → L3 明细` 纵向组织，L1 占首屏上部。
- L1 流水线状态灯用**纯 HTML/CSS**（轻量、风格统一、便于点击锚点），图表化内容才用 ECharts——避免为简单状态灯引入重型组件。
- L2 四域图表卡 2×2 网格；L3 明细全部默认折叠（沿用现有 `details` 模式）。
- **理由**：信息层级是本次改造核心；分层后非专业用户止步 L1，专业用户可钻到底。

### D3: 健康度评分为"展示汇总"而非"算法重算"
- 前端从现有字段推导 0-100 评分：四域 availability 加权（available=1.0 / partial=0.6 / unavailable=0 / not_applicable 不计权）+ `effective_multiview_ratio` + 恢复成功率（guided 成功/机会）混合。
- 评分旁 MUST 标注"由前端基于后端事实汇总"，不宣称算法结论；页脚说明沿用既有"页面不重新计算算法结论"。
- **理由**：评委需要整体印象；同时守住不重算的红线（评分的输入全部是后端已发布事实）。

### D4: 热力图数据获取——现有 API 分段拉取
- 前端按固定窗口（如 2000ms）分段调用 `display-diagnostics?timestamp_ms=&window_ms=`，客户端拼接为 `(stage × tick)` 矩阵；仅拉取当前选中球员，切换球员时重新拉取。
- 若某段返回 `partial` 或窗口无行，对应列留空（灰色"未触发"），不伪造数据。
- 后端仅在需要时放宽 `window_ms` 上限（若无现成上限则无需改动）。
- **理由**：零产物语义改动，复用已验证的窗口查询；热力图是 L3 调试工具，容忍分段拉取的加载开销。

### D5: 交互设计
- **悬停**：ECharts `tooltip.formatter` 输出原始值 + `authority_reason` / `reason_code` / `safety_gate.reason` 原文（后端字段已含）。
- **下钻**：L1 流水线阶段点击 → `scrollIntoView` 至对应 L2 卡片；L2 卡片内"查看明细" → 展开 L3。
- **时间筛选**：恢复卡片顶部加时间范围 slider（起止 ms），写入 URL query 或组件 state，同时驱动漏斗过滤与 episodes 请求的 `from_ms/to_ms`（接口已支持）。
- **视频定位**：恢复时间线事件 / 热力图格点击 → 复用现有 `onSeek(episode.debug_video_seek_ms)` 机制与 `DebugReplayPanel` 的 `currentTime` 定位，不新增机制。

## Risks / Trade-offs

- [ECharts 包体增加] → 按需引入 `echarts/core` 并注册最少组件；构建后用 `vite build` 产物体积验证（目标增量 < 150KB gzip）。
- [热力图全量数据量大] → 分段拉取 + 仅当前球员 + 时间范围限定；必要时前端抽样（>500 tick 时降采样）。
- [健康度评分被误读为算法结论] → 明确标注"展示汇总"，沿用既有页面免责声明。
- [现有测试破坏] → `MultiviewObservabilityPage.test.tsx` 适配新 DOM 结构；可视化组件补单测（图表渲染用最小数据 fixture）。
- [评委演示时缺数据/未生成 debug 视频] → 所有图表对 `partial/unavailable` 分域降级为占位说明（沿用 `SectionBadge` 语义），不渲染空图。

## Migration Plan

1. 阶段一（基础）：安装 `echarts`；新建 `components/platform/viz/`（`EChart.tsx` 封装 + 按需注册）；新增 L1 概览条与流水线状态灯（纯 HTML/CSS），接入现有 summary 数据。
2. 阶段二（四大域图表）：同步对比柱、融合环形+堆叠、恢复漏斗图、精修门控流程，逐个替换对应 Panel 内的 `MetricRow` 网格。
3. 阶段三（热力图与交互）：球员显示热力图（分段拉取拼接）、悬停 tooltip 全文、时间刷选联动、视频定位联动。
4. 阶段四（收尾）：测试适配与新增、`vite build` 体积验证、旧明细层默认折叠、演示数据造数脚本（可选）。
- **回滚策略**：每阶段独立提交；任一阶段可单独 revert，L3 明细完整保留保证功能不倒退。

## Open Questions

- 健康度评分的权重组合是否需要后端提供一份"官方权重"？当前由前端推导，若评委口径有要求可后续在 summary 中增加 `health_score` 字段（属后端变更，另行提案）。
- 热力图时间轴粒度：默认按 tick 展示即可，是否需要切换为固定 ms 桶（如 100ms/桶）？待实现时以数据量实测决定。
- 是否需要在 L1 提供"演示模式"（自动播放/高亮讲解路径）以配合现场答辩？若需要，追加到交互需求。
