## MODIFIED Requirements

### Requirement: Stable doubles player identities

后端 SHALL 将目标球场合格的投影球员观测分配为稳定的比赛级 `player_id`，区别于检测器观测与临时 tracker `track_id`。身份分配 SHALL 以 lock manager 的一对一 track-to-slot hint 为权威；身份层 SHALL 不独立创建球员身份，但 SHALL 允许对合格且未匹配的 track 做有界的位置连续性软接管。

#### Scenario: Tracker 为四名真实球员产生碎片化 ID

- **WHEN** 双打视频在全场产生超过四个不同的 source `track_id`
- **THEN** 最终球员轨迹 artifact 对目标球场比赛指标只暴露不超过四个稳定的 `player_id` 轨迹

#### Scenario: 保留源 track 历史

- **WHEN** 多个 source `track_id` 被分配给同一名真实目标球场球员
- **THEN** 球员状态记录当前与历史 source track ID 供诊断使用

#### Scenario: lock hint 优先且一对一

- **WHEN** lock manager 为一个新 track 发出 canonical player hint
- **THEN** 身份层 SHALL 优先绑定 hint 指定的 player
- **AND** 同一个 track SHALL NOT 同时更新两个 player

#### Scenario: 身份层不独立创建身份

- **WHEN** 出现新的未绑定 `track_id`，且 lock manager 尚未为其发出 hint
- **THEN** 身份层 SHALL 先尝试位置连续性软接管
- **AND** 若软接管不可用，SHALL 将该观测记录为 `unmatched`
- **AND** SHALL 不创建新的 `player_id`

### Requirement: PlayerLockUpdate 驱动的 eligible_track_ids

`_run_tracking()` 构建 `eligible_track_ids` 时 SHALL 消费 `PlayerLockManager.update()` 返回的 `PlayerLockUpdate`，并保留 lock manager 提供的当前锁定 track、同槽位恢复候选和 `track_identity_hints`。

#### Scenario: PlayerLockUpdate 包含恢复候选

- **WHEN** 一个已锁定 slot 的旧 track 暂时消失
- **AND** 当前帧出现通过同槽位恢复门控的新 track
- **THEN** `eligible_track_ids` SHALL 包含该新 track
- **AND** `track_identity_hints` SHALL 将其指向原 canonical player ID

#### Scenario: 同一 track 不产生多个身份提示

- **WHEN** 多个 LOST slot 竞争一个新 track
- **THEN** `PlayerLockUpdate.track_identity_hints` SHALL 只保留一个 slot 的绑定
- **AND** 未获分配的 slot SHALL 保持 LOST

#### Scenario: 已锁定 track 即使未进 top 4 也被保留

- **WHEN** 已锁定 track 本帧置信度低且未进入 selector top 4
- **THEN** 该 track SHALL 仍在 `eligible_track_ids` 中
- **AND** 身份层 SHALL 能接收到该 track 的观测

### Requirement: track 重连评分

当已锁定球员的 track 断开或短暂换 ID 后出现新 track，系统 SHALL 使用目标球场资格、metric court position、运动连续性、槽位 side/quadrant 辅助信息和可选 bbox 形状评分判断同槽位回连；首版 SHALL NOT 依赖外观特征。

#### Scenario: 新 track 出现在短暂丢失球员附近

- **WHEN** 一个未绑定 source track 出现在丢失球员最近已知或预测的 metric court 位置附近
- **AND** 该 track target-court eligible
- **AND** 该候选未被其他 slot 预留
- **THEN** 系统 SHALL 将其绑定到原 player identity
- **AND** SHALL 产出 `player_reconnected_from_lost` 或等价恢复诊断

#### Scenario: 一个候选不能重复回连

- **WHEN** 一个候选同时达到多个 slot 的 reconnect threshold
- **THEN** 系统 SHALL 使用确定性的一对一分配选出至多一个目标 slot
- **AND** SHALL NOT 产生两个 player_id 指向同一 track 的最终样本

#### Scenario: 总重连分达到阈值时回连

- **WHEN** reconnect_score >= reconnect_threshold
- **THEN** 系统 SHALL 将新 track 绑定到已有的 canonical player identity
- **AND** 状态 SHALL 从 LOST 恢复为 LOCKED 或保持 LOCKED
- **AND** 诊断事件 SHALL 包含各分项 score

### Requirement: 合格未匹配 track 的位置连续性软接管

后端 SHALL 对目标球场合格、既无 lock hint 也无既有映射的观测按最近已知位置进行有界软接管；lock manager 的 hint 和一对一分配 SHALL 始终优先。

#### Scenario: 新 track 在短暂漏检后获得软接管

- **WHEN** 新 track 尚未获得 lock hint
- **AND** 该 track 已进入 `eligible_track_ids`
- **AND** 其位置落在某既有球员 `soft_takeover_max_distance_m` 范围内
- **THEN** 身份层 SHALL 绑定到该既有 player
- **AND** 样本 SHALL 标记为 `tracking_status="tentative"`

#### Scenario: 未进入 eligibility 的 track 不应静默生成 person 轨迹

- **WHEN** 一个新 track 没有 lock hint、没有既有映射且未进入 `eligible_track_ids`
- **THEN** 身份层 SHALL 记录过滤或 unmatched 原因
- **AND** 回归诊断 SHALL 能区分“未进入 eligibility”和“进入后无法软接管”

## ADDED Requirements

### Requirement: 短暂漏检后的 canonical 身份恢复

系统 SHALL 将同一真实球员的短暂漏检和 tracker track replacement 视为同一 canonical player 的候选恢复，而不是创建新身份或长期降级为通用 person。

#### Scenario: 旧 track 到新 track 的身份保持

- **WHEN** Player_2 在帧 N 使用 track A
- **AND** 在短暂缺失后于帧 N+K 使用合格的 track B
- **THEN** track B SHALL 绑定到 Player_2
- **AND** Player_1、Player_3、Player_4 SHALL 不因该恢复发生重新编号

#### Scenario: 恢复失败仍可诊断

- **WHEN** track B 不满足距离、置信度或目标球场门控
- **THEN** 系统 SHALL 保持原 slot 身份但暂不绑定 track B
- **AND** diagnostics SHALL 记录拒绝原因，不创建第五个身份
