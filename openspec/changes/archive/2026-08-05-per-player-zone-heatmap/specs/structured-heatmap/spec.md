## MODIFIED Requirements

### Requirement: 系统暴露结构化热力图数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点中返回热力图结构化数据，包含 22 行 × 10 列的合并网格计数、最大计数值、球场几何信息，以及每名球员独立网格与展示标签。

#### Scenario: 分析完成后返回热力图数据

- **WHEN** 分析任务状态为 `completed`，且 `PositionVisualizer` 已生成 22×10 网格数据
- **THEN** `/visualization-data` 返回的 JSON 中包含 `heatmaps` 对象，含合并 `visual_grid`（`rows: 22`、`cols: 10`、`max_count` 及 `cells: [{row, col, count}]`）与 `players` 数组，每个球员元素有 `id`、`label`（"球员N"）、`color` 及独立 `grid`（同样含 `rows/cols/max_count/cells`）

#### Scenario: 无可用坐标点时返回空网格

- **WHEN** 球员轨迹数据中无有效坐标点
- **THEN** `heatmaps.visual_grid.cells` 为空数组、`max_count` 为 0，`heatmaps.players` 为空数组

#### Scenario: 球员网格各自归一化计数

- **WHEN** 构建每名球员的独立网格
- **THEN** 每名球员的 `grid.max_count` SHALL 使用该球员自身的最大格计数，而非合并网格的全局峰值

### Requirement: 前端从结构化数据渲染热力图

前端 SHALL 根据 `StructuredVisualizationData` 中的热力图数据，用 SVG 绘制矢量热力图，包含球场底图与颜色映射网格，并支持按球员图例切换显示。每名球员图层 SHALL 使用其自身网格的 `max_count` 归一化配色。组件 SHALL NOT 向用户显示网格坐标 tooltip 或颜色刻度图例（`max_count` 仅用于内部配色归一化，不作为展示信息）。

#### Scenario: 正常显示热力图

- **WHEN** 前端收到有效热力图数据且存在 `heatmaps.players`
- **THEN** 在 `StructuredHeatmap` 组件中渲染 SVG 球场底图，按当前可见球员图层叠加各自的网格，每个网格颜色使用该球员 `color`，透明度根据该球员 `count / max_count` 比例归一化

#### Scenario: 球员图例切换显示

- **WHEN** 用户点击热力图下方的球员图例按钮
- **THEN** 对应球员的网格图层切换显示/隐藏，其余球员图层不受影响

#### Scenario: 默认显示全部球员图层

- **WHEN** 前端首次渲染含 `heatmaps.players` 的热力图
- **THEN** 所有球员图层默认可见

#### Scenario: 仅合并网格时仍可渲染

- **WHEN** `heatmaps.players` 缺失或为空但 `heatmaps.visual_grid` 存在（旧 JSON）
- **THEN** 组件回退渲染合并 `visual_grid`（蓝渐变到红配色），不展示空白的 SVG 区域

#### Scenario: 悬停不显示开发向提示

- **WHEN** 用户鼠标悬停在热力网格上
- **THEN** 不显示 `"第X行第Y列: Z 次"` 之类的网格坐标 tooltip，也不显示从 0 到 `max_count` 的颜色刻度图例

#### Scenario: 数据不可用时降级显示

- **WHEN** 热力图数据为空或请求失败
- **THEN** 组件降级使用旧 PNG 路径显示，不展示空白的 SVG 区域

#### Scenario: 旧 job 无 structured JSON

- **WHEN** 分析任务是在本变更部署前完成的
- **THEN** `/visualization-data` 返回 404，`StructuredHeatmap` 不渲染，`VisualizationArtifactGallery` 显示旧 PNG

#### Scenario: structured JSON 部分字段缺失

- **WHEN** JSON 存在但 `heatmaps.visual_grid` 字段缺失或为 null
- **THEN** 仅热力图区域降级到 PNG，不影响散点图和轨迹图等其他组件
