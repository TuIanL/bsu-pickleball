# player-zone-heatmap Specification

## Purpose

定义球员空间热力图（区域占用）数据的后端输出、Kitchen Control Rate 计算口径、比赛有效时间分母分层解析、网前控制反馈文案生成，以及前端渲染与交互契约。

## MODIFIED Requirements

### Requirement: 系统暴露球员空间热力图（区域占用）数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点返回 `zone_stats` 对象，包含每名球员在三个球场区域（kitchen/transition/backcourt）的占用统计、Kitchen Control Rate、平均站位距厨房线距离、数据充分性与反馈文案。每名球员的 `id` SHALL 为 canonical player ID（`Player_1`..`Player_4`），`label` SHALL 为 `P1`..`P4`（与视频叠加 HUD 对齐）。

#### Scenario: 分析完成后返回区域统计

- **WHEN** 分析任务状态为 `completed`，且球员轨迹 artifact 存在
- **THEN** `zone_stats.players` 数组包含每名球员，每项含 `id`（canonical `Player_N`）、`label`（`P1`..`P4`）、`color`、`denominator_seconds`、`tracked_seconds`、`data_sufficiency`、`kitchen_control_rate`、`avg_distance_to_kitchen_line_m` 及 `zones: [{zone, label, seconds, occupancy}]`

#### Scenario: 无坐标点时返回空数组

- **WHEN** 球员轨迹数据中无有效坐标点
- **THEN** `zone_stats.players` 为空数组

#### Scenario: 三分区占用率之和归一

- **WHEN** 计算某球员的区域占用率
- **THEN** kitchen/transition/backcourt 三区的 `seconds` 之和不超过 `denominator_seconds`，且各 `occupancy` 在 [0,1] 区间
