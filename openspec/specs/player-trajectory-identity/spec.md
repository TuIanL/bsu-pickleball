# player-trajectory-identity Specification

## Purpose
Provide stable match-level player identities, metric-unit player trajectories, trajectory repair, and diagnostics for doubles pickleball analysis.
## Requirements
### Requirement: Stable doubles player identities

后端 SHALL 将"目标球场合格"的投影球员观测分配为稳定的比赛级 `player_id`，区别于检测器观测与临时 tracker `track_id`。身份分配 SHALL 以 lock manager 的 track-to-slot hint 为权威；身份层 SHALL 不独立创建球员身份，但 SHALL 允许对"合格且未匹配"的 track 做有界的位置连续性软接管（见本 requirement 的软接管场景与新增 requirement）。

#### Scenario: Tracker 为四名真实球员产生碎片化 ID

- **WHEN** 双打视频在全场产生超过四个不同的 source `track_id`
- **THEN** 最终球员轨迹 artifact 对目标球场比赛指标只暴露不超过四个稳定的 `player_id` 轨迹

#### Scenario: 保留源 track 历史

- **WHEN** 多个 source `track_id` 被分配给同一名真实目标球场球员
- **THEN** 球员状态记录当前与历史 source track ID 供诊断使用

#### Scenario: 再次观测到既有 track 映射

- **WHEN** 一条观测包含已绑定到 `player_id` 的 `track_id`，且仍为目标球场合格或在配置的重连宽限期内
- **THEN** 身份层更新既有球员而不是创建新球员

#### Scenario: 身份层不独立创建身份

- **WHEN** 出现新的未绑定 `track_id`，且 lock manager 尚未为其发出 hint
- **THEN** 身份层 SHALL 先尝试位置连续性软接管（若该 track 落在某球员最近已知位置的 `soft_takeover_max_distance_m` 阈值内）
- **AND** 若软接管不可用，SHALL 将该观测记录为 `unmatched`
- **AND** SHALL 不创建新的 `player_id`（槽位封顶为 4）
- **AND** 对超过距离阈值的 track，SHALL NOT 通过全局 best-candidate 匹配指派

#### Scenario: 观测到相邻球场 track

- **WHEN** 一条观测属于被球员选择层判定为非目标球场的 tracklet
- **THEN** 身份层不基于该观测创建或更新最终目标球场 `player_id`，并记录 filtered 诊断

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

- **WHEN** `PlayerLockManager` 确定 track_id=4 是 Player_3 的 LOST 恢复候选
- **THEN** `PlayerLockUpdate.track_identity_hints` SHALL 包含 `{4: "Player_3"}`
- **AND** `PlayerIdentityManager` 在 `_assign_player()` 中 SHALL 优先绑定到 Player_3
- **AND** 提示值 SHALL 与身份层 `player_id` 键格式一致（`Player_1`..`Player_4`），保证提示真正生效

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
  - `"player_slot_filled"` — 空位被填充
  - `"rejected_low_conf_unlocked"` — 未锁定低置信度拒绝
  - `"rejected_outside_near_court"` — 超出近场区域拒绝
  - `"rejected_outside_tracking"` — 超出跟踪区域拒绝
  - `"rejected_bbox_size"` — bbox 尺寸不合规
  - `"retained_by_lock"` — 因锁定状态而保留
  - `"unmatched"` — 无法关联到任何锁定身份（含锁定层尚未给出 hint 的新 track）

#### Scenario: player_reset_after_prolonged_loss 已移除

- **WHEN** 槽位长时间丢失（`lost_frames >= lost_max_frames_locked`）
- **THEN** SHALL NOT 产生 `event: "player_reset_after_prolonged_loss"`
- **AND** 该事件值 SHALL 从 `event` 有效值中移除

#### Scenario: reason 字段包含子项分

- **WHEN** 产生 `"player_reconnected_from_lost"` 事件
- **THEN** `reason` 字段 SHALL 包含各分项分数，格式如 `"position=0.82 motion=0.65 appearance=0.43 side=0.90 bbox=0.70"`

### Requirement: 对外 player_id 取值契约

后端对外 trajectory 产物中的 `player_id` SHALL 只取锁定槽位对应的 canonical ID（`Player_1`..`Player_4`，展示为整数 `1`–`4`），数量不超过 `effective_player_count`，且 SHALL NOT 以原始 `track_id` 作为身份标识。

#### Scenario: 身份数量与锁定槽位一一对应

- **WHEN** 锁定层完成 bootstrap 并锁定 N 个槽位（N = `effective_player_count`）
- **THEN** 最终 trajectory artifact SHALL 恰好暴露 N 个 `player_id`
- **AND** 每个 `player_id` SHALL 与一个锁定槽位一一对应

#### Scenario: 原始 track_id 不作为身份标识

- **WHEN** 生成 projection 轨迹点或 trajectory 样本
- **THEN** 其身份字段 SHALL 为 canonical `player_id`
- **AND** SHALL NOT 使用原始 `track_id` 数字作为 `player_id`

### Requirement: 合格未匹配 track 的位置连续性软接管

后端 SHALL 对"目标球场合格、且既无 lock hint 也无既有 track-to-player 映射"的观测，按最近已知球场位置就近归入一个既有球员：候选球员的 `last_position_m` 距该观测在 `soft_takeover_max_distance_m` 阈值内、且本帧尚未被该球员接收过样本。软接管样本 SHALL 标记为 `tentative` 低置信度状态，SHALL NOT 创建第 5 个球员身份，且 lock hint 优先于软接管。

#### Scenario: 新 track 出现在某球员最近已知位置附近

- **WHEN** 一条目标球场合格观测既无 hint 也无映射，且其球场位置落在某球员 `last_position_m` 的 `soft_takeover_max_distance_m` 范围内
- **THEN** 身份层将该 track 绑定到该球员，记录 `soft_takeover_assigned` 诊断，并产出 `tracking_status="tentative"`、置信度被截断为低值的样本

#### Scenario: 新 track 距所有球员都很远

- **WHEN** 一条目标球场合格观测既无 hint 也无映射，且距每个球员的 `last_position_m` 都超过 `soft_takeover_max_distance_m`
- **THEN** 身份层将该观测记录为 `unmatched`，不进行指派

#### Scenario: 一帧内两名 track 抢占同一球员

- **WHEN** 某球员在当前帧已接收过一个样本，且第二条观测也在该球员的软接管阈值内
- **THEN** 身份层不把第二条观测指派给该球员

#### Scenario: lock hint 优先于软接管

- **WHEN** lock manager 在同一帧为某 track 发出 `track_identity_hints`，而软接管本应适用
- **THEN** 该 track 被指派为 hint 指定的身份，软接管不生效

#### Scenario: 软接管样本进入检测框身份

- **WHEN** 某 track 因软接管获得 `tentative` 样本
- **THEN** 该 track 在当帧检测叠加中的 `player_id` SHALL 为该球员的 canonical ID，使框标签可显示 `P1-P4`
