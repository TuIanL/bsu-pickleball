# view-tracking-session Specification

## Purpose
可复用的单视角逐帧 tracking session —— 从 `AnalysisPipeline._run_tracking()` 抽出，供单视角与未来 joint_tracking_v2 双摄复用。

## Requirements
### Requirement: 可复用逐帧接口 step()

后端 SHALL 提供 `ViewTrackingSession`，封装单视角逐帧球员跟踪计算链（检测 → detection ROI 过滤 → 多目标跟踪 → 重复抑制 → 脚点 → 投影 → 平滑 → 主球员选择 → 锁定 → 身份 → 渲染观测），暴露 `step(frame, *, frame_index, timestamp, guidance=()) -> ViewFrameResult` 接口。默认 `guidance=()` 时输出与既有单视角 pipeline 完全一致（行为保护）。

#### Scenario: 逐帧调用

- **WHEN** 调用方逐帧调用 `step` 传入 frame / frame_index / timestamp
- **THEN** 返回 `ViewFrameResult`，包含 `frame_detections` / `frame_positions` / `render_raw_by_track` / `player_motion_pixels`
- **AND** session 内部按每 source frame 至多一次完整 tracking 链推进其 per-view 状态

#### Scenario: 默认 guidance 行为保护

- **WHEN** `guidance=()` 且无 guided detection 输入
- **THEN** session 输出 SHALL 与重构前的单视角跟踪路径一致
- **AND** 重构前后 synthetic differential test SHALL 逐项一致（raw detections / frame detections / positions / render observations / render events / player trajectory / metric tracks / ROI counters）

#### Scenario: guidance 参数占位

- **WHEN** 传入非空 `guidance`
- **THEN** session SHALL NOT 执行 guided ROI 检测（Change 1 契约未启用，仅预留参数）

### Requirement: Per-view tracking 状态持有

`ViewTrackingSession` SHALL 持有 per-view tracking 状态（`MultiObjectTracker` / `DuplicateTrackSuppressor` / `CourtPositionSmoother` / `PrimaryPlayerSelector` / `PlayerLockManager` / `PlayerIdentityManager` / `FootpointEstimator` / `PlayerProjector`）。不同 session 实例间 SHALL NOT 共享内部状态。

#### Scenario: 双实例隔离

- **WHEN** 创建两个 `ViewTrackingSession` 实例
- **THEN** 各自的 tracker / lock / identity 状态 SHALL 独立演进，互不干扰

### Requirement: 组件注入保留

`ViewTrackingSession` SHALL 接受**已解析**的 tracking components（tracker / footpoint_estimator / projector 等），并由 `build_view_tracking_session(...)` 工厂解析/构造。工厂 SHALL 保留调用方对 `tracker` / `footpoint_estimator` / `projector` 的注入语义（注入优先，未注入才默认构造）。session SHALL NOT 裸露内部 manager，SHALL 提供窄接口（`snapshot()` / `build_player_trajectory_artifact(...)` / `projected_metric_tracks()`）供结束阶段消费。

#### Scenario: 注入优先

- **WHEN** 调用方注入自定义 `tracker` / `footpoint_estimator` / `projector`
- **THEN** session SHALL 使用注入实例，而非默认构造

#### Scenario: 窄接口消费

- **WHEN** run 完成
- **THEN** 调用方 SHALL 通过 session 窄接口（而非直接访问内部 manager）读取结束阶段所需数据

### Requirement: 重量模型注入共享

`ViewTrackingSession` SHALL 接受外部注入的 `PersonDetector`（可跨实例共享同一实例）；`PoseEstimator` 由调用方（`AnalysisPipeline`）持有，不进入 session 主循环。

#### Scenario: 共享 detector

- **WHEN** 两个 `ViewTrackingSession` 注入同一 `PersonDetector` 实例
- **THEN** 两个实例均可正常 `step`，无重复加载模型

### Requirement: detection ROI 过滤在 session 内

`ViewTrackingSession` SHALL 在检测后、跟踪前对检测框应用 detection ROI 过滤（ROI artifact 由调用方计算并注入 session），并累积被过滤计数与全帧回退计数供诊断产物消费。

#### Scenario: ROI 过滤计数累积

- **WHEN** session 处理帧且检测框落在 ROI 外
- **THEN** 被过滤的检测 SHALL NOT 进入 tracking / projection 路径
- **AND** session SHALL 累积 `roi_filtered_detection_count`

#### Scenario: ROI 不可用全帧回退

- **WHEN** ROI artifact 不可用或被配置禁用
- **THEN** session SHALL 回退到全帧检测行为
- **AND** session SHALL 累积 `full_frame_fallback_count`

### Requirement: 处理帧计数归 Pipeline

`processed_frame_count` SHALL 由 `AnalysisPipeline` 持有，统计"被 stride 采样并经过 court-view 判断的帧数"（含被 court-view gate 挡掉的帧），并在 court-view gate 判断之后、跳过 gated 帧之前递增。`ViewTrackingSession` SHALL NOT 持有该计数。

#### Scenario: gated 帧计入计数

- **WHEN** 一帧被 court-view gate 挡掉
- **THEN** `processed_frame_count` 仍 SHALL 递增（与重构前一致）
- **AND** session 的 step 不被调用（gated 帧不进入 tracking 链）

### Requirement: identity epoch 更新顺序

`ViewTrackingSession` SHALL 保持以下顺序不变量：identity 更新后先构建当帧 render observation（使用当前 identity_epoch），再读取 diagnostics；若发生 reset 则在该帧观测生成后递增 epoch。即 reset 发生当帧的 render observation 使用旧 epoch，新 epoch 从后续帧生效。

#### Scenario: reset 当帧 epoch 不变

- **WHEN** identity 在某帧发生 `player_reset_after_prolonged_loss`
- **THEN** 该帧的 render observation SHALL 使用 reset 前的 epoch
- **AND** 自下一帧起使用递增后的新 epoch

### Requirement: 累积产物契约

`ViewTrackingSession` SHALL 在 run 过程中累积 `raw_detections` / `tracks` / `positions` / `overlay_frames` / `render_observations` / `render_events` / `player_multitarget_detections` / `selection_diagnostics` / `lock_diagnostics` / `roi_filtered_detection_count` / `full_frame_fallback_count`，供结束阶段读取并组装单视角 artifacts。`selection_diagnostics` 与 `lock_diagnostics` SHALL 为累计列表；`latest_selection_training_samples` SHALL 为最新快照（每帧覆盖，最终保存 selector 最新输出），SHALL NOT 累计拼接。

#### Scenario: 结束阶段读取

- **WHEN** run 完成
- **THEN** 调用方 SHALL 能从 session 累积产物组装 `TrackingResult` / `PlayerTrajectoryArtifact` / `PlayerSelectionArtifact` / 渲染轨迹
- **AND** `lock_diagnostics` SHALL 原样参与 `player_trajectories.diagnostics` 合并排序
- **AND** `latest_selection_training_samples` 保存 selector 最新一帧的输出快照，而非跨帧累计
