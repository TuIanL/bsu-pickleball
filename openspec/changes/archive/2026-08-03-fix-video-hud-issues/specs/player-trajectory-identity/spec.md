## MODIFIED Requirements

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

## ADDED Requirements

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
