## MODIFIED Requirements

### Requirement: 位置融合状态机

`PlayerPositionFusion` 在同一 canonical timestamp、同一 global player 下融合有效观测，状态 MUST 只包括 `dual_observed / single_view_fallback / conflict / unavailable`。**`predicted` MUST NOT 属于 Fusion 状态**；是否在无观测时刻输出预测点 MUST 由 `GlobalTrackFilter` 决定。Fusion MUST NOT 采用固定 50/50 平均，而应按观测质量加权。**`single_view_fallback` SHALL 覆盖"仅单视图 binding 的 roster 玩家"场景：该玩家任一视图存在有效观测时，融合 SHALL 产出 `single_view_fallback` measurement（该视图观测质量加权），不得因跨视图 binding 缺失而不出 sample。**

#### Scenario: 双观测

- **WHEN** 同一 global player 在同一时刻有两路有效观测
- **THEN** 系统 SHALL 按观测质量加权融合
- **AND** 融合状态 SHALL 为 `dual_observed`

#### Scenario: 单视角回退

- **WHEN** 仅一路存在有效观测（含"该玩家另一路 binding 缺失/过期"情形）
- **THEN** 系统 SHALL 使用该路观测
- **AND** 融合状态 SHALL 为 `single_view_fallback`

#### Scenario: 单视图 binding 玩家持续产出

- **WHEN** roster 内玩家仅 cam_1 binding 且 cam_1 持续观测（conf≥0.5）
- **THEN** 每个观测 tick 系统 SHALL 产出 `single_view_fallback` measurement
- **AND** fused trajectory SHALL 覆盖该玩家全时段（不得结构性缺失）

#### Scenario: 无观测无预测状态

- **WHEN** 两路均无有效观测
- **THEN** `PlayerPositionFusion` SHALL 标记 `unavailable`
- **AND** 是否输出预测点 SHALL 交由 `GlobalTrackFilter` 决定，而非 Fusion 产生 `predicted` 状态
