## Why

当前结构化热力图只输出一张 22×10 的"全部球员合并"网格，无法按球员（球员1/2/3/4）筛选查看各自的位置密度；同时缺少匹克球最核心的战术指标——网前区（Kitchen/NVZ）控制。教练和球员无法从可视化产物中判断"谁站在了哪里、谁掌控了网前"。

## What Changes

- **位置热力图支持按球员筛选**：`heatmaps` 从单一 `visual_grid` 扩展为同时包含合并网格与每球员独立网格（`players: [{id, label, color, grid}]`），前端 `StructuredHeatmap` 增加与散点图一致的图例切换交互，每球员网格使用各自 `max_count` 归一化配色。
- **新增"球员空间热力图"**：按全球场三段横带（Kitchen/网前区、Transition/过渡区、Backcourt/后场区）统计每球员的区域占用率，新增 `/visualization-data` 端点字段 `zone_stats`，并在前端作为第三张可视化卡片渲染。
- **新增 Kitchen Control Rate（KCR）与网前控制反馈**：KCR = 球员在厨房区停留的有效时间 / 比赛有效时间；分母按可用性分层——rally 片段 clip 时长 > 时间线 rally 净时间 > 总时长回退。同步输出平均站位距厨房线距离（英尺转米），用硬编码基准常数 `KITCHEN_LINE_REFERENCE_DISTANCE_M` 生成定性反馈文案（不足/良好/优秀）。
- **统一球员展示标签**：热力图与区域统计中的球员标签统一显示为"球员1/2/3/4"，不使用位置命名。

## Capabilities

### New Capabilities
- `player-zone-heatmap`: 定义球员空间热力图的数据输出、Kitchen Control Rate 计算口径、有效时间分母分层解析、网前控制反馈文案生成，以及前端渲染与交互契约。

### Modified Capabilities
- `structured-heatmap`: `heatmaps` 数据结构从单一 `visual_grid` 扩展为"合并网格 + 每球员网格"，前端 `StructuredHeatmap` 增加球员图例切换与每球员 `max_count` 归一化行为。

## Impact

- **后端**：`visualization_schemas.py`（新增 `PlayerZoneStats`/`ZoneStat` 等 dataclass）、`visualization_data_builder.py`（每球员网格 + zone stats 构建）、有效时间窗口解析（连接 AnalysisBatchItem clip 区间与 timeline rally 事件）、`config.py`（新增 `KITCHEN_LINE_REFERENCE_DISTANCE_M` 基准常数）、`/visualization-data` 端点序列化。
- **前端**：`StructuredHeatmap.tsx`（图例切换）、新增 `StructuredZoneHeatmap.tsx` 组件、`src/types/report.ts`（`zone_stats` 类型）、`VisionPage.tsx`（第三张可视化卡片与图例）。
- **测试**：后端 builder/zone stats 单测、`visualization-data` 契约测试；现有 `structured-heatmap` 相关测试需适配新字段。
- **兼容性**：`heatmaps.visual_grid` 字段保留，旧 job 无结构化 JSON 时按既有路径降级到 PNG。
