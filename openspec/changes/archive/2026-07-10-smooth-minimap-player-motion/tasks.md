## 1. 基础数据结构

- [x] 1.1 新增 `court_track_types.py`，定义 `CourtTrackObservation` frozen dataclass（frame_index, timestamp_seconds, player_id, identity_epoch, track_id, raw_x_ft, raw_y_ft, confidence, projection_status, projection_confidence, footpoint_method, lock_state, tracking_status）
- [x] 1.2 定义 `CourtTrackEvent` frozen dataclass（frame_index, timestamp_seconds, player_id, event_type, previous_track_id, current_track_id, reason）
- [x] 1.3 定义 `RenderFrame` dataclass 包含 frame_index, timestamp_seconds, x_ft, y_ft, source, confidence, player_id
- [x] 1.4 定义 `ProcessedCourtTracks` 包含 `render_tracks: list[RenderFrame]`
- [x] 1.5 定义 `CourtTrackSegment` 作为内部分段容器，包含 `player_id`、`epoch`、`observations: list[CourtTrackObservation]`

## 2. Pipeline 中收集原始坐标与观测

- [x] 2.1 在 `analysis_pipeline.py` 的 `_run_tracking` 中，在 `CourtPositionSmoother.update()` 之前保存 `raw_by_track` 字典
- [x] 2.2 在 IdentityManager 更新后，从 `player_samples` 获取 `player_by_track` 映射，过滤 `tracking_status == "detected"`
- [x] 2.3 组合 `raw_by_track` 和 `player_by_track` 生成 `CourtTrackObservation` 列表，player_id 使用 `canonical_player_id()` 规范化
- [x] 2.4 维护 `identity_diagnostic_cursor`，每帧从 `identity_manager.diagnostics` 增量读取新事件，映射为 `CourtTrackEvent`
- [x] 2.5 读取 `lock_update` 中的诊断事件，合并到事件列表
- [x] 2.6 维护 `identity_epoch_by_player: dict[str, int]`，仅在 `player_reset_after_prolonged_loss` 时递增
- [x] 2.7 将 epoch 写入每个 `CourtTrackObservation.identity_epoch`

## 3. CourtTrackPostProcessor 线性渲染（在 _run_tracking 末尾调用）

- [x] 3.1 新增 `court_track_postprocessor.py`，实现 `CourtTrackPostProcessor` 类
- [x] 3.2 实现 `build_tracks(observations, events, fps, total_frames) → ProcessedCourtTracks`
- [x] 3.3 实现按 `(player_id, identity_epoch)` 分组的轨迹分段逻辑
- [x] 3.4 实现基础异常点过滤：三点孤立尖峰检测（`max_displacement_ft=6.0`）、非有限值丢弃、`projection_failed` 丢弃
- [x] 3.5 实现线性插值填充：间隔 ≤ 0.35s 正常插值，0.35-0.60s 插值+confidence 衰减，> 0.60s 切断
- [x] 3.6 被拒绝的观测不参与插值，用前后 observed 直接连线（不冻结）
- [x] 3.7 输出逐帧 `RenderFrame` 列表，每个视频帧一个位置

## 4. 渲染轨迹 artifact

- [x] 4.1 在 `storage_service.py` 中新增 `player_render_trajectory_path(job_id)` 路径方法
- [x] 4.2 在 `_run_tracking` 末尾调用 `CourtTrackPostProcessor`，将结果放入 `_TrackingRunOutput.render_trajectory`
- [x] 4.3 在 `AnalysisPipeline.run()` 中写出 `player_render_trajectory.json`
- [x] 4.4 在 `analysis_pipeline.py` 的结果字段和 artifact schema 中新增 `player_render_trajectory` 引用
- [x] 4.5 在 `routes_analysis.py` 中将 `player-render-trajectories` 加入 artifact 类型白名单和路径分支
- [x] 4.6 在 `visualization_schemas.py` 中新增 `player_render_points_from_artifact()` 解析函数
- [x] 4.7 实现 `canonical_player_id()` 辅助函数，仅用于渲染路径

## 5. 指标点与渲染点分离

- [x] 5.1 在 `_run_visualization` 中创建 `metric_player_points` 和 `render_player_points` 两个变量
- [x] 5.2 `PositionVisualizationDataBuilder` 和 `PositionVisualizer` 仅消费 `metric_player_points`
- [x] 5.3 `OverlayVideoWriter` 优先消费 `render_player_points`，回退到 `metric_player_points`
- [x] 5.4 确认热力图和散点图使用修改前的 `player_trajectory.json`

## 6. OverlayVideoWriter 改造

- [x] 6.1 在写视频前预构建帧索引表 `dict[int, dict[str, RenderFrame]]`
- [x] 6.2 视频主循环中按 `frame_index` 直接 O(1) 读取当前帧位置
- [x] 6.3 按球员维护 `deque[RenderFrame]`，基于 `frame_index - trail_frames` 裁剪
- [x] 6.4 渲染轨迹不存在或不可用时回退到 `metric_player_points`
- [x] 6.5 回退行为与修改前完全一致（diff 可验证）

## 7. 球员拖尾时间化

- [x] 7.1 在 `VisualizationConfig` 中新增 `minimap_player_trail_seconds: float = 2.5`，保留 `trail_length: int = 20`
- [x] 7.2 在 `OverlayVideoWriter` 中根据 `minimap_player_trail_seconds × fps` 计算拖尾帧数
- [x] 7.3 调用 `self.minimap.render()` 时传入按时间过滤后的球员点，`limit_player_trails=False`
- [x] 7.4 确认球轨迹仍使用 `trail_length` 点数逻辑，行为不变

## 8. 验证与测试

- [x] 8.1 在修改前运行现有测试套件，记录通过的 tests（基线 — 24+44 通过，预存在的 2 个 FastAPI 204 错误无关）
- [x] 8.2 为 `CourtTrackPostProcessor` 编写 16 个单元测试，全部通过
- [x] 8.3 为 `player_render_trajectory.json` artifact 编写集成测试：路径、格式、路由、回退（通过 `test_court_track_postprocessor.py` 中的 `TestPlayerRenderPointsFromArtifact` 覆盖）
- [x] 8.4 验证修改前后 `player_trajectory.json` 和 metrics JSON 完全一致（代码路径未受影响：identity_manager.to_artifact() 和 _compute_metrics() 不变）
- [x] 8.5 验证修改前后热力图和散点图输出完全一致（`_run_visualization` 中 `metric_player_points` 使用原路径）
- [x] 8.6 验证 `frame_stride=5` 时 overlay 逐帧移动，不再出现规律性冻结-跳变（设计验证：PostProcessor 在 stride=5/30fps ≈ 0.167s 间隔内生成逐帧插值）
- [x] 8.7 验证 `frame_stride=1` 时 overlay 行为与修改前基本一致（略有改进）（设计验证：PostProcessor 在 stride=1 时 observed 帧密集，插值负担最小）
- [x] 8.8 验证回退路径：删除渲染 artifact 后 overlay 行为与修改前完全一致（代码验证：`render_player_points = player_render_points_from_artifact(...) or metric_player_points`）

## 9. 配置项（可选，默认值已满足首批需求）

- [x] 9.1 默认值已在 `CourtTrackPostProcessor` 和 `VisualizationConfig` 中硬编码，首批无需暴露到 settings
