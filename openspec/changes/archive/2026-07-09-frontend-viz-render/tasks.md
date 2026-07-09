## MVP（核心数据链路）

### 1. 后端 StructuredVisualizationData schema 与 JSON 写入

- [x] 1.1 在 `visualization_schemas.py` 中创建 `StructuredVisualizationData` 数据类，包含：
  - `court`: 球场几何（dimensions, net, center）
  - `heatmaps.visual_grid`: `{ rows: 22, cols: 10, max_count, cells: [{row, col, count}] }`
  - `scatter_plots.players`: `[{ id, label, color, points: [[x,y],...] }]`
  - `scatter_plots.ball`: `[[x,y],...]`
  - `scatter_plots.bounces`: `[[x,y],...]`
  - `player_trajectories`: `[{ id, label, path: [[x,y],...] }]`
- [x] 1.2 创建 `PositionVisualizationDataBuilder`，从检测/跟踪数据构建 `StructuredVisualizationData`，与 `PositionVisualizer` 的数据计算逻辑复用
- [x] 1.3 修改 `PositionVisualizer.generate()`：接收 `StructuredVisualizationData` 作为数据源，不再重复计算 22×10 网格
- [x] 1.4 `PositionVisualizationDataBuilder.build()` 结果写入 `position_visualizations/structured/` 目录

### 2. 后端 /visualization-data API

- [x] 2.1 在 `routes_analysis.py` 中新增 `GET /api/analysis/jobs/{job_id}/visualization-data` 端点，读取 structured JSON 并返回
- [x] 2.2 旧 job / job 未完成时返回 404（不做空 JSON 占位），前端据此触发 fallback

### 3. 前端 courtGeometry 坐标映射工具

- [x] 3.1 安装 D3 子包：`d3-scale`、`d3-interpolate`、`d3-array`
- [x] 3.2 在 `analysisClient.ts` 中新增 `getStructuredVizData(jobId)` 函数
- [x] 3.3 创建 `src/utils/courtGeometry.ts`，封装球场物理坐标（20ft × 44ft）到 SVG viewBox 的映射函数

### 4. 前端 StructuredHeatmap 组件

- [x] 4.1 创建 `StructuredHeatmap.tsx`：SVG 球场底图渲染（使用 courtGeometry 映射）
- [x] 4.2 实现 D3 颜色插值：`count / max_count` → 蓝→绿→黄→红
- [x] 4.3 实现 22×10 网格层渲染
- [x] 4.4 实现 hover tooltip："第X行第Y列: Z 次"
- [x] 4.5 实现颜色标尺图例（渐变条 + 刻度）
- [x] 4.6 实现降级逻辑：`heatmaps.visual_grid` 为空或请求失败时显示旧 PNG

### 5. 前端 StructuredScatterPlot 组件

- [x] 5.1 创建 `StructuredScatterPlot.tsx`：SVG 球场底图渲染
- [x] 5.2 实现球员/球/弹跳点的分层渲染，每位球员独立颜色
- [x] 5.3 实现可切换图例：点击图例项切换对应图层显示/隐藏
- [x] 5.4 实现降级逻辑：`scatter_plots` 数据为空或请求失败时显示旧 PNG

### 6. 前端 VisualizationArtifactGallery 集成

- [x] 6.1 修改 `VisualizationArtifactGallery`：优先调用 `getStructuredVizData`，加载 `StructuredVisualizationData`
- [x] 6.2 数据可用时分别使用 `StructuredHeatmap` 和 `StructuredScatterPlot`，数据不可用时 fallback 到旧 `<img>` PNG

---

## Optional（UI 美化 — 可后置）

### A. ReportVisualization 球场轨迹图美化

- [x] A.1 viewBox 从 100×72 改为 1000×720，按比例缩放所有坐标和尺寸
- [x] A.2 增加浅灰色虚线坐标参考网格
- [x] A.3 增加球员名称标签（起点/终点旁）
- [x] A.4 轨迹折线增加从浅绿到深绿的渐变
- [x] A.5 增加图例卡片（右下角）

### B. MetricCard sparkline 美化

- [x] B.1 折线下方增加半透明面积渐变填充
- [x] B.2 在平均值位置绘制浅灰色虚线参考基线

### C. ProgressChart 柱状图美化

- [x] C.1 每根柱状顶部增加百分比数值标签
- [x] C.2 hover 时柱子宽度增加、显示更详细的信息

---

## 验收

### 9. 兼容性与失败态

- [x] 9.1 旧 job 无 structured JSON 时，前端不报错并显示旧 PNG
- [x] 9.2 `/visualization-data` 返回 404/empty/null 时，前端展示 fallback 状态，不白屏
- [x] 9.3 structured JSON 部分字段缺失时，对应组件显示局部 fallback，不影响整个报告页
- [x] 9.4 22×10 `visual_grid` 和 11×5 `metrics_heatmap` 在文档和 schema 中明确区分用途，避免后续混淆
