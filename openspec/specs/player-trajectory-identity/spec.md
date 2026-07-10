# player-trajectory-identity Specification

## Purpose
Provide stable match-level player identities, metric-unit player trajectories, trajectory repair, and diagnostics for doubles pickleball analysis.
## Requirements
### Requirement: Stable doubles player identities
The backend SHALL assign target-court-eligible projected player observations to stable match-level `player_id` values for doubles analysis, distinct from detector observations and temporary tracker `track_id` values.

#### Scenario: Tracker emits fragmented IDs for four real players
- **WHEN** a doubles video produces more than four distinct source `track_id` values across the match
- **THEN** the final player trajectory artifact exposes no more than four stable `player_id` trajectories for target-court match metrics

#### Scenario: Source track history is preserved
- **WHEN** multiple source `track_id` values are assigned to the same real target-court player
- **THEN** the player state records current and historical source track IDs for diagnostics

#### Scenario: Existing track mapping is observed again
- **WHEN** an observation contains a `track_id` already bound to a `player_id` and remains target-court eligible or is within a configured reconnect grace period
- **THEN** the identity manager updates the existing player rather than creating a new player

#### Scenario: Neighbor court track is observed
- **WHEN** an observation belongs to a tracklet classified as non-target-court by the player selection layer
- **THEN** the identity manager does not create or update a final target-court `player_id` from that observation and records filtered diagnostics

### Requirement: Metric court coordinate identity matching
The backend SHALL use metric court coordinates as the canonical unit for player identity matching, speed filtering, interpolation, and final trajectory export.

#### Scenario: Final trajectory sample is exported
- **WHEN** a detected or interpolated player sample is written to the final trajectory artifact
- **THEN** the sample includes metric `court_x` and `court_y` values and artifact metadata declares `court_unit` as `m`

#### Scenario: Imperial dimensions are documented
- **WHEN** the final trajectory artifact includes court metadata
- **THEN** it includes standard pickleball dimensions as 13.41 m by 6.10 m and reference dimensions as 44 ft by 20 ft

#### Scenario: Existing projection uses feet during migration
- **WHEN** upstream projection output is expressed in feet
- **THEN** the identity layer converts coordinates to meters before applying distance, speed, interpolation, or boundary thresholds

### Requirement: Player state lifecycle
The backend SHALL maintain player states with `active`, `lost`, and `inactive` lifecycle statuses based on the last observed frame and configured frame buffers.

#### Scenario: Player is observed in current frame
- **WHEN** a player receives a detector-backed observation for the current frame
- **THEN** the player status is `active` and its last seen frame, position, velocity, and confidence are updated

#### Scenario: Player is temporarily missing
- **WHEN** a player has not been observed in the current frame but the gap is within the configured lost buffer
- **THEN** the player status is `lost` and the player remains eligible for reconnect assignment

#### Scenario: Player is missing beyond lost buffer
- **WHEN** a player has not been observed beyond the configured lost buffer
- **THEN** the player status becomes `inactive` while its trajectory history remains available

### Requirement: Track-to-player reconnect scoring
The backend SHALL score new or unbound track observations against existing players using target-court eligibility, metric court position, motion continuity, and optional appearance similarity when available.

#### Scenario: New track appears near predicted lost player
- **WHEN** an unbound source `track_id` appears near a lost player's predicted metric court position and is target-court eligible
- **THEN** the identity manager assigns the track to that player when the score meets the configured threshold

#### Scenario: Candidate assignment implies implausible speed
- **WHEN** assigning an observation to a player would exceed the configured maximum plausible player speed in meters per second
- **THEN** the identity manager rejects or downranks that assignment

#### Scenario: Four player identities already exist
- **WHEN** four player identities already exist and a new unbound target-court-eligible track appears
- **THEN** the system does not create a fifth player identity and instead assigns, drops, or records the track as unmatched diagnostics

#### Scenario: Unbound track lacks target-court eligibility
- **WHEN** an unbound source `track_id` has low target-court membership or is classified as a neighbor-court candidate
- **THEN** the identity manager rejects the assignment regardless of generic person confidence or movement level

### Requirement: Trajectory repair and sample status
The backend SHALL repair short missing intervals with interpolation and SHALL distinguish detector-backed samples from synthetic samples.

#### Scenario: Player reconnects after short gap
- **WHEN** the same player has detector-backed positions before and after a missing interval within the interpolation buffer
- **THEN** the backend fills the missing frames with interpolated metric court positions

#### Scenario: Interpolated point is exported
- **WHEN** a trajectory point is generated by interpolation
- **THEN** the exported sample sets `is_interpolated` to true and uses a `tracking_status` that is not `detected`

#### Scenario: Missing interval exceeds interpolation buffer
- **WHEN** a player is missing for longer than the configured interpolation buffer
- **THEN** the backend does not synthesize continuous trajectory points for that interval

### Requirement: Player trajectory artifacts
The backend SHALL export player-level trajectory artifacts that include JSON and CSV forms suitable for metrics, debug visualization, and manual review.

#### Scenario: JSON artifact is generated
- **WHEN** a real calibrated video analysis completes with player observations
- **THEN** the backend writes a JSON artifact containing video metadata, court unit metadata, player states, source track history, and per-player trajectory samples

#### Scenario: CSV artifact is generated
- **WHEN** a real calibrated video analysis completes with player observations
- **THEN** the backend writes a CSV artifact with frame, timestamp, player ID, source track ID, bbox, image footpoint, metric court coordinates, confidence, tracking status, and interpolation marker

#### Scenario: Metrics consume player identities
- **WHEN** player-level trajectory artifacts are available
- **THEN** movement metrics use stable `player_id` trajectories instead of raw temporary `track_id` fragments

### Requirement: Identity diagnostics
The backend SHALL expose diagnostics for identity assignment, reconnect, lost, inactive, and unmatched-track events.

#### Scenario: Track is assigned to player
- **WHEN** an unbound source track is assigned to a player
- **THEN** diagnostics record the frame, source `track_id`, target `player_id`, assignment score, and primary reason

#### Scenario: Player transitions to lost
- **WHEN** a player becomes lost
- **THEN** diagnostics record the transition frame and the player's last known metric court position

#### Scenario: Track cannot be assigned
- **WHEN** a source track fails assignment or is filtered as incidental
- **THEN** diagnostics preserve the decision without adding it to final player trajectories

### Requirement: Player trajectory 覆盖诊断

后端 SHALL 在 player trajectory identity 输出或分析阶段 counters 中提供轨迹覆盖诊断，使下游发球检测能够识别目标球员轨迹提前中断、身份失联或目标球场过滤过严。

#### Scenario: Player trajectory 覆盖完整视频
- **WHEN** 真实视频分析完成且稳定 player trajectory 覆盖接近完整源视频时长
- **THEN** trajectory artifact 或 diagnostics SHALL 暴露每个 `player_id` 的样本数量、最早时间、最晚时间、detected/interpolated 分布和源 track 历史摘要

#### Scenario: Player trajectory 提前中断
- **WHEN** tracking overlay 仍覆盖后续视频但所有或主要 player trajectory 的最后样本时间明显早于源视频结束时间
- **THEN** trajectory diagnostics SHALL 记录覆盖缺口、最后活跃时间、可能原因和被过滤或未匹配 track 的摘要

#### Scenario: 目标球场过滤导致无样本
- **WHEN** 后半段存在人体检测框但 primary-player selection 或 target-court eligibility 没有为 identity layer 提供合格 track
- **THEN** diagnostics SHALL 记录该时间段的过滤原因，以便发球检测和 UI 能报告输入链路不足

#### Scenario: 下游能力读取覆盖诊断
- **WHEN** 发球检测消费 player trajectory artifact
- **THEN** 它 SHALL 能读取或推导 trajectory 覆盖信息，并在覆盖不足时输出降级或诊断结果

### Requirement: PlayerLockUpdate 驱动的 eligible_track_ids

`_run_tracking()` 构建 `eligible_track_ids` 时 SHALL 消费 `PlayerLockManager.update()` 返回的 `PlayerLockUpdate` 结构，而非仅使用 `PrimaryPlayerSelector` 的 top 4 结果。`PlayerLockUpdate` 提供 `eligible_track_ids` 并集以及 `track_identity_hints` 映射。

#### Scenario: PlayerLockUpdate 包含建议 + 锁定 + 重连候选

- **WHEN** `PrimaryPlayerSelector` 建议 track_ids = {3, 7, 12, 15}
- **AND** `PlayerLockManager` 已锁定 slot 包含 track_ids = {3, 4, 8}（4 为 LOST 恢复窗口中的 track）
- **THEN** `PlayerLockUpdate.eligible_track_ids` SHALL = {3, 4, 7, 8, 12, 15}

#### Scenario: track_identity_hints 告知身份管理器绑定关系

- **WHEN** `PlayerLockManager` 确定 track_id=4 是 player_3 的 LOST 恢复候选
- **THEN** `PlayerLockUpdate.track_identity_hints` SHALL 包含 `{4: "player_3"}`
- **AND** `PlayerIdentityManager` 在 `_assign_player()` 中 SHALL 优先尝试绑定到 player_3

#### Scenario: 已锁定 track 即使未进 top 4 也被保留

- **WHEN** 远端球员 track_id=5 是已锁定的 `Player_4`，但本帧置信度低未进入 select() top 4
- **AND** `PlayerLockManager` 的 LOCKED slot 中 `current_track_id=5`
- **THEN** track_id=5 SHALL 仍在 `PlayerLockUpdate.eligible_track_ids` 中
- **AND** `PlayerIdentityManager` SHALL 接收到该 track 的观测

#### Scenario: 无锁定球员时不引入额外候选

- **WHEN** `PlayerLockManager` 无任何 LOCKED/LOST slot（如 bootstrap 尚未完成）
- **AND** `PrimaryPlayerSelector` 建议 track_ids = {1, 2, 3}
- **THEN** `PlayerLockUpdate.eligible_track_ids` SHALL = {1, 2, 3}

### Requirement: track 重连评分

当已锁定球员的 track 断开后出现新 track，系统 SHALL 计算 reconnect_score 判断是否回连。首版 SHALL NOT 依赖外观特征。

#### Scenario: 位置匹配贡献最高权重

- **WHEN** 新候选的球场坐标距 Player_x 上次已知位置距离为 d
- **THEN** position_score SHALL = max(0, 1 - d / max_reconnect_distance_ft)
- **AND** position_score 在综合分中 SHALL 权重为 0.40

#### Scenario: 运动预测权重

- **WHEN** Player_x 有最近速度估计
- **THEN** motion_prediction_score SHALL 基于预测位置与实际候选位置的匹配度计算
- **AND** motion_prediction_score SHALL 权重为 0.30

#### Scenario: 外观特征首版禁用

- **WHEN** `player_lock_enable_appearance_score = False`（默认）
- **THEN** 重连评分 SHALL 仅包含 position（0.40）+ motion（0.30）+ side（0.20）+ bbox_shape（0.10）
- **AND** appearance_score 权重 SHALL 为 0.0

#### Scenario: 总重连分达到阈值时回连

- **WHEN** reconnect_score >= reconnect_threshold（默认 0.45）
- **THEN** 系统 SHALL 将新 track 绑定到已有的 player identity
- **AND** 状态 SHALL 从 LOST 恢复为 LOCKED
- **AND** 诊断事件 SHALL 包含 `event: "player_reconnected_from_lost"` 及各分项 score

### Requirement: 诊断事件扩展

`PlayerIdentityDiagnostic` 的 `event` 字段 SHALL 扩展以支持锁定相关事件。

#### Scenario: 新事件类型

- **WHEN** `PlayerLockManager` 产生状态相关事件
- **THEN** `event` 有效值 SHALL 包含：
  - `"player_locked"` — 球员首次锁定
  - `"player_reconnected_from_lost"` — 从 LOST 恢复
  - `"player_reset_after_prolonged_loss"` — 长时间丢失后重置
  - `"player_slot_filled"` — 空位被填充
  - `"rejected_low_conf_unlocked"` — 未锁定低置信度拒绝
  - `"rejected_outside_near_court"` — 超出近场区域拒绝
  - `"rejected_outside_tracking"` — 超出跟踪区域拒绝
  - `"rejected_bbox_size"` — bbox 尺寸不合规
  - `"retained_by_lock"` — 因锁定状态而保留

#### Scenario: reason 字段包含子项分

- **WHEN** 产生 `"player_reconnected_from_lost"` 事件
- **THEN** `reason` 字段 SHALL 包含各分项分数，格式如 `"position=0.82 motion=0.65 appearance=0.43 side=0.90 bbox=0.70"`
