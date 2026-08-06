# structured-scatter-plot Specification

## Purpose

定义结构化散点图数据的后端输出、前端渲染、图例切换和历史任务缺失数据时的降级行为，确保轨迹数据和可视化组件边界清晰可测。

## MODIFIED Requirements

### Requirement: 系统暴露结构化散点图数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点中返回散点图结构化数据，包含每位球员的轨迹坐标序列、球轨迹坐标序列、弹跳事件坐标序列。每位球员的 `id` SHALL 为 canonical player ID（`Player_1`..`Player_4`），`label` SHALL 为 `P1`..`P4`（与视频叠加 HUD 对齐）。

#### Scenario: 分析完成后返回散点图数据
- **WHEN** 分析任务状态为 `completed`
- **THEN** `/visualization-data` 返回的 JSON 中包含 `scatter_plots` 对象，含有 `players: [{id: canonical Player_N, label: P1..P4, points: [[x,y],...]}]`、`ball: [[x,y],...]`、`bounces: [[x,y],...]` 字段

#### Scenario: 无球轨迹时球数据为空
- **WHEN** 球检测未启用或未检测到球
- **THEN** `scatter_plots.ball` 为空数组
