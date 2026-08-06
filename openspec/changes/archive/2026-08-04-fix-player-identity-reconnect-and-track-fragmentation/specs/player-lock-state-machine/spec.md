## ADDED Requirements

### Requirement: 重连候选的空间距离门控与横向错配惩罚

系统 SHALL 在 LOCKED/LOST 槽位重连时应用空间距离门控：候选距槽位最后确认位置超过"允许距离"（`max_reconnect_distance_ft` + 估计速度 × 流逝时间）时 SHALL 拒绝重连并保持 LOST；同侧但横向错配的候选 SHALL 受到显著惩罚，不得仅凭运动/外观分数完成重连。

#### Scenario: 超距离候选被拒绝

- **WHEN** LOST 槽位的重连候选距最后确认位置超过允许距离
- **THEN** 该候选 SHALL 被拒绝，槽位 SHALL 保持 LOST
- **AND** 不输出该候选的 `track_identity_hints`

#### Scenario: 距离门按流逝时间缩放

- **WHEN** 槽位自上次确认后流逝时间越长
- **AND** 槽位估计速度非零
- **THEN** 允许距离 SHALL 相应增大（基础距离 + 速度 × 流逝时间）

#### Scenario: 同侧横向错配候选分数不足

- **WHEN** 候选在允许距离内但属于同侧不同横向象限（如近左槽位接近右候选）
- **THEN** 该候选的侧分 SHALL 与错侧同级惩罚，单独不足以达到 `reconnect_threshold`
