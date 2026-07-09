## ADDED Requirements

### Requirement: 系统暴露结构化热力图数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点中返回热力图结构化数据，包含 22 行 × 10 列的网格计数、最大计数值、球场几何信息。

#### Scenario: 分析完成后返回热力图数据
- **WHEN** 分析任务状态为 `completed`，且 `PositionVisualizer` 已生成 22×10 网格数据
- **THEN** `/visualization-data` 返回的 JSON 中包含 `heatmaps` 数组，每个元素有 `rows: 22`、`cols: 10`、`max_count` 及 `cells: [{row, col, count}]`

#### Scenario: 无可用坐标点时返回空网格
- **WHEN** 球员轨迹数据中无有效坐标点
- **THEN** `heatmaps.cells` 为空数组，`max_count` 为 0

### Requirement: 前端从结构化数据渲染热力图

前端 SHALL 根据 `StructuredVisualizationData` 中的热力图数据，用 SVG + D3 绘制矢量热力图，包含球场底图、颜色映射网格、颜色标尺和图例。

#### Scenario: 正常显示热力图
- **WHEN** 前端收到有效热力图数据
- **THEN** 在 `StructuredHeatmap` 组件中渲染 SVG 球场底图，叠加热力网格，每个网格的颜色根据 `count / max_count` 比例从蓝渐变到红

#### Scenario: Hover 时显示网格计数
- **WHEN** 用户鼠标悬停在热力网格上
- **THEN** 显示 tooltip，内容为 `"第X行第Y列: Z 次"`，其中 Z 为该网格的 count 值

#### Scenario: 显示颜色标尺
- **WHEN** 热力图渲染完成
- **THEN** 在球场右侧或底部显示颜色渐变标尺，标注从 0 到 `max_count` 的刻度

#### Scenario: 数据不可用时降级显示
- **WHEN** 热力图数据为空或请求失败
- **THEN** 组件降级使用旧 PNG 路径显示，不展示空白的 SVG 区域

#### Scenario: 旧 job 无 structured JSON
- **WHEN** 分析任务是在本变更部署前完成的
- **THEN** `/visualization-data` 返回 404，`StructuredHeatmap` 不渲染，`VisualizationArtifactGallery` 显示旧 PNG

#### Scenario: structured JSON 部分字段缺失
- **WHEN** JSON 存在但 `heatmaps.visual_grid` 字段缺失或为 null
- **THEN** 仅热力图区域降级到 PNG，不影响散点图和轨迹图等其他组件
