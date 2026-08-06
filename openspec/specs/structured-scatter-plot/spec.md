# structured-scatter-plot Specification

## Purpose

定义结构化散点图数据的后端输出、前端渲染、图例切换和历史任务缺失数据时的降级行为，确保轨迹数据和可视化组件边界清晰可测。
## Requirements
### Requirement: 系统暴露结构化散点图数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点中返回散点图结构化数据，包含每位球员的轨迹坐标序列、球轨迹坐标序列、弹跳事件坐标序列。每位球员的 `id` SHALL 为 canonical player ID（`Player_1`..`Player_4`），`label` SHALL 为 `P1`..`P4`（与视频叠加 HUD 对齐）。

#### Scenario: 分析完成后返回散点图数据
- **WHEN** 分析任务状态为 `completed`
- **THEN** `/visualization-data` 返回的 JSON 中包含 `scatter_plots` 对象，含有 `players: [{id: canonical Player_N, label: P1..P4, points: [[x,y],...]}]`、`ball: [[x,y],...]`、`bounces: [[x,y],...]` 字段

#### Scenario: 无球轨迹时球数据为空
- **WHEN** 球检测未启用或未检测到球
- **THEN** `scatter_plots.ball` 为空数组

### Requirement: 前端从结构化数据渲染散点图

前端 SHALL 根据 `StructuredVisualizationData` 中的散点图数据，用 SVG 绘制矢量散点图，包含球场底图、球员/球/弹跳点的分层显示与可切换图例。

#### Scenario: 正常显示散点图
- **WHEN** 前端收到有效的散点图数据
- **THEN** 在 `StructuredScatterPlot` 组件中渲染 SVG 球场底图，叠加以下图层：
  - 球员轨迹点（每位球员独立颜色，半透明）
  - 球轨迹点（统一蓝色，较小半径）
  - 弹跳候选点（十字标记，红色）

#### Scenario: 图例可切换显示
- **WHEN** 用户点击图例中的球员名称或类别
- **THEN** 对应图层切换显示/隐藏

#### Scenario: 数据不可用时降级显示
- **WHEN** 散点图数据为空或请求失败
- **THEN** 组件降级使用旧 PNG 路径显示

#### Scenario: 旧 job 无 structured JSON
- **WHEN** 分析任务是在本变更部署前完成的
- **THEN** `/visualization-data` 返回 404，`StructuredScatterPlot` 不渲染，`VisualizationArtifactGallery` 显示旧 PNG

#### Scenario: structured JSON 部分字段缺失
- **WHEN** JSON 存在但 `scatter_plots` 字段缺失或为 null
- **THEN** 仅散点图区域降级到 PNG，不影响热力图和轨迹图等其他组件

