## 1. 后端数据模型与构建

- [x] 1.1 `visualization_schemas.py` 新增 dataclass：`HeatmapPlayerGrid`（id/label/color/grid）、`VisualHeatmaps`（visual_grid + players）、`ZoneStat`（zone/label/seconds/occupancy）、`PlayerZoneStats`（id/label/color/denominator_seconds/tracked_seconds/data_sufficiency/kitchen_control_rate/avg_distance_to_kitchen_line_m/zones/feedback）、`ZoneStats`（players）；`StructuredVisualizationData.heatmaps` 由 `VisualGrid | None` 改为 `VisualHeatmaps | None`，新增 `zone_stats: ZoneStats | None`
- [x] 1.2 `visualization_data_builder.py`：把 `_build_visual_grid` 重构为通用 `_build_grid(points)`，合并视图与每球员视图共用；`_build_heatmaps` 生成 `VisualHeatmaps`（合并 `visual_grid` + 每 label 独立 grid）
- [x] 1.3 `visualization_data_builder.py` 新增 `_display_label(label)`：解析 `Player_N`/`player_N` → "球员N"，失败回退原始 label；热力图与 zone stats 统一使用
- [x] 1.4 `_structured_to_dict` 扩展：输出 `heatmaps.players` 与顶层 `zone_stats`，保留既有 `heatmaps.visual_grid` 字段（纯增量，旧消费者不受影响）

## 2. 区域统计与核心指标

- [x] 2.1 `pickleball_performance_engine` 新增 `zone_for(x, y)` 辅助函数（kitchen/transition/backcourt 三段，基于 `standard_court()` 的 net_y/kitchen_depth 推导），界外点返回 None
- [x] 2.2 新增区域统计函数：按球员（points + 有效窗口）累计三区停留秒数（沿用 `kitchen_dwell` 的相邻帧时间差法，仅统计窗口内点）；无窗口时统计全部点
- [x] 2.3 计算每球员 `kitchen_control_rate`、`tracked_seconds`、`data_sufficiency`（`tracked_seconds/denominator_seconds < 0.3` 标记 insufficient）
- [x] 2.4 计算时间加权平均站位距厨房线距离：`d=min(|y−15|,|y−29|)` 英尺，×0.3048 转米，保留一位小数
- [x] 2.5 反馈生成：按 `avg_distance_to_kitchen_line_m` 与 `kitchen_line_reference_distance_m` 比较分档（≤ref → excellent；≤1.5×ref → good；否则 insufficient），文案含"参考基准"与 KCR 百分比，写入 `PlayerZoneStats.feedback`

## 3. 有效时间窗口解析

- [x] 3.1 新增 `resolve_effective_windows(...)`（pipeline/service 层）：tier ① job 有 `clip_start_ms`/`clip_end_ms` → 单一窗口；tier ② 有 `capture_take_id` → `list_timeline_events` 取 `rally_start`/`rally_end` 并集，排除 non-play/暂停/换边，畸形事件钳制或丢弃；tier ③ → 返回 None
- [x] 3.2 `analysis_pipeline.py::_run_visualization` 调用 `resolve_effective_windows`，将结果作为 `effective_windows` 传入 `builder.build_and_write(...)`（builder 保持纯函数，不感知 DB）

## 4. 配置

- [x] 4.1 `config.py` 新增 `kitchen_line_reference_distance_m: float = 0.9`（环境变量可覆盖），供反馈生成读取

## 5. 前端

- [x] 5.1 `src/types/report.ts` 扩展：`HeatmapPlayerGrid`、`VisualHeatmaps`（heatmaps 类型）、`ZoneStat`、`PlayerZoneStats`、`ZoneStats`，并接入 `StructuredVisualizationData`（`heatmaps` 新结构 + `zone_stats`）
- [x] 5.2 `StructuredHeatmap.tsx`：复刻散点图图例交互——球员 chip 切换图层（默认全开），每球员图层用自身 grid + `max_count` 归一化 + player.color 渲染；`players` 缺失时回退渲染合并 `visual_grid`
- [x] 5.3 新增 `StructuredZoneHeatmap.tsx`：SVG 三段横带球场底图 + 球员单选 chip + 区域占用条/KCR/平均距离/反馈文案；`data_sufficiency === "insufficient"` 显示"有效帧不足"警示；`zone_stats` 缺失时显示"暂无区域统计"
- [x] 5.4 `VisionPage.tsx::VisualizationArtifactGallery`：接入第三张区域空间热力图卡片（`zone_stats` 判定 `hasStructured`）

## 6. 测试与验证

- [x] 6.1 builder 单测：每球员 grid 独立且各自 `max_count`、label 为"球员N"、无点时空数组、`visual_grid` 保留
- [x] 6.2 zone stats 单测：三区 occupancy 归一、KCR 三分层（clip/时间线/总时长回退）、时间加权平均距离、`data_sufficiency` 阈值、反馈分档文案
- [x] 6.3 窗口解析单测：clip 单窗口、时间线并集排除 non-play、缺 `rally_end` 畸形输入钳制、无数据回退 None
- [x] 6.4 `/visualization-data` 契约测试：新字段存在、旧 JSON 兼容（无 `players`/`zone_stats` 时前端可降级）
- [x] 6.5 前端 `tsc` 类型检查与 `npm run build` 通过；手工验证热力图图例切换与区域卡片降级
