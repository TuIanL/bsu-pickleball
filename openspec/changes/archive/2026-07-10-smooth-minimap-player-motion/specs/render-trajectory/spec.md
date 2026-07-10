## ADDED Requirements

### Requirement: 原始坐标在 smoother 前保存

系统必须在 `CourtPositionSmoother.update()` 执行之前保存每一帧的原始球场坐标，供渲染轨迹使用。

#### Scenario: 原始坐标与平滑坐标分离

- **WHEN** analysis pipeline 处理每一帧
- **THEN** `pos.court_position` 被 smoother 覆盖之前，系统必须保存该值的副本
- **AND** 原始坐标必须独立于 `pos.court_position` 的后续修改

#### Scenario: 原始坐标不参与指标计算

- **WHEN** metrics 从 `player_metric_tracks` 计算
- **THEN** 原始坐标不得出现在 `player_metric_tracks` 中
- **AND** 现有指标输出必须与修改前一致

### Requirement: 渲染观测 (CourtTrackObservation) 逐帧收集

系统必须在 pipeline 中逐帧收集 `CourtTrackObservation` 结构，包含原始坐标和稳定 player_id。

#### Scenario: 观测包含原始坐标

- **WHEN** pipeline 完成一帧的身份分配
- **THEN** 系统必须为每个有 `tracking_status == "detected"` 的球员生成一条 CourtTrackObservation
- **AND** `raw_x_ft` / `raw_y_ft` 必须来自 smoother 前的原始坐标
- **AND** `player_id` 必须来自 IdentityManager 分配的稳定身份（通过 `canonical_player_id()` 规范化大小写）
- **AND** `identity_epoch` 必须反映该身份的当前纪元

#### Scenario: 观测包含投影质量信息

- **WHEN** 生成 CourtTrackObservation
- **THEN** 必须包含 `projection_status`、`projection_confidence`、`footpoint_method`
- **AND** 必须包含该帧的 `confidence`

### Requirement: 生命周期事件通过 Pipeline 侧 Cursor 收集

系统不得在 `PlayerIdentityManager` 上新增 API 方法。必须通过 diagnostics cursor 在 pipeline 侧适配。

#### Scenario: diagnostics cursor 收集事件

- **WHEN** pipeline 每帧调用 IdentityManager 后
- **THEN** 系统必须从 `identity_manager.diagnostics` 的增量中读取新事件
- **AND** 根据事件映射表转换为 `CourtTrackEvent`

#### Scenario: 身份重置时递增 epoch

- **WHEN** 遇到 `player_reset_after_prolonged_loss` 事件
- **THEN** 系统必须在 `identity_epoch_by_player` 中递增对应 player_id 的纪元
- **AND** 后续该 player_id 的观测必须使用递增后的 epoch 值

#### Scenario: epoch 在不同 player_id 之间独立

- **WHEN** 一个球员触发 prolonged_loss_reset
- **THEN** 其他球员的 epoch 不得受影响

### Requirement: CourtTrackPostProcessor 处理渲染轨迹

系统必须提供 `CourtTrackPostProcessor` 模块，从观测/事件输入生成逐帧渲染轨迹。

#### Scenario: 输入为观测和事件列表

- **WHEN** 调用 `CourtTrackPostProcessor.build_tracks(observations, events, fps, total_frames)`
- **THEN** 必须返回 `ProcessedCourtTracks` 包含分段后的逐帧轨迹

#### Scenario: 按 (player_id, epoch) 分段

- **WHEN** `identity_epoch` 发生变化
- **THEN** 必须将轨迹切分为独立 segment
- **AND** 不同 segment 之间不得跨段插值

### Requirement: 基础异常点过滤

PostProcessor 必须在插值前过滤孤立跳点。

#### Scenario: 三点孤立尖峰检测

- **WHEN** 三个连续观测点中，中间点距前后点均超过 `max_displacement_ft`（默认 6.0 英尺），而前后点距离较小
- **THEN** 系统必须拒绝中间观测点
- **AND** 被拒绝的观测点不参与插值
- **AND** 前后观测之间直接连线，不冻结位置

#### Scenario: 非有限值丢弃

- **WHEN** 观测的 `raw_x_ft` 或 `raw_y_ft` 为非有限值
- **THEN** 该观测必须丢弃
- **AND** 不进入插值

#### Scenario: projection_failed 丢弃

- **WHEN** 观测的 `projection_status` 为 `projection_failed`
- **THEN** 该观测必须丢弃
- **AND** 不进入插值

### Requirement: 线性插值填充中间帧

#### Scenario: 短间隔正常插值

- **WHEN** 两个保留的 observed 帧间隔 ≤ 0.35 秒
- **THEN** 系统必须在它们之间生成逐帧线性插值坐标
- **AND** 每个插值点的 `source` 标记为 `interpolated`

#### Scenario: 超过最大间隙不插值

- **WHEN** 两个保留的 observed 帧间隔 > 0.60 秒
- **THEN** 系统不得连接两端点
- **AND** 中间帧不得产生任何坐标
- **AND** 轨迹在该处切断

#### Scenario: 中等间隔插值且 confidence 衰减

- **WHEN** 0.35 秒 < 间隔 ≤ 0.60 秒
- **THEN** 系统生成线性插值坐标
- **AND** 插值点的 `confidence` 必须低于两端观测点
- **AND** `confidence` 随与最近观测点的距离递减

### Requirement: 渲染轨迹 artifact

系统必须生成独立的 `player_render_trajectory.json` artifact。

#### Scenario: 渲染轨迹包含逐帧坐标

- **WHEN** 生成 `player_render_trajectory.json`
- **THEN** 每个球员的轨迹必须包含从帧 0 到 `total_frames` 的逐帧坐标
- **AND** 每帧必须包含 `frame_index`、`timestamp_seconds`、`x_ft`、`y_ft`、`source`、`confidence`

#### Scenario: 渲染轨迹不包含未分配身份的点

- **WHEN** 某帧某身份无对应观测且不在插值范围内
- **THEN** 该帧不得出现在该球员的轨迹数组中

### Requirement: Artifact API 路由

系统必须为渲染轨迹 artifact 提供 HTTP API 端点。

#### Scenario: 注册白名单和路由

- **WHEN** 系统启动
- **THEN** `player-render-trajectories` 必须出现在 artifact 类型白名单中
- **AND** `/api/analysis/jobs/{job_id}/artifacts/player-render-trajectories` 必须可用

### Requirement: 指标点与渲染点分离

`_run_visualization` 必须分离静态可视化轨迹和 Overlay 渲染轨迹的消费数据源。

#### Scenario: 热力图和散点图使用指标点

- **WHEN** `PositionVisualizationDataBuilder` 和 `PositionVisualizer` 处理数据
- **THEN** 它们必须消费 `player_points_from_artifact(players_trajectory)` 的结果

#### Scenario: Overlay 使用渲染点

- **WHEN** `OverlayVideoWriter` 渲染小地图
- **THEN** 它必须消费 `player_render_points_from_artifact(player_render_trajectory)` 的结果

#### Scenario: 渲染点缺失时回退

- **WHEN** `player_render_trajectory.json` 不存在或状态不可用
- **THEN** OverlayVideoWriter 必须回退到 `player_points_from_artifact(players_trajectory)` 的结果
- **AND** 回退行为必须与修改前一致

### Requirement: Overlay 逐帧索引读取

OverlayVideoWriter 不得在视频循环中全量扫描历史点列表。

#### Scenario: 帧索引表预构建

- **WHEN** OverlayVideoWriter 开始写入视频
- **THEN** 必须将渲染轨迹构建为 `dict[int, dict[str, Point]]` 帧索引表
- **AND** 视频主循环按 `frame_index` 直接读取，复杂度 O(1)

### Requirement: 球员拖尾按时间定义

球员拖尾长度由时间秒数决定，球轨迹仍使用点数。

#### Scenario: 拖尾覆盖固定时间窗口的轨迹

- **WHEN** Overlay 渲染小地图球员拖尾
- **THEN** 拖尾必须包含当前帧之前 `minimap_player_trail_seconds` 秒内的所有渲染点
- **AND** 无论 `frame_stride` 为何值，拖尾视觉长度一致

#### Scenario: 球轨迹不受影响

- **WHEN** Overlay 渲染球轨迹
- **THEN** 球轨迹仍然使用 `trail_length` 的点数逻辑
- **AND** 行为与修改前一致

#### Scenario: 球员拖尾默认值

- **WHEN** 未显式配置 `minimap_player_trail_seconds`
- **THEN** 默认值为 2.5 秒

### Requirement: player_id 渲染路径规范化

渲染路径中 LockManager 产生的 `player_` 前缀 player_id 必须规范化为 `Player_` 前缀。

#### Scenario: 规范化函数缩小作用域

- **WHEN** 在渲染事件适配器中调用 `canonical_player_id()`
- **THEN** `player_1` 必须返回 `Player_1`
- **AND** `Player_1` 必须返回 `Player_1`（不变）
- **AND** 该函数只用于渲染路径，不回写 Manager

#### Scenario: 不影响 Manager

- **WHEN** `player_id` 传入 IdentityManager 或 LockManager
- **THEN** 不得调用 `canonical_player_id()`
- **AND** Manager 的 player_id 格式保持当前行为
