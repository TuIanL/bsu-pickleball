## ADDED Requirements

### Requirement: Binding 逐 tick aging 与最后 view evidence

registry SHALL 在每个 canonical tick、perception 前以 take timestamp age 全部 bindings。`ViewBinding` SHALL 保存最后 local player identity、`local_identity_epoch`、track、source frame、quality、visibility、lock/tracking state、observation origin 与可用 guidance reference。availability 不得被伪装为视觉 observation。

#### Scenario: 消失后 aging
- **WHEN** 一个 view 的当前可用 source frame 未形成该 player observation
- **THEN** binding SHALL 随配置阈值从 observed 转为 weak/lost
- **AND** 另一 view 的 binding 仍可维持 global state

#### Scenario: local identity epoch 变更
- **WHEN** 同一 view 的 `player_id` 经 identity reset 产生新的 `identity_epoch`
- **THEN** 系统 SHALL 不将新 epoch 继承为旧 epoch 的 continuity binding

### Requirement: base-only cross-view anchor

`cross_view_anchored` SHALL 只由同一 tick 中 distinct views 的 base+base 一致 observation 累积；guided/base 组合可融合但不得建立或增加 anchor。

#### Scenario: guided 恢复不自证
- **WHEN** 某 tick 包含 Cam1 base 与 Cam2 guided_roi observation
- **THEN** 系统 SHALL 可将其作为真实 measurement 融合
- **AND** SHALL NOT 因该组合使尚未 anchored 的 global 成为 anchored
