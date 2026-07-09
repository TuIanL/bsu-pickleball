## Why

当前视频分析结果页面的可视化产物（热力图、散点图）由后端 OpenCV 生成固定 220×420 像素的 PNG 图片，前端以 `<img>` 标签显示时被拉伸放大至数倍尺寸，导致严重像素化、字体模糊、细节丢失。同时，前端 SVG 球场轨迹图、sparkline 和柱状图设计简陋，缺乏图例、标签、交互反馈等基本视觉元素。

本变更将可视化渲染从后端 PNG 迁移到前端 SVG，实现无限分辨率、可交互、视觉一致的高质量图表展示，提升产品专业度和学术展示价值。

## What Changes — MVP（核心链路）

- **后端新增 PositionVisualizationDataBuilder**：从检测/跟踪数据构建结构化可视化数据，与 `PositionVisualizer` 的 PNG 绘制职责分离
- **后端新增 `/visualization-data` API**：返回结构化数据 `{ court, heatmaps: { visual_grid: { rows: 22, cols: 10, ... } }, scatter_plots, player_trajectories }`
- **前端引入 D3.js 子包**：`d3-scale`, `d3-interpolate`, `d3-array`，仅用于颜色插值和坐标映射
- **前端创建 courtGeometry.ts**：球场物理坐标（20ft × 44ft）到 SVG viewBox 的映射工具
- **前端重写热力图渲染**：`StructuredHeatmap` 组件，SVG + D3 绘制 22×10 网格，含 hover tooltip 和颜色标尺图例
- **前端重写散点图渲染**：`StructuredScatterPlot` 组件，SVG 绘制球员/球/弹跳分层散点图，含可切换图例
- **前端 VisualizationArtifactGallery 集成**：优先加载结构化数据，数据不可用时降级到旧 PNG
- **后端保留 PNG 生成作为 fallback**

## What Changes — Optional（可后置的 UI 美化）

- **SVG 球场轨迹图美化**：增加坐标参考网格、球员名称标签、路径方向渐变、图例卡片
- **MetricCard sparkline 美化**：增加面积渐变填充、平均值参考基线、当前值标记点
- **ProgressChart 柱状图美化**：增加数值标签、hover 突出效果

## Capabilities

### New Capabilities

- `structured-heatmap`: 前端从结构化数据渲染热力图，包括 22×10 网格计数、颜色映射、hover 交互（MVP）
- `structured-scatter-plot`: 前端从结构化坐标数据渲染散点图，包括球员/球/弹跳点的分层显示与图例（MVP）
- `frontend-viz-beautification`: 改进前端球场轨迹图、sparkline、柱状图的视觉设计（Optional）

### Modified Capabilities

- （无现有 spec 被修改 — 当前可视化没有独立 spec 文件）

## Impact

- **后端新增代码**：`visualization_schemas.py` 新增结构化数据 schema；`PositionVisualizationDataBuilder` 构建结构化数据；`PositionVisualizer` 重构为消费结构化数据；`routes_analysis.py` 新增 API 端点
- **前端新增依赖**：D3.js (`d3-scale`, `d3-interpolate`, `d3-array`)
- **前端新增组件**：`StructuredHeatmap.tsx`, `StructuredScatterPlot.tsx`
- **前端修改组件**：`App.tsx` 中 `VisualizationArtifactGallery` 的渲染逻辑
- **无 breaking changes**：后端 PNG 生成保留，旧 API 端点不变。Optional 部分涉及 `ReportVisualization.tsx`、`MetricCard.tsx`、`ProgressChart.tsx`

## Acceptance Criteria

- **旧 job 兼容**：没有 structured JSON 的旧分析任务，前端不报错，显示旧 PNG
- **运行中 job 兼容**：分析任务未完成时 `/visualization-data` 返回 404，前端展示 fallback 状态
- **部分数据缺失**：structured JSON 缺少某些字段时，对应组件局部 fallback，不影响报告页其他部分
- **22×10 与 11×5 区分**：`heatmaps.visual_grid`（22×10）用于可视化渲染，`PerformanceMetrics.Heatmap`（11×5）用于报告指标，二者在文档和代码中明确分开
