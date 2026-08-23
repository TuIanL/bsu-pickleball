## ADDED Requirements

### Requirement: Track 与 slot 双射及歧义保持
`PlayerLockManager` SHALL 在每 tick 维护 active track↔player slot 双射。incumbent 失去观测时 slot SHALL 进入 grace/lost；候选接管必须满足同 side、运动/尺度连续、未被其他 slot 占用、连续证据与 ambiguity margin。证据歧义时 SHALL 保持 incumbent/lost 状态，不得直接换人。

#### Scenario: P1 track 被误提议给 P2
- **WHEN** P1 的 active track 同时被恢复逻辑提议给 lost P2
- **THEN** P2 恢复 SHALL 被拒绝为 track-owned/duplicate
- **AND** P1 binding SHALL 保持不变

#### Scenario: 新 track 连续证明属于 P2
- **WHEN** 新 track 在同 side、预测邻域和尺度范围内连续达到切换证据阈值且无竞争
- **THEN** slot SHALL 将其恢复为 P2 并增加 identity epoch
- **AND** diagnostic SHALL 记录旧/新 track、分项分数和证据帧数

### Requirement: Slot appearance template 不可自污染
PlayerSlot appearance template SHALL 只由 confirmed detector-backed observation 更新，并使用质量加权、限幅的稳健聚合。reconnect probation、歧义、投影、插值或已被其他 slot 拥有的 track SHALL NOT 更新 template。appearance score SHALL 作为 reconnect 分项写入诊断，但 MUST NOT 覆盖 side/ownership/distance hard rejection。

#### Scenario: P1 bbox 被误提议为 P2 且颜色接近
- **WHEN** candidate 已被 P1 拥有，即使其 appearance 与 P2 template 相似
- **THEN** P2 SHALL 因 ownership hard gate 拒绝该 candidate
- **AND** P2 template SHALL 不更新
