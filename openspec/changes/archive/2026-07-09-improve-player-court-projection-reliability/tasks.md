## 1. Phase 0：标定质量诊断（前置 —— 标定错了后面全错）

- [x] 1.1 新建 `calibration_diagnostics.py`：`CalibrationDiagnostics` 类，接受 homography + 标定控制点 + frame_shape，计算诊断指标
- [x] 1.2 `compute_corner_reprojection_errors()`：对每个标定角点计算 `image_point` 与 `court_to_image(court_point, inv_H)` 的像素偏差
- [x] 1.3 `check_derived_points()`：生成派生球场线点（网线两端、厨房线两端、中线-厨房线交点）并投影回图像，验证所有点落在图像范围内且相对空间关系合理
- [x] 1.4 `compute_aspect_ratio_error()`：计算投影后球场宽高比与 20/44 的偏差百分比
- [x] 1.5 `check_baseline_direction()`：验证近端底线投影到画面下部、远端底线投影到画面上部（注意：此检查依赖 y=0 为近端、y=44 为远端的约定）
- [x] 1.6 `compute_homography_condition_number()`：使用 `np.linalg.cond()` 计算矩阵条件数
- [x] 1.7 `assess_quality()`：综合以上指标输出 `calibration_quality`（good / suspect / bad）和 warnings 列表
- [x] 1.8 在 `AnalysisPipeline._run_calibration()` 完成后调用 `CalibrationDiagnostics`，写入 `calibration_diagnostics.json` artifact
- [x] 1.9 将 `calibration_diagnostics_url` 加入 `AnalysisPipelineResult.artifacts`
- [x] 1.10 验证：模拟 near/far 方向颠倒的标定，确认诊断输出 `calibration_quality = "suspect"` 和 `"Near/far baseline may be swapped"` 警告

## 2. Phase 1：投影诊断 JSONL

- [x] 2.1 新建 `projection_debug_writer.py`：`ProjectionDebugWriter` 类，接受输出路径，管理 line-buffered 文件写入
- [x] 2.2 JSONL 每行包含：`frame_index`, `track_id`, `bbox`, `image_footpoint`, `footpoint_method`, `footpoint_confidence`, `court_position_raw`, `court_position_smoothed`, `projection_status`, `minimap_pixel`, `homography`, `calibration_quality`
- [x] 2.3 近端裁切检测标记：`bbox.y2 > frame_height * near_clip_threshold` 时增加 `near_frame_bottom: true` + `bbox_clip_suspected: true` 字段
- [x] 2.4 `write_frame()` 使用 line-buffered 模式打开文件，每 `flush_interval_frames`（默认 30）帧执行 `file.flush()`，异常/结束时强制 flush
- [x] 2.5 新增 `enable_projection_debug_jsonl` 配置项（默认 `False`），控制 JSONL 生成
- [x] 2.6 `ProjectionDebugWriter.write_frame()` 在每帧投影完成后追加一行，不做全量内存缓存
- [x] 2.7 在 `AnalysisPipeline` tracking 阶段集成 `ProjectionDebugWriter`
- [ ] 2.8 验证：生成一段测试视频的 JSONL，确认 line-buffered flush 行为正确（异常退出时丢失量 ≤ 30 帧）

## 3. Phase 2：脚点估计升级——近端裁切标记

- [x] 3.1 `footpoint_estimator.py`：`estimate()` 方法签名新增可选参数 `frame_shape: tuple[int, int] | None = None`（向后兼容）
- [x] 3.2 `footpoint_estimator.py`：新增 `_check_near_frame_bottom(bbox, frame_shape, threshold=0.94)` 方法，返回 `(near_frame_bottom: bool, bbox_clip_suspected: bool)`
- [x] 3.3 `footpoint_estimator.py`：`_estimate_from_bbox()` 在检测到 near_frame_bottom 时，FootpointEstimate 的 metadata 设置 `near_frame_bottom: true` + `bbox_clip_suspected: true`，confidence <= 0.35
- [x] 3.4 `footpoint_estimator.py`：正常 bbox fallback confidence 显式设为 0.7（之前未设默认值）
- [x] 3.5 `footpoint_estimator.py`：pose_ankle / knee_extrapolated 方法不受 near_frame_bottom 检测影响（即使 bbox 接近底部，只要 ankle 可用就优先 pose）
- [x] 3.6 新增配置项 `near_clip_threshold`，默认 0.94，可覆盖
- [x] 3.7 `player_projector.py`：`project()` 调用 `footpoint_estimator.estimate()` 时传入 `frame_shape`（从视频属性获取）
- [ ] 3.8 验证：构造近端裁切场景（bbox y2 = frame_height * 0.96, 无 ankle pose），确认输出 metadata 含 `near_frame_bottom: true, bbox_clip_suspected: true`，confidence <= 0.35
- [ ] 3.9 验证：有 ankle pose 时（即使 bbox y2 = frame_height * 0.96），优先用 `pose_ankle_midpoint`，不设 near_frame_bottom 标记

## 4. Phase 3：投影诊断叠加视频

- [x] 4.1 新增 `enable_projection_debug_overlay` 配置项（默认 `False`），独立于 JSONL 开关
- [x] 4.2 扩展 `OverlayVideoWriter` 或其子类 `ProjectionDebugOverlayWriter`，支持 debug 模式：在每帧绘制 bbox、脚点十字标记、投影坐标文本、method/status 文本
- [x] 4.3 `bbox_clip_suspected: true` 的球员 bbox 以黄色（而非绿色）绘制，method 文本附加 " ⚠ clip_suspected"
- [x] 4.4 Debug overlay 使用半透明叠加（alpha 0.5~0.7），球场四角编号标注可选
- [x] 4.5 在 `AnalysisPipeline` visualization 阶段集成 debug overlay 生成（独立于 `analysis_overlay.mp4`）
- [x] 4.6 验证：`enable_projection_debug_overlay=True` 且 `enable_projection_debug_jsonl=False` 时只生成 overlay 视频不生成 JSONL

## 5. Phase 4：前后端 SVG 坐标一致

- [x] 5.1 `courtGeometry.ts`：确认 `trackingToSvg()` 函数和 `TRACKING_VIEWBOX_WIDTH/HEIGHT` 常量存在
- [x] 5.2 `StructuredScatterPlot.tsx`：将 `courtToSvg(pt[0], pt[1])` 替换为 `trackingToSvg(pt[0], pt[1])`
- [x] 5.3 `App.tsx` StandardCourtPlan：确认 SVG viewBox 为 `-4 -8 28 60`，tracking buffer 底纹渲染正确
- [x] 5.4 `StructuredScatterPlot.tsx`：界外点（outside_court_visible）使用 `opacity={0.4}` 半透明样式
- [x] 5.5 验证：用同一组坐标数据（含 y=-5ft 发球点），确认前端 SVG 散点图和后端 overlay 小地图的球员相对位置一致

## 6. Phase 5：边界体系回归测试

- [ ] 6.1 回归测试：`y=-5ft` 发球点 → `projection_status = outside_court_visible` → 进入 minimap_points → 不进入 heatmap_points
- [ ] 6.2 回归测试：`x=-3ft` 救球点 → `projection_status = outside_court_visible` → 小地图半透明显示
- [ ] 6.3 回归测试：`x=-12ft` 异常点 → `projection_status = outside_tracking_area` → 小地图不显示
- [ ] 6.4 回归测试：姿态脚踝可用时 → `footpoint_method = pose_ankle_midpoint`
- [ ] 6.5 回归测试：gap_hold 点 → 不进入移动距离计算 → 不进入热力图统计
- [ ] 6.6 回归测试：旧分析结果兼容 → `valid`/`validity` 旧字段仍可读

## 7. Phase 6：端到端验证

- [ ] 7.1 对已知标定质量的视频运行完整 pipeline，检查 `calibration_diagnostics.json` 的 `calibration_quality` 和派生点校验结果
- [ ] 7.2 同时开启 `enable_projection_debug_jsonl` 和 `enable_projection_debug_overlay`，验证两个产物文件存在且内容一致
- [ ] 7.3 只开启 `enable_projection_debug_jsonl`（不开 overlay），确认 JSONL 正常生成、无 video writer 初始化
- [ ] 7.4 近端球员场景：确认 debug JSONL 中 near_frame_bottom 标记准确，overlay 中对应球员 bbox 为黄色
- [ ] 7.5 关闭全部 debug 开关 → pipeline 输出与修改前一致（回归验证）
- [ ] 7.6 无 frame_shape 信息的旧数据回放 → 不报错，footpoint 行为与旧版一致
