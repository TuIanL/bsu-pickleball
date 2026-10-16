## MODIFIED Requirements

### Requirement: 身份只读 canonical Player_N

overlay 的 `players` 中所有用户可见 P 身份 SHALL 为冻结名册审计已确认的 canonical `Player_1`..`Player_4`（展示为 P1-P4），MUST NOT 出现 `global_player_<id>`、局部 `track_id`，也不得把 `_build_roster_map` 的顺序 fallback 当作已确认身份。身份映射 SHALL 只读复用 `bootstrap-binding-audit` 与 Global Roster 的唯一绑定，overlay SHALL NOT 反写 roster、tracker 或 association。未确认但有真实观测的目标 SHALL 进入可选的匿名 `unconfirmed_observations`，不得占用 `players` 中的 P 编号；无可靠观测时不渲染目标。

#### Scenario: 已确认身份标签统一

- **WHEN** fused overlay 生成已通过冻结名册审计的球员
- **THEN** `players[].player_id` SHALL 为其 canonical `Player_N`
- **AND** `players[].label` SHALL 为对应 P1-P4 形式

#### Scenario: 顺序补位不能冒充 P 身份

- **WHEN** global roster 为球员提供 `slot_fallback`，但锚点审计未确认
- **THEN** 该观测 SHALL NOT 作为 P1-P4 出现在 `players`
- **AND** 有真实可展示证据时 SHALL 以匿名未确认观测呈现，并标明证据来源

#### Scenario: 没有证据不补画框

- **WHEN** 某冻结 P 槽位在当前帧没有有效本机位或跨机位观测
- **THEN** overlay SHALL 不生成该球员的人体框
- **AND** 页面上的身份状态 SHALL 可读取该槽位的缺失原因

#### Scenario: overlay 不反写分析真值

- **WHEN** builder 消费 F0/F1 evidence、Global Roster 与冻结身份审计
- **THEN** SHALL NOT 修改 tracker、association、metrics、roster 或审计状态
