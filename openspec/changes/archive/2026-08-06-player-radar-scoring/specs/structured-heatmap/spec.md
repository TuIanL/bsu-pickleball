# structured-heatmap Specification

## Purpose

定义结构化热力图数据的后端输出、前端渲染、交互图例和历史数据缺失时的降级行为，确保数据契约与视觉展示可以独立验证。

## MODIFIED Requirements

### Requirement: 系统暴露结构化热力图数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点中返回热力图结构化数据，包含 22 行 × 10 列的合并网格计数、最大计数值、球场几何信息，以及每名球员独立网格与展示标签。每名球员的 `id` SHALL 为 canonical player ID（`Player_1`..`Player_4`），`label` SHALL 为 `P1`..`P4`（与视频叠加 HUD 对齐）。

#### Scenario: 分析完成后返回热力图数据

- **WHEN** 分析任务状态为 `completed`，且 `PositionVisualizer` 已生成 22×10 网格数据
- **THEN** `/visualization-data` 返回的 JSON 中包含 `heatmaps` 对象，含合并 `visual_grid`（`rows: 22`、`cols: 10`、`max_count` 及 `cells: [{row, col, count}]`）与 `players` 数组，每个球员元素有 `id`（canonical `Player_N`）、`label`（`P1`..`P4`）、`color` 及独立 `grid`（同样含 `rows/cols/max_count/cells`）

#### Scenario: 无可用坐标点时返回空网格

- **WHEN** 球员轨迹数据中无有效坐标点
- **THEN** `heatmaps.visual_grid.cells` 为空数组、`max_count` 为 0，`heatmaps.players` 为空数组

#### Scenario: 球员网格各自归一化计数

- **WHEN** 构建每名球员的独立网格
- **THEN** 每名球员的 `grid.max_count` SHALL 使用该球员自身的最大格计数，而非合并网格的全局峰值
