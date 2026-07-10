## Why

小地图（overlay 视频右上角 + 前端 SVG 球场图）中球员位置存在系统性错位——底线球员常被投影到厨房区、界外发球/救球点消失、前后端坐标显示不一致。根因不在 MinimapVisualizer 的绘制逻辑，而在上游坐标链路 `image_footpoint → homography → court_position → visualization point` 的精度不足。上一个 change（`fix-player-court-projection-and-minimap-bounds`）修复了「人消失」的边界问题，但坐标精度本身并未改善。此次 change 聚焦于提升投影准确性和可诊断性。

## What Changes

- **Phase 0：标定质量诊断（全新）** —— 对每次分析任务输出标定质量报告（角点 + 派生球场线点重投影误差、球场比例偏差、基线方向校验、homography 条件数），并在标定可疑时主动降级。标定是第一道门，标定错了后面全错，所以诊断前置
- **Phase 1：投影诊断 JSONL（全新）** —— 新增 `projection_debug.jsonl`（默认 line-buffered，每 N 帧 flush），逐帧记录脚点来源、投影坐标、分类状态，为逐帧排查提供结构化证据
- **Phase 2：脚点估计升级** —— `FootpointEstimator` 新增近端裁切感知：当 bbox 底边 `y2 > frame_height * 0.94` 且 fallback 到 bbox 方法时，标记 `near_frame_bottom: true` + `bbox_clip_suspected: true`，projection_confidence 上限降至 0.35（正常 bbox fallback 为 0.7）。pose_ankle 方法不受裁切检测影响
- **Phase 3：投影诊断叠加视频（全新）** —— 新增 `enable_projection_debug_overlay` 配置（独立于 JSONL），生成 `projection_debug_overlay.mp4`，在每帧绘制 bbox、脚点十字、投影坐标文本、method/status 标注
- **Phase 4：前后端坐标一致** —— 前端 `StructuredScatterPlot` / `StandardCourtPlan` SVG 统一使用 tracking viewBox，与后端 MinimapVisualizer 的 `court_to_pixel(bounds="tracking")` 对齐
- **Phase 5：边界体系回归测试** —— 基于已完成的 `court_bounds` / `tracking_bounds` 三层空间门控（上一 change 产物），新增自动化回归测试覆盖 inside/outside/tracking 的语义正确性
- **畸变校正 / PnP（本 change 不做，留作后续）** —— 先确保脚点和标定到位，最后才上相机模型

## Capabilities

### New Capabilities
- `projection-diagnostics`: 投影全链路诊断可视化（debug overlay 视频 + JSONL 诊断日志），逐帧暴露脚点来源、投影坐标、状态分类、回投误差
- `calibration-quality-diagnostics`: 标定质量自动诊断，输出角点重投影误差、比例偏差、基线方向、homography 条件数，并在可疑标定时发出降级警告
- `near-clip-footpoint-compensation`: 近端 bbox 裁切检测与脚点置信度降级，防止 bbox 底边被画面底部裁切时产生高置信度错误投影

### Modified Capabilities
- `player-tracking-engine`: FootpointEstimator 的 spec 要求从「bbox_bottom_center 为 MVP」升级为「hybrid 脚点估计 + 近端裁切感知」，增加 pose_ankle_midpoint / pose_ankle_single / knee_extrapolated / near_frame_bottom（bbox 底边接近画面底部时降级）等方法
- `visualization-reporting-outputs`: MinimapVisualizer 的渲染与 VisualizationDataBuilder 的数据分流需要增加 projection_status 感知，前端 SVG 需要支持 tracking viewBox

## Impact

- **后端修改**：`footpoint_estimator.py`（近端裁切检测 + 方法统计）、`player_projector.py`（诊断信息透传）、`homography.py`（标定质量评估）、`court_geometry.py`（不变，复用已有 tracking_bounds）、`minimap_visualizer.py`（不变，复用已有 bounds 参数）、`visualization_data_builder.py`（不变，复用已有 _split_points）、`overlay_video_writer.py`（新增 debug overlay 模式，由 `enable_projection_debug_overlay` 独立控制）、`position_visualizer.py`（不变）、新增 `projection_debug_writer.py`（由 `enable_projection_debug_jsonl` 控制）、新增 `calibration_diagnostics.py`
- **前端修改**：`courtGeometry.ts`（已有 trackingToSvg，确保 StructuredScatterPlot 使用）、`App.tsx`（StandardCourtPlan 已使用 tracking viewBox，验证一致性）
- **不影响**：热力图统计（继续只使用 court_bounds 内点）、移动距离/速度计算（继续排除 gap_hold/outlier_clamped 点）、YOLO/RTMPose 模型、AnalysisPipeline 主流程、ball tracking 链路
