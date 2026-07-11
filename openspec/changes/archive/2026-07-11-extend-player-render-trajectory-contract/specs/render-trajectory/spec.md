## MODIFIED Requirements

### Requirement: CourtTrackPostProcessor 处理渲染轨迹

系统必须提供 `CourtTrackPostProcessor` 模块，从观测/事件输入生成包含渲染槽位和分段信息的逐帧渲染轨迹。`build_tracks()` 保持返回 `list[RenderFrame]`（向后兼容），新增 `process()` 返回 `CourtTrackPostProcessResult`。

#### Scenario: process() 返回完整结果

- **WHEN** 调用 `CourtTrackPostProcessor.process(observations, events, fps, total_frames)`
- **THEN** 必须返回 `CourtTrackPostProcessResult`，包含 `players`、`segments`、`samples`

#### Scenario: build_tracks() 向后兼容

- **WHEN** 调用 `CourtTrackPostProcessor.build_tracks(observations, events, fps, total_frames)`
- **THEN** 必须返回 `list[RenderFrame]`（委托给 `process()` 并取 `.samples`）

#### Scenario: 读取上游 identity_epoch 并切段

- **WHEN** `CourtTrackObservation.identity_epoch` 在连续观测之间发生变化
- **THEN** 必须创建新 segment
- **AND** `segment.break_before` 必须为 `identity_reset`
- **AND** PostProcessor MUST NOT 自行递增 epoch

#### Scenario: 时间 gap 超越阈值产生新 segment

- **WHEN** 两个连续 observed 帧的时间差 > `max_visible_gap_seconds`
- **AND** identity_epoch 不变
- **THEN** 必须创建新 segment
- **AND** `segment.break_before` 必须为 `visible_gap`

#### Scenario: 无投影失败事件时不得生成 projection_gap

- **WHEN** 连续 observed 帧间仅存在时间缺口
- **AND** 没有 CourtTrackEvent 明确记录投影失败
- **THEN** 系统 MUST 生成 `visible_gap` 而非 `projection_gap`

#### Scenario: 全量输入建立 roster 并分配 render_slot

- **WHEN** `process()` 被调用
- **THEN** 系统必须首先建立完整 player roster
- **AND** `observed_player_count > 4` 时抛出 `RenderSlotOverflowError`
- **AND** 按确定性规则一次性分配 `render_slot`（slot_1 至 slot_4）
- **AND** 每个 `RenderFrame` 的 `render_slot` 字段必须被填充

#### Scenario: 生成 segment 元数据

- **WHEN** segments 被划分完成后
- **THEN** 系统必须为每个 segment 生成 `RenderSegmentMetadata`
- **AND** 必须包含 `segment_id`、`player_id`、`identity_epoch`、`start_frame_index`、`end_frame_index`、`break_before`、`sample_count`
- **AND** MUST NOT 包含 `start_sequence_index` 或 `end_sequence_index`

## ADDED Requirements

### Requirement: identity_epoch 由上游生成，PostProcessor 只消费

`CourtTrackPostProcessor` 将 `CourtTrackObservation.identity_epoch` 视为权威输入，不负责递增或重新计算 epoch。当前只有上游已实现的 `player_reset_after_prolonged_loss` 会改变 epoch。未来上游实现 canonical identity reassignment 后，只要递增 epoch，PostProcessor 无需修改即可自动切段。

#### Scenario: epoch 变化触发新 segment

- **WHEN** PostProcessor 处理过程中连续观测的 identity_epoch 不同
- **THEN** 系统必须创建新 segment
- **AND** `segment.break_before` 必须为 `identity_reset`
- **AND** PostProcessor MUST NOT 修改 `identity_epoch`

#### Scenario: 可见性 gap 只产生新 segment，epoch 不变

- **WHEN** 两帧时间 gap > `max_visible_gap_seconds`
- **AND** identity_epoch 相同
- **THEN** identity_epoch MUST 保持不变
- **AND** 系统 MUST 创建新 segment
- **AND** `segment.break_before` MUST 为 `visible_gap`

#### Scenario: 普通 track ID 变化不触发 epoch 递增

- **WHEN** source_track_id 在两帧之间变化
- **AND** identity_epoch 相同
- **AND** 时间和距离连续
- **THEN** identity_epoch MUST 保持不变
- **AND** segment_id MUST 保持不变

### Requirement: canonical_player_id 在 PostProcessor 入口规范化

PostProcessor 入口必须对输入的所有 player_id 执行 `canonical_player_id()` 规范化，确保 slot 分配和分段使用一致的 ID 格式。

#### Scenario: 规范化输入中的 player_id

- **WHEN** `process()` 接收包含 `player_1` 和 `Player_1` 的观测
- **THEN** 所有 player_id MUST 被规范化为 `Player_1`
- **AND** roster 中 MUST 只出现一次 `Player_1`

### Requirement: RenderSlotOverflowError 仅影响渲染 artifact

`RenderSlotOverflowError` MUST 被 visualization/post-processing 阶段捕获，仅将 `player-render-trajectories` artifact 标记为 `failed`。

#### Scenario: 溢出错误不传播

- **WHEN** PostProcessor 抛出 `RenderSlotOverflowError`
- **THEN** `player_render_trajectory_status` MUST 为 `failed`
- **AND** tracking、ball trajectory、report 等其他 artifact MUST 不受影响
- **AND** 分析任务整体 MUST NOT 标记为 failed
