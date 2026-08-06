## Context

当前结构化可视化数据 `StructuredVisualizationData`（由 `PositionVisualizationDataBuilder` 构建，经 `GET /api/analysis/jobs/{job_id}/visualization-data` 暴露）中：

- `heatmaps.visual_grid`：一张 22×10 的"全部球员合并"网格，无法按球员查看。
- `scatter_plots.players[]`：已按球员 label 分组，前端 `StructuredScatterPlot` 已有按球员切换图例的交互——这是我们要复刻的模式。
- `player_points` 每个点携带 `label`（player_id），来源是 `players_trajectory` artifact。

匹克球区域与比赛时间的基础设施也已存在：

- `court_geometry.py`：`net_y_ft=22`、`kitchen_depth_ft=7`、`is_in_kitchen()`、`kitchen_zones`（y∈[15,22]∪[22,29]）。
- `pickleball_performance_engine/zone_metrics.py`：`kitchen_dwell()` 已按相邻帧时间差累计厨房区停留秒数，`PerformanceMetrics.kitchen_dwell` 已进 pipeline 结果。
- 双摄/录制侧有比赛时间信息：`AnalysisBatchItem` 的 `snapshot_start_ms/end_ms`（= rally 片段 clip 区间）、`timeline_events`（`rally_start/rally_end`、`non_play_start/non_play_end` 等）、`list_timeline_events(db, field_session_id, capture_take_id=...)`。

缺口：热力图没有按球员拆分；缺少"区域占用 + Kitchen Control Rate + 网前控制反馈"这组战术指标；缺少"比赛净时间"口径的分母解析。

## Goals / Non-Goals

**Goals:**

- `heatmaps` 扩展为"合并网格 + 每球员网格"，前端 `StructuredHeatmap` 支持球员图例切换（默认全开，每球员用各自 `max_count` 归一化）。
- 新增 `zone_stats` 数据：每球员三段区域占用率、Kitchen Control Rate（KCR）、平均站位距厨房线距离、数据充分性标记、反馈文案。
- 分母"比赛有效时间"按可用性分层：① rally 片段 clip 时长 → ② 时间线 rally 净时间 → ③ 总时长回退。
- 统一球员展示标签"球员1/2/3/4"。
- 向后兼容：`visual_grid` 字段保留；旧 job 无结构化 JSON 时按既有路径降级到 PNG。

**Non-Goals:**

- 不做 rally 检测/球判定：只消费已有的 clip 区间与时间线事件，不自行切分回合。
- 不做逐拍/逐分统计、不做近/远半场分区的六段区域。
- 不改动 `structured-scatter-plot`。
- 不引入"同水平选手"规范数据库：仅使用硬编码基准常数 `KITCHEN_LINE_REFERENCE_DISTANCE_M`，反馈文案明确标注为"参考基准"。

## Decisions

### D1：热力图数据结构——合并网格 + 每球员网格

```jsonc
"heatmaps": {
  "visual_grid": { "rows": 22, "cols": 10, "max_count": 120, "cells": [...] },   // 保留，合并视图
  "players": [
    { "id": "0", "label": "球员1", "color": "#22C55E",
      "grid": { "rows": 22, "cols": 10, "max_count": 45, "cells": [...] } },
    // ... 球员2/3/4
  ]
}
```

- 把 `_build_visual_grid` 重构为通用 `_build_grid(points)`：合并视图传全部界内点，每球员视图传该 label 的点。
- 颜色复用散点图的 `PLAYER_HEX_COLORS`（`visualization_data_builder.py`），保证图例配色跨图一致。
- **球员展示标签**：新增 `_display_label(label)`，从 `Player_N` / `player_N` 解析出数字 N 映射为"球员N"；解析失败时回退原始 label。散点图与热力图共用。
- 选择合并视图保留而非删除：`visual_grid` 是既有契约，且"全部球员"心智模型仍有价值。

### D2：区域划分——全球场三段横带

基于几何常量推导（`net_y_ft=22`、`kitchen_depth_ft=7`、`length_ft=44`），不写魔法数：

| 区域 | label | y 范围（英尺） |
|---|---|---|
| Kitchen / 网前区 | `kitchen` | [15, 29]（两个 NVZ + 网） |
| Transition / 过渡区 | `transition` | [7, 15] ∪ [29, 37] |
| Backcourt / 后场区 | `backcourt` | [0, 7] ∪ [37, 44] |

**备选被否**：近/远半场各三段的六段方案。双打换边频繁，同一球员数据会在两个半场间来回跳，分段统计很碎；而 KCR 关心的就是"有没有站到网前 7ft"，NVZ 两侧语义相同。全球场三段与用户的三横条心智模型一致。

实现：新增 `zone_for(x, y)` 辅助函数（放 `pickleball_performance_engine`，复用 `standard_court()`），界外点（超出 [0,44]）不计入任何区域占用。

### D3：比赛有效时间（分母）解析——三层优先

`PositionVisualizationDataBuilder` 保持纯函数（只吃坐标点），新增可选入参 `effective_windows: list[tuple[float, float]] | None`（单位秒，半开区间）。窗口解析放在 pipeline 层，因为它需要 DB 与 job 上下文：

1. **① rally 片段 job**：job 携带 `requested_clip` / `clip_start_ms`/`clip_end_ms`（来自 `AnalysisBatchItem.snapshot_*`）→ 单一窗口 `[clip_start, clip_end)`。
2. **② 双摄整段视频 + 时间线事件**：job metadata 有 `capture_take_id` → `list_timeline_events(db, field_session_id, capture_take_id)` → 取 `rally_start→rally_end` 窗口求并集；`non_play_start/non_play_end`、timeout、side_change 区间不计入。畸形事件（缺 `rally_end`）钳制到视频末尾或丢弃。
3. **③ 无任何比赛数据**（上传裸视频）→ `None`，回退"该球员轨迹首帧→末帧"的总时长。

**计算规则**（每球员，在 `builder.build` 内）：
- 有窗口时：只统计时间戳落在某窗口内的点；无窗口时统计全部点。
- 区域占用秒数：沿用 `kitchen_dwell` 的相邻帧时间差累计法（前一帧在窗口内且在区内 → 累加 Δt）。
- **分母**：有窗口时 = Σ 窗口长度；无窗口时 = 该球员 `[first_ts, last_ts]`。
- `tracked_seconds`（窗口内实际被跟踪到的时长）记入数据，供充分性判定。

选择把窗口解析放在 pipeline 层而非 builder：窗口需要查时间线事件（DB），builder 保持无副作用，便于单测。

### D4：区域统计与核心指标（每球员）

`zone_stats.players[]` 每项：

```jsonc
{
  "id": "0", "label": "球员1", "color": "#22C55E",
  "denominator_seconds": 300,          // 分母：Σ窗口长度 或 总时长
  "tracked_seconds": 285,              // 窗口内实际跟踪到的时间
  "data_sufficiency": "sufficient",    // "sufficient" | "insufficient"
  "kitchen_control_rate": 0.68,        // kitchen_seconds / denominator_seconds
  "avg_distance_to_kitchen_line_m": 1.8,
  "zones": [
    { "zone": "kitchen",    "label": "网前区", "seconds": 204, "occupancy": 0.68 },
    { "zone": "transition", "label": "过渡区", "seconds": 84,  "occupancy": 0.28 },
    { "zone": "backcourt",  "label": "后场区", "seconds": 12,  "occupancy": 0.04 }
  ],
  "feedback": { "level": "insufficient", "summary": "平均站位距厨房线 1.8m，高于参考基准 0.9m，网前控制不足（KCR 68%）。" }
}
```

- **占用率** = 该区累计秒数 / 分母；**KCR** = 网前区秒数 / 分母。
- **平均站位距厨房线**：时间加权平均 `Σ(d(p)·Δt)/ΣΔt`，`d(p)=min(|y−15|, |y−29|)` 英尺，×0.3048 转米。选时间加权是为与占用率口径一致（占用率是时间口径）。
- **数据充分性**：`tracked_seconds / denominator_seconds < 0.3` → `insufficient`，前端显示"有效帧不足"警告而非硬给百分比。这是 MVP 阶段对"窗口内某球员未被跟踪"缺帧风险的诚实处理。

### D5：反馈文案 + 基准常数

- `config.py` 新增 `kitchen_line_reference_distance_m: float = 0.9`，可用环境变量覆盖。**这是硬编码参考基准（用户选型 A）**。
- 反馈等级按 `avg_distance_to_kitchen_line_m` 与基准比较：
  - `≤ ref` → `excellent`（"网前控制优秀"）
  - `≤ 1.5×ref` → `good`（"网前控制良好"）
  - `>` → `insufficient`（"网前控制不足"）
- 文案后端生成（放入 `zone_stats.players[].feedback`）：不足时形如 `"平均站位距厨房线 {:.1f}m，高于参考基准 {:.1f}m，网前控制不足（KCR {:.0f}%）。"` 明确写"参考基准"而非"同水平选手"，避免把常数伪装成真实规范数据。
- 选择后端生成而非前端：文案与 zh-CN 拷贝模式一致（`labels_for`），且可被后端测试覆盖。

### D6：前端——`StructuredHeatmap` 图例切换

复刻 `StructuredScatterPlot` 的交互：球员 chip 按钮切换图层显示/隐藏，**默认全开**（与散点图一致，符合用户决策 #3）。

- 每球员图层用其**各自**的 `grid.max_count` 归一化配色（决策 #3），颜色用 `player.color`，透明度叠加。
- 想只看某球员时点掉其它 chip 即可隔离单球员——满足原始诉求"筛选不同球员的热力图样式，而不是把四人的热力混在一起"。
- 兼容：`heatmaps.players` 缺失（旧 JSON）时回退渲染当前合并 `visual_grid`。

### D7：前端——新增 `StructuredZoneHeatmap` 卡片

- 作为第三张可视化卡片放进 `VisualizationArtifactGallery` 的 `md:grid-cols-2` 网格（自然换行）。
- 渲染三段横带球场底图 + 每段按占用率着色；顶部球员 chip（单选，默认选中第一个或"全部"合并视图）。
- 卡片下半部：选中球员的区域占用条（Kitchen/Transition/Backcourt 百分比）、KCR 大字、平均距厨房线距离、反馈文案。
- `data_sufficiency === "insufficient"` 时显示"有效帧不足"警示。
- 数据来自 `structuredViz.zone_stats`，无数据时整卡降级为"暂无区域统计"。

### D8：序列化与兼容

- `_structured_to_dict` 增加 `heatmaps.players` 与顶层 `zone_stats`；不删除既有字段。前端旧代码忽略未知字段，后端旧 JSON 前端按缺失回退。
- 结构化 JSON 是文件 artifact，无 DB 迁移。

## Risks / Trade-offs

- **[窗口内球员缺帧 → 占用率偏低]** → `tracked_seconds` + `data_sufficiency` 阈值标记，前端显示"有效帧不足"。
- **[时间线事件不完整（缺 rally_end / 事件顺序异常）]** → 窗口解析做钳制与丢弃，单测覆盖畸形输入。
- **[②需要 DB 访问，与纯 builder 冲突]** → 窗口解析在 pipeline/service 层完成，把 `effective_windows` 作为纯入参传给 builder；builder 与解析各自可测。
- **[每球员各自 max_count 会让去得少的球员网格显得"很热"（相对饱和）]** → 这是有意的相对语义，与散点图一致；不引入绝对色阶（MVP 不展示图例刻度）。
- **["参考基准 0.9m"是硬编码，非真实规范数据]** → 文案强制标注"参考基准"；阈值（ref、1.5×ref、0.3 充分性）全部进 config 可调。

## Migration Plan

1. 后端：schema + builder + zone stats + config 常数 + `_structured_to_dict` 扩展；pipeline 可视化阶段解析 `effective_windows` 后传入 builder。
2. 前端：`report.ts` 类型扩展 → `StructuredHeatmap` 图例 → 新 `StructuredZoneHeatmap` → `VisionPage` 第三卡。
3. 发布顺序：先后端（新增字段，旧前端不受影响）→ 再前端（对旧 JSON 优雅降级）。
4. 回滚：后端字段纯增量，前端对新字段缺省降级，无破坏性迁移。

## Open Questions

- `data_sufficiency` 阈值 0.3、反馈分段阈值 1.5×ref：先取经验值，后续按真实数据标定。
- 区域占用条是否也展示"全部球员"的对比视图（合并占用）？MVP 先做单球员视图，合并对比留待后续。
