## Why

视频分析页需要新增"球员打分"能力：为每名球员在六维（发球 / 接发球 / 进攻能力 / 防守能力 / 敏捷 / 击球稳定性）上给出 10 分制（1 位小数）的雷达评分，并按 P1-P4 切换查看。这依赖球员身份与各分析产物之间的对齐。目前结构化可视化产物（热力图 / 散点图 / 区域统计 / 球员轨迹）用"排序索引重新编号"（`id="0".."3"`、`label="球员N"`）标识球员，与 canonical `Player_1`..`Player_4` 无法 join，导致评分无法可靠归属到正确的球员。该对齐必须解决，不能靠 mock 回避。

## What Changes

- **对齐修复（BREAKING 数据契约）**：`/visualization-data` 中 `heatmaps`、`scatter_plots`、`zone_stats`、`player_trajectories` 的球员 `id` 从排序索引改为 canonical `player_id`（`Player_1`..`Player_4`），`label` 统一为 `P1`..`P4`（与视频叠加 HUD 一致）。**颜色保持现有调色板不变**（按 canonical 序号显式分配，视觉零变化，从"巧合对齐"变为"显式对齐"）。
- **新增球员六维雷达评分面板**：视频分析页底部整行新增面板，左侧六轴 SVG 雷达图，右侧 P1-P4 球员切换 tab；评分 10 分制带 1 位小数。分数当前以 mock 数据填充，但数据模型键为 canonical `player_id`，为后续接入真实算法预留、不改键。
- **自适应球员列表**：面板按分析结果中实际检测到的 canonical 球员显示（双打 4 人、单打 2 人），demo / 无结果时兜底 4 人。

## Capabilities

### New Capabilities
- `player-scoring`: 球员六维雷达评分面板（发球 / 接发球 / 进攻能力 / 防守能力 / 敏捷 / 击球稳定性，10 分制 1 位小数），P1-P4 自适应切换，数据模型键为 canonical `player_id`。

### Modified Capabilities
- `player-identity-display`: 扩展 canonical player ID 唯一性要求到结构化可视化产物——`heatmaps` / `scatter_plots` / `zone_stats` / `player_trajectories` 的球员 `id` MUST 为 canonical `Player_N`，`label` MUST 为 `P1`..`P4`。
- `structured-heatmap`: 热力图 `players[].label` 从 `"球员N"` 改为 canonical `P1`..`P4`。
- `player-zone-heatmap`: `zone_stats.players` 的 `id` / `label` 从排序索引 / `"球员N"` 改为 canonical `Player_N` / `P1`..`P4`。
- `structured-scatter-plot`: 散点图 `players[].id` / `label` 改为 canonical。

## Impact

- **后端**：`zone_stats.py`、`visualization_data_builder.py`（canonicalize id + label，颜色显式按 canonical 序号分配）、相关后端测试。
- **前端**：`src/types/report.ts`（新增 `PlayerScore` 等类型）、新组件 `src/components/platform/RadarChart.tsx`、`src/components/platform/PlayerScoringPanel.tsx`、`src/pages/VisionPage.tsx`（接入面板）、mock 数据、相关前端测试。
- **数据契约**：`/visualization-data` 中结构化可视化产物的球员 `id` / `label` 变更（BREAKING）。现有 `StructuredZoneHeatmap` / `StructuredHeatmap` / `StructuredScatterPlot` 读 `id/label/color` 为通用字段，标签自动变为 `P1`，无需前端改动。
- **颜色**：不变（保持现有调色板）。
