## Context

视频分析结果界面（`VisionPage` → `VideoAnalysisCard`）面向用户暴露了三处开发期信息：

- `StructuredHeatmap.tsx` 渲染 22×10 格点热力图时，hover 显示「第X行第Y列: Z 次」（网格内部坐标），并在底部渲染色阶图例（0 → `max_count`，如 181）。
- `VideoCardHeader` 右侧比分胶囊渲染 `match.score`，真实分析任务中该值是占位符 `"MVP"`（demo 为真实比分 "11 - 8"）。
- `RealVideoFooter` 在视频下方渲染四张检测信息卡（YOLO 人体框 / RTMPose 骨架 / 球轨迹 / 弹跳候选），文案来自后端 artifact 的 `detail` 字段。

这些信息对看比赛的最终用户没有语义，属于开发/调试期产物。用户已决策：**只清理开发向信息，保留热力图本体**；不做球员友好 tooltip 重设计，也不替换为散点图。

## Goals / Non-Goals

**Goals:**
- 热力图不再暴露网格坐标与 `max_count` 刻度；格点颜色可视化保留。
- 视频标题不再显示 "MVP" 占位比分；demo 真实比分保留展示能力。
- 视频下方四张检测信息卡整体移除。

**Non-Goals:**
- 不重设计热力图为球员友好语义（分区名/停留占比/按球员分色）。
- 不替换热力图为散点图。
- 不改动后端数据契约（`visual_grid` / `max_count` / artifact `detail` 字段保留，仍作为调试产物）。
- 不改变 `RealVideoOverlay` 的视频播放层行为（球轨迹、弹跳、骨架、人体框叠加与图层开关、视频内状态徽章）。

## Decisions

### 决策 1：热力图采用纯前端删除，后端零改动

删除 `StructuredHeatmap.tsx` 中的 hover 状态（`hovered` state）、tooltip、hover 高亮描边与 `ColorLegend` 组件渲染。`colorScale` 内部仍用 `grid.max_count` 做配色归一化（蓝→绿→黄→红），只是不再把数字展示给用户。

- **备选 A**：改成球员友好 tooltip（球场区域名 + 停留占比）——被用户否决，且需要后端补充区域语义数据。
- **备选 B**：改用散点图——被用户否决；散点图数据（`scatter_plots.players`）虽已存在，但属另一可视化。
- **理由**：最小改动、不触碰数据契约、无回归面。

### 决策 2：MVP 占位比分胶囊按「有真实比分才显示」处理

`VideoCardHeader` 中比分胶囊只在 `match.score` 存在真实比分时渲染。判定规则：`score` 非空且不等于占位符 `"MVP"`。这样真实任务的占位 "MVP" 消失，demo 的 "11 - 8" 继续显示。

- **备选 A**：直接删除胶囊——会连带 demo 真实比分消失，丢失演示信息。
- **备选 B**：后端生成真实比分——超出本变更范围，属于计分能力后续工作。
- **理由**：保留比分展示能力，仅剔除占位。

### 决策 3：只删 `RealVideoFooter`，props 与 `VisionPage` 不动

删除 `RealVideoFooter` 组件定义（`VideoAnalysisCard.tsx` 约 917–986 行）与其唯一渲染块（约 136–155 行的 `{!compact ? <RealVideoFooter …/> : null}`）。

关键约束：`*Detail` / `*Status` / `*LoadState` props 同时被 `RealVideoOverlay` 使用（图层开关的 `unavailableReason`、视频内状态徽章 `statusCopy`），因此 **`VideoAnalysisCard` 的 props 签名与 `VisionPage.tsx` 的传参保持不变**，只移除 footer 的展示层。

- **备选 A**：连带清理 props——会破坏 `RealVideoOverlay` 的视频内状态徽章与图层不可用提示。
- **理由**：footer 是四张卡的唯一消费者，删除组件与其渲染块即可，无连带。

## Risks / Trade-offs

- **[热力图删图例后用户无法理解色阶含义]** → 用户明确选择"只清理"；颜色仅作直觉热度指示，配色逻辑不变，后续如需语义化可单独变更。
- **[删除 footer 后遗留死代码/未用工具函数]** → `statusCopy` / `statusLabel` / `layerDetail` / `resolveLayerStatus` 在 `RealVideoOverlay` 仍被使用（412–419、833–839 行），不会成为死代码；实施时以 TypeScript 编译与 lint 校验兜底。
- **[误删 `RealVideoOverlay` 仍在用的 props]** → 决策 3 明确 props 签名不变；实施时先跑现有 `VideoAnalysisCard.test.tsx` 确认图层行为未破坏。
