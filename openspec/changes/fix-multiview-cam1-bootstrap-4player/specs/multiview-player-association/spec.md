# multiview-player-association Delta

## ADDED Requirements

### Requirement: reference view binding 槽位唯一性

`GlobalPlayerAssociator` 对 reference view 的 `(view_id, view_player_id)` 映射 SHALL 保持唯一：同一 view 内同一个 `Player_N` 槽位 SHALL 至多绑定一个 global player。新 global 尝试占用已被其他 global 占用的槽位时，SHALL 走 reassociation（`PendingReassociation`，连续强证据帧数达到 `reassociation_frames` 才切换），MUST NOT 直接覆盖既有 mapping。

#### Scenario: 两个 global 抢同一 reference 槽位不覆盖

- **WHEN** gid_1 已绑定 cam_1 的 Player_1，gid_3 的观测试图关联到 cam_1 的 Player_1
- **THEN** 系统 SHALL 将该候选标记为 reassoc pending（记录 challenger 连续强证据帧数）
- **AND** 在 `reassociation_frames` 帧强证据前，mapping SHALL 保持 gid_1 → Player_1
- **AND** SHALL NOT 立即把 Player_1 重新绑定到 gid_3

#### Scenario: 强证据达标后切换

- **WHEN** challenger（gid_3）对 cam_1 Player_1 连续强证据 ≥ `reassociation_frames`
- **THEN** mapping SHALL 切换到 gid_3 → Player_1
- **AND** 原绑定（gid_1）SHALL 进入 reacquire 候选池（historical_reacquired 语义）

### Requirement: 槽位冲突可观测

系统 SHALL 记录 reference view 槽位冲突事件（如 `event: "reference_slot_conflict"` + `view_id` + `view_player_id` + `incumbent_global` + `challenger_global` + `epoch`），供身份冲突归因（display diagnostics 的 `roster_conflict` 字段数据来源）。该观测 SHALL 只读，MUST NOT 改变 association 算法与门限。

#### Scenario: 冲突事件记录

- **WHEN** 第二个 global 尝试占用已绑定的 reference 槽位
- **THEN** 系统 SHALL 记录 `reference_slot_conflict` 事件（含双方 gid 与槽位）
- **AND** 该事件 SHALL 可在 job 观测产物中检索

#### Scenario: 观测不改变关联结果

- **WHEN** 发生槽位冲突且触发 reassoc pending
- **THEN** 冲突事件 SHALL 仅记录观测信息
- **AND** 关联算法、门限、晋升逻辑 SHALL 与实施前一致
