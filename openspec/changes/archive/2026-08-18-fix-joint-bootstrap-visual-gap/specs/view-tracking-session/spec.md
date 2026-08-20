## ADDED Requirements

### Requirement: 首次 lock 映射透出
`PlayerLockManager` SHALL 在任意 slot **第一次**进入 `locked` 状态时记录一次 `InitialLockAssignment(player_id, track_id, locked_frame_index)`（永不覆盖），并随 `ViewTrackingSession.snapshot()` 透出为 `initial_lock_assignments`。该机制 SHALL NOT 改变谁被锁、何时锁、锁定阈值或 bootstrap 行为。

#### Scenario: 首次 lock 仅记一次
- **WHEN** 某 slot 从 searching/tentative 首次进入 locked（含 `_assign_candidate_to_slot` 的 bootstrap 锁定路径）
- **THEN** `initial_lock_assignments[player_id]` SHALL 被写入一次
- **AND** 后续 reconnect / tentative 切换 SHALL NOT 覆盖该记录

#### Scenario: snapshot 暴露首次 lock 映射
- **WHEN** 调用方在 run 结束后读取 `snapshot()`
- **THEN** snapshot SHALL 包含 `initial_lock_assignments`，可直接查得每个 Player_N 的锁定 `track_id` 与 `locked_frame_index`

### Requirement: pre-lock 原始 tracking 数据复用
`ViewTrackingSession.snapshot()` **已**暴露（`positions` / `tracks`，含 `track_id`、`bbox`、`court_position`(local)、`frame_index`）且覆盖 pre-lock 全帧。回填 SHALL 直接复用这些已暴露数据，MUST NOT 要求新增透出字段。

#### Scenario: 复用已有 positions
- **WHEN** joint finalize 阶段需要 pre-lock 原始观测
- **THEN** 系统 SHALL 直接消费 `snapshot().positions`（不对 `ViewTrackingSession` 增加新字段）
- **AND** 原始轨道与正式 Player_N 归因观测 SHALL 保持可区分（按 `track_id` 而非 `player_id` 取数）
