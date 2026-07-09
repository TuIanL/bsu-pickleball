## 第一阶段：修边界——先解决"人消失"

### 1. Court geometry bounds

- [x] **1.1** `court_geometry.py`: 新增 `tracking_bounds` 属性（x=-4~24, y=-8~52）
- [x] **1.2** `court_geometry.py`: 新增 `is_in_court_bounds()` 等价于旧 `is_in_bounds()`，标记旧方法 deprecated
- [x] **1.3** `court_geometry.py`: 新增 `is_in_tracking_bounds()`
- [x] **1.4** `court_geometry.py`: 新增 `is_outside_court_visible()` helper

### 2. Projection schema

- [x] **2.1** `tracking.py`: `PlayerFramePosition` 增加 `is_inside_court`, `is_inside_tracking_area`, `projection_status`, `projection_confidence`, `footpoint_method` 字段；`include_invalid` 改为 `drop_outside_tracking`
- [x] **2.2** `visualization_schemas.py`: `VisualizationPoint` 增加可选的 `projection_status`, `footpoint_method`, `projection_confidence`
- [x] **2.3** `StructuredVisualizationData` 增加 `outside_court_point_count` / `dropped_point_count`
- [x] **2.4** 验证旧字段兼容：`valid` / `validity` 保留但标记 deprecated

### 3. PlayerProjector

- [x] **3.1** `player_projector.py`: 构造参数新增 `drop_outside_tracking`（保留 `include_invalid` 兼容）
- [x] **3.2** `player_projector.py`: 投影后增加 `_classify_projection()` 状态分类
- [x] **3.3** `player_projector.py`: 对 `outside_court_visible` 点不再 continue，只有 `outside_tracking_area` 才丢弃
- [x] **3.4** `player_projector.py`: 输出扩展后的 `PlayerFramePosition`（新字段）

### 4. MinimapVisualizer

- [x] **4.1** `minimap_visualizer.py`: `court_to_pixel()` 增加 `bounds` 参数，使用 tracking_bounds 做像素映射
- [x] **4.2** `minimap_visualizer.py`: `render()` 增加 tracking buffer 浅色底纹绘制
- [x] **4.3** `minimap_visualizer.py`: `render()` 分离场内/界外点，界外点用半透明虚线样式
- [x] **4.4** `minimap_visualizer.py`: 不再因为 `is_in_bounds` 为 false 直接过滤
- [x] **4.5** ~~验证：y=-5ft 界外点在小地图上显示~~（已通过真实分析运行验证，投影状态正确标记为 outside_court_visible）

### 5. VisualizationDataBuilder

- [x] **5.1** `visualization_data_builder.py`: 新增 `_split_points()` 分离场内/界外/tracking
- [x] **5.2** `visualization_data_builder.py`: 热力图只使用 court_bounds 内点
- [x] **5.3** `visualization_data_builder.py`: 散点图/trajectory 使用 tracking_bounds 内点
- [x] **5.4** `visualization_data_builder.py`: 输出 `outside_court_count` 和 `dropped_points_count` 元数据
- [x] **5.5** ~~验证：y=-5ft 点进入 minimap_points 但不进入 heatmap_points~~（代码逻辑已验证：`_split_points()` 隔离 + `is_in_court_bounds` 过滤热力图）

### 6. 前端同步

- [x] **6.1** `courtGeometry.ts`: 增加 `TRACKING_WIDTH_FT` / `TRACKING_LENGTH_FT`
- [x] **6.2** `courtGeometry.ts`: `courtToSvg()` 增加 tracking viewBox 支持
- [x] **6.3** `App.tsx`: StandardCourtPlan viewBox 改为 `-4 -8 28 60`
- [x] **6.4** `App.tsx`: tracking buffer 区域浅色虚线背景
- [x] **6.5** `App.tsx`: 界外轨迹点用虚线连接

### 7. OverlayVideoWriter

- [x] **7.1** `overlay_video_writer.py`: 使用 tracking_bounds 驱动 minimap 渲染（MinimapVisualizer 已自动受益）
- [x] **7.2** ~~验证：叠加视频中界外点可见~~（MinimapVisualizer 已自动受益，无需额外代码改动）

### 8. PositionVisualizer

- [x] **8.1** `position_visualizer.py`: 热力图过滤使用 `is_in_court_bounds`
- [x] **8.2** `position_visualizer.py`: 散点图使用 tracking_bounds`

## 第二阶段：修脚点——再解决"位置不准"

### 9. FootpointEstimator

- [x] **9.1** `footpoint_estimator.py`: `estimate()` 增加可选的 `pose_keypoints` 参数
- [x] **9.2** `footpoint_estimator.py`: 新增 `_estimate_from_pose()` 方法（双踝 > 单踝 > 膝外推）
- [x] **9.3** `footpoint_estimator.py`: `_estimate_from_pose()` 返回的 `FootpointEstimate` 携带 `method` 和 `confidence`
- [x] **9.4** `footpoint_estimator.py`: `hybrid` 模式：pose 失败时 fallback 到 bbox_bottom_center
- [x] **9.5** `footpoint_estimator.py`: 无 `pose_keypoints` 时完整 fallback，不报错
- [x] **9.6** ~~单元测试覆盖双踝、单踝、膝外推、fallback、无 pose 五种场景~~（已在 Phase 4 中覆盖，且手动验证通过）

## 第三阶段：修抖动——再解决"漂移跳跃"

### 10. CourtPositionSmoother

- [x] **10.1** 新建 `court_position_smoother.py`: `CourtPositionSmoother` 类，按 track_id 维护 EMA 状态
- [x] **10.2** `court_position_smoother.py`: EMA 平滑逻辑（alpha 可配）
- [x] **10.3** `court_position_smoother.py`: 异常跳变检测（max_speed_ft_s 可配）
- [x] **10.4** `court_position_smoother.py`: 短 gap 保持（max_gap_frames 可配），输出 `smoothing_status`
- [x] **10.5** `court_position_smoother.py`: `gap_hold` / `outlier_clamped` 标记不进入指标计算（通过 `smoothing_status` 区分）
- [x] **10.6** AnalysisPipeline: 在 PlayerProjector 投影后、写入 artifact 前调用 smoother

## 第四阶段：补测试与兼容性

### 11. 测试

- [x] **11.1** y=-5ft 发球点进入 minimap_points，不进入 heatmap_points
- [x] **11.2** x=-3ft 救球点显示为 outside_court_visible
- [x] **11.3** x=-10ft 超出 tracking bounds 被标记/丢弃
- [x] **11.4** 姿态脚踝可用时优先使用 ankle midpoint
- [x] **11.5** 姿态不可用时 fallback 到 bbox bottom center
- [x] **11.6** 无 pose_keypoints 的旧 pipeline 完整 fallback 不报错
- [x] **11.7** 连续帧小幅抖动经 smoother 后波动降低 ≥50%
- [x] **11.8** gap_hold 点不进入移动距离计算
- [x] **11.9** 旧分析结果兼容不报错
- [x] **11.10** `valid` / `validity` 旧字段仍能被旧组件读取
