# player-identity-display Specification

## Purpose

用户可见输出（视频检测叠加、球场 minimap、轨迹详情页、报告）只呈现 canonical player ID（`1`–`4`），原始 tracker `track_id` 不得出现在任何面向用户的 API 字段或文案中。

## ADDED Requirements

### Requirement: 结构化可视化产物使用 canonical player ID 与展示标签

后端 `/visualization-data` 中的 `heatmaps.players`、`scatter_plots.players`、`zone_stats.players`、`player_trajectories` 球员标识字段 SHALL 使用 canonical player ID（`Player_1`..`Player_4`），展示标签 SHALL 为 `P1`..`P4`；SHALL NOT 使用排序索引（如 `"0"`）或 `"球员N"` 形式作为标识或标签。

#### Scenario: 热力图球员 id 为 canonical

- **WHEN** 分析完成生成 heatmaps 结构化数据
- **THEN** `heatmaps.players[].id` SHALL 为 canonical player ID（如 `Player_2`）
- **AND** `heatmaps.players[].label` SHALL 为 `P2`（或等价 canonical 形式）

#### Scenario: zone_stats 球员 id 为 canonical

- **WHEN** 分析完成生成 zone_stats 结构化数据
- **THEN** `zone_stats.players[].id` SHALL 为 canonical player ID（如 `Player_1`）
- **AND** `zone_stats.players[].label` SHALL 为 `P1`（或等价 canonical 形式）

#### Scenario: 散点图球员 id 为 canonical

- **WHEN** 分析完成生成 scatter_plots 结构化数据
- **THEN** `scatter_plots.players[].id` SHALL 为 canonical player ID（如 `Player_3`）

#### Scenario: 非 canonical 标签不参与对齐声明

- **WHEN** 某球员点 label 无法解析为 `Player_N` 形式
- **THEN** 该 id 原样保留且颜色回退索引分配
- **AND** 该产物不声称与 canonical P1-P4 对齐
