# player-trajectory-identity Delta Spec

## MODIFIED Requirements

### Requirement: Stable doubles player identities

The backend SHALL assign target-court-eligible projected player observations to stable match-level `player_id` values for doubles analysis, distinct from detector observations and temporary tracker `track_id` values. Identity assignment SHALL be driven by the lock manager's track-to-slot hints; the identity layer SHALL NOT create player identities independently.

#### Scenario: Tracker emits fragmented IDs for four real players
- **WHEN** a doubles video produces more than four distinct source `track_id` values across the match
- **THEN** the final player trajectory artifact exposes no more than four stable `player_id` trajectories for target-court match metrics

#### Scenario: Source track history is preserved
- **WHEN** multiple source `track_id` values are assigned to the same real target-court player
- **THEN** the player state records current and historical source track IDs for diagnostics

#### Scenario: Existing track mapping is observed again
- **WHEN** an observation contains a `track_id` already bound to a `player_id` and remains target-court eligible or is within a configured reconnect grace period
- **THEN** the identity manager updates the existing player rather than creating a new player

#### Scenario: Identity layer does not create identities independently
- **WHEN** a new unbound `track_id` appears and the lock manager has not yet emitted a hint for it
- **THEN** the identity manager SHALL record the observation as `unmatched`
- **AND** SHALL NOT create a new `player_id` for it
- **AND** SHALL NOT reassign it via position-based best-candidate matching

#### Scenario: Neighbor court track is observed
- **WHEN** an observation belongs to a tracklet classified as non-target-court by the player selection layer
- **THEN** the identity manager does not create or update a final target-court `player_id` from that observation and records filtered diagnostics

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

## ADDED Requirements

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
