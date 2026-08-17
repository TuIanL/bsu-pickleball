# Change Proposal: multiview-observability-visualization

## Why

「联合运行状态」页面（`MultiviewObservabilityPage`）承载双摄协同分析的全部运行事实，但当前以 `MetricRow` 标签-数值形式平铺展示，指标丰富却缺少信息层级，对不了解算法背景的评委等非专业用户难以快速理解。项目即将参加中国体育智能制造大赛，需要将该页面升级为「一眼看懂、逐层深挖」的可视化形态，在不丢失专业细节的前提下提升展示说服力。

## What Changes

- 引入 **ECharts** 作为图表渲染库（新增依赖），封装 `components/platform/viz/` 下的轻量图表组件。
- 页面重构为**三层信息架构**：
  - **L1 概览层**：一句话自动结论 + 整体健康度 + SYNC → FUSION → RECOVERY → REFINEMENT 流水线状态灯（每阶段一个关键数字）。
  - **L2 图形层**：四大域图表卡——同步权威对比柱、融合质量环形图+状态分布堆叠条、恢复六段漏斗图、精修安全门控流程。
  - **L3 明细层**：现有 `MetricRow` 明细、Recovery Episodes 表格、技术运行详情折叠区全部保留，默认收起；球员显示诊断新增 **9 阶段 × 时间 tick 热力图**。
- 新增交互：图表悬停显示原始值与原因文本、L1 流水线点击下钻 L2/L3、恢复时间线事件与热力图格点击定位 Debug Replay 视频、时间范围刷选联动恢复漏斗与时间线。
- 健康度评分由前端从现有字段推导（`effective_multiview_ratio`、恢复成功率、分域 availability 加权），后端算法结论 MUST NOT 被重算（沿用 `multiview-joint-observability` 既有约束）。

## Capabilities

### New Capabilities
- `observability-viz-layer`: 前端可视化层能力——ECharts 图表组件封装、三层信息架构、流水线状态灯、健康度推导、悬停/下钻/时间筛选/视频定位等交互行为。

### Modified Capabilities
- `multiview-joint-observability`: 页面展示需求升级——由平铺指标改为分层可视化展示，新增 L1 概览条、流水线状态灯与 L2 图表化呈现要求；后端投影约束不变。
- `player-display-diagnostics`: 查询 API 增加全时间范围序列获取能力（热力图数据源），基于现有 `timestamp_ms + window_ms` 窗口查询扩展大窗口/分段拉取约定。

## Impact

- **前端**：`src/pages/MultiviewObservabilityPage.tsx` 重构；新增 `src/components/platform/viz/` 图表组件；`package.json` 新增 `echarts` 依赖；`types/report.ts` 或 `multiviewObservability.ts` 可能补充热力图数据聚合类型。
- **后端**：无算法改动；`routes_analysis.py` 的 display-diagnostics 路由仅需确认/放宽窗口查询限制（如窗口上限），不影响已发布产物语义。
- **测试**：`MultiviewObservabilityPage.test.tsx` 需适配新布局；新增可视化组件单元测试。
- **文档**：无外部 API 契约破坏（summary schema 不变）。
