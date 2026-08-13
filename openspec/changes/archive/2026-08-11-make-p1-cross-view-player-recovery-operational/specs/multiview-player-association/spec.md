## ADDED Requirements

### Requirement: geometry-gated identity continuity prior

`GlobalPlayerAssociator` SHALL 先以 canonical distance 应用 hard feasibility gate，随后才以 stable local identity key `(view_id, view_player_id, local_identity_epoch)` continuity 和 guided `expected_global_player_id` 作为 ranking penalty/prior。历史 mapping 的 fallback SHALL 遵守同一 hard gate，identity prior SHALL NOT 强制分配不可行 global；identity epoch 变化 SHALL 使旧 key 的 continuity mapping 失效。

#### Scenario: 历史 mapping 超出几何门
- **WHEN** 一个 local player 的历史 global mapping 与当前 canonical observation 距离超过 association gate
- **THEN** 系统 SHALL NOT 直接复用该 mapping
- **AND** diagnostics SHALL 记录 geometry-infeasible continuity rejection

#### Scenario: identity epoch reset 不继承 prior
- **WHEN** `Player_3` 从 identity epoch 0 reset 到 epoch 1
- **THEN** epoch 1 observation SHALL NOT 继承 epoch 0 的 global continuity prior

### Requirement: tentative bootstrap view uniqueness

同一个 tentative global 在同一 tick SHALL 至多接受每个 view 一份 observation；bootstrap grouping SHALL 不把同一 camera 的两个不同 formal local players 合并为同一 global。

#### Scenario: 同 view 近距离双人
- **WHEN** Cam1 的两个 formal local players 的 canonical 距离小于 bootstrap gate
- **THEN** 系统 SHALL 为其保留不同 tentative global candidates
