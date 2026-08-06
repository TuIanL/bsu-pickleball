## MODIFIED Requirements

### Requirement: 前端从结构化数据渲染热力图

前端 SHALL 根据 `StructuredVisualizationData` 中的热力图数据，用 SVG + D3 绘制矢量热力图，包含球场底图与颜色映射网格，每个网格的颜色根据 `count / max_count` 归一化从蓝渐变到红。组件 SHALL NOT 向用户显示网格坐标 tooltip 或颜色刻度图例（`max_count` 仅用于内部配色归一化，不作为展示信息）。

#### Scenario: 正常显示热力图

- **WHEN** 前端收到有效热力图数据
- **THEN** 在 `StructuredHeatmap` 组件中渲染 SVG 球场底图，叠加热力网格，每个网格的颜色根据 `count / max_count` 比例从蓝渐变到红

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
