## 1. Config 与模块骨架

- [x] 1.1 新建 `backend/app/vision/player_tracking_engine/view_tracking_session.py`：定义 `ViewTrackingSessionConfig` dataclass（fps / frame_stride / frame_width / frame_height / effective_player_count / match_context / group_profile / 以及从 settings 解析的 tracking、identity、lock、selector 全部数值字段，以 `_run_tracking` 1753-1860 行推导块为逐字段核对清单）
- [x] 1.2 定义 `ViewFrameResult` dataclass：`frame_index` / `timestamp` / `frame_detections` / `frame_positions` / `render_raw_by_track` / `player_motion_pixels`
- [x] 1.3 把 `_run_tracking` 里 settings→config 推导抽为 `build_view_tracking_config(settings, match_context, *, fps, frame_stride, frame_width, frame_height)` 纯函数，逐字段等价迁移（含 `position_smoother.max_gap_frames = frames_for_seconds(10/30, fps)`）

## 2. ViewTrackingSession 实现（状态容器 + step 算法）

- [x] 2.1 `ViewTrackingSession.__init__` 接受**已解析** components（detector / tracker / duplicate_suppressor / footpoint_estimator / projector / position_smoother / selector / lock_manager / identity_manager / roi_artifact / config），不在内部无条件重建 tracker / footpoint / projector
- [x] 2.2 实现 `step(frame, *, frame_index, timestamp, guidance=())`：检测 → `filter_detections_to_roi`（ROI artifact 构造时注入）→ `tracker.update` → `duplicate_suppressor.filter` → 脚点 → 投影 → 平滑 → `primary_player_selector.select` → `player_lock_manager.update` → `eligible = lock | suggested`（语义不变）→ `_tracks_to_frame_detections` → `identity_manager.update` → 渲染观测构建 → 帧检测 player_id 标注
- [x] 2.3 session 累积 `roi_filtered_detection_count` / `full_frame_fallback_count`（不累积 `processed_frame_count`——该计数由 pipeline 在 court-view gate 前递增，见 4.4）
- [x] 2.4 迁移渲染生命周期逻辑并**保持顺序不变量**：identity_manager.update → 构建本帧 render observation（使用当前 identity_epoch）→ 读取 identity/lock diagnostics → 若 reset 则 `render_identity_epoch_by_player += 1`（render observation emission 必须在同帧 epoch increment 之前）
- [x] 2.5 累积 `raw_detections` / `tracks` / `positions` / `overlay_frames` / `render_observations` / `render_events` / `player_multitarget_detections`；`selection_diagnostics` 用 `extend` 累积；**`lock_diagnostics`** 用 `extend` 累积；**`latest_selection_training_samples`** 用 `=` 最新快照（非累计列表）；`player_motion_pixels` 由 session 从帧检测质心计算并返回

## 3. 工厂 + 依赖注入保留

- [x] 3.1 新增 `build_view_tracking_session(...)` 工厂：settings→config + 解析/构造 components，**保留 AnalysisPipeline 注入语义**（`tracker = self.tracker or MultiObjectTracker(...)`、`footpoint_estimator`、`projector` 注入优先）
- [x] 3.2 session 提供窄接口供结束阶段，不裸露内部 manager：`snapshot() -> ViewTrackingSessionOutputs`（累积数据 + selector mode / fallback reason）、`build_player_trajectory_artifact(...)`、`projected_metric_tracks()`

## 4. detect_regions 可选契约（显式 unsupported）

- [x] 4.1 定义 `RegionDetectionUnsupported(RuntimeError)`；`PersonDetector` 增加 `detect_regions(frame, regions, confidence_override=None)` 抛 `RegionDetectionUnsupported`（不用 `[]` 静默表示不支持），并提供 `supports_region_detection = False`
- [x] 4.2 `EmptyPersonDetector` 增加同名方法返回 `[]`（其语义 = 永无检测）
- [x] 4.3 确认 session 主路径（guidance=()）永不调用 `detect_regions`

## 5. 改造 _run_tracking 委托

- [x] 5.1 `_run_tracking` 用 `build_view_tracking_session(...)` 构造 session（传入共享 detector、注入的 tracker/footpoint/projector、roi_artifact、config），移除原 tracker/suppressor/identity/lock/selector/smoother 的构造逻辑
- [x] 5.2 逐帧循环改为：court-view 门控（保留在 pipeline）→ **`processed_frame_count += 1`（保持 gate 前递增顺序，见 design D1b）** → gated 帧 `continue` → `result = session.step(frame, frame_index=..., timestamp=...)` → 用 `result` 驱动 debug writers / 球检测（player_motion_pixels）/ 姿态估计（frame_detections）/ debug overlay
- [x] 5.3 结束阶段通过 session 窄接口（snapshot / build_player_trajectory_artifact / projected_metric_tracks）组装：`TrackingResult` / `player_trajectories` / `player_metric_tracks` / `PlayerSelectionArtifact` / court-view ROI artifact（消费 ROI 计数）/ 渲染轨迹；**`lock_diagnostics` 原样参与 `player_trajectories.diagnostics` 合并排序**
- [x] 5.4 迁移 `_detect_frame` / `_tracks_to_frame_detections` 到 session 内部；确认 `position_smoother` / 相关实例属性不再被 pipeline 引用

## 6. 测试与回归

- [x] 6.1 新增 `ViewTrackingSession` 单元测试：默认 `guidance=()` 逐帧 step 返回 `ViewFrameResult`；双实例 tracker/lock/identity 状态隔离；共享同一 detector 实例可正常 step；`detect_regions` unsupported 显式抛 `RegionDetectionUnsupported`（`EmptyPersonDetector` 返回 `[]`）
- [x] 6.2 新增 DI 保留测试：注入自定义 `tracker` / `footpoint_estimator` / `projector` 经 `build_view_tracking_session` 后仍被使用
- [x] 6.3 新增 config 构造测试：`build_view_tracking_config` 关键字段（含 frame_width / frame_height）与 settings / match_context 一致
- [x] 6.4 **强制 synthetic differential test**：固定 synthetic frames + scripted/mock `PersonDetector` + 固定 homography + 固定 config，重构前后两路径逐项对比（raw detections / frame detections / positions / render observations / render events / player trajectory / metric tracks / ROI counters），须逐项一致
- [x] 6.5 运行现有单摄 tracking 相关测试套件全绿（行为保护 regression = 0）
- [x] 6.6 运行相关多视角测试套件（`test_multiview_*`）确认无回归
- [ ] 6.7 （可选）real-video golden smoke：真实 fixture 视频产物冒烟，不维护全量 golden

## 7. 边界确认

- [x] 7.1 确认不改动 eligibility 语义（`lock | suggested` 保持现状）、不新增 guided detection 逻辑
- [x] 7.2 确认不触碰 `GlobalTrackFilter` / `CrossViewPlayerAssociator` / fusion / orchestration / artifact schema / Executor / Composer、不改动已归档 P0 文档
