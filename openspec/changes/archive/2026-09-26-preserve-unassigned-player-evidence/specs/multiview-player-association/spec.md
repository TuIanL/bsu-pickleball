## ADDED Requirements

### Requirement: Bounded candidate recovery for an active roster

当 roster 已激活时，joint association SHALL 将未锁定候选和无法匹配的正式观测保留为有界恢复证据，而不是只增加一次性 unresolved 计数。恢复证据 SHALL 按 view 和稳定 tracklet lineage 跨有效 tick 聚合；恢复只能指向已有 roster global，不得创建新 global。候选只有在连续性、有效 canonical projection、uncertainty-aware geometry gate、一对一唯一性及 reassociation 安全门均通过后，才可作为既有 global 的恢复观测。未通过或有歧义时 SHALL 继续隔离。

#### Scenario: 稳定候选恢复既有 global
- **WHEN** roster 已激活，候选在同一 view 连续达到配置稳定度，且对一个已有 global 的投影几何匹配唯一并通过所有关联门
- **THEN** 系统 SHALL 将该候选作为该 global 的 recovered evidence
- **AND** SHALL 记录候选 tracklet、目标 global、证据窗口和决策原因
- **AND** SHALL NOT 创建新 global id

#### Scenario: 单帧候选不改变身份
- **WHEN** 某候选只出现一个 tick，或最佳与次优 global 的代价差未达配置 margin
- **THEN** 系统 SHALL 将其保持为 pending/ambiguous
- **AND** SHALL NOT 修改正式绑定或 trajectory

#### Scenario: view 槽位冲突保持隔离
- **WHEN** 候选恢复会覆盖同 view 内已有的不同 global binding，且 reassociation 窗口尚未满足
- **THEN** 系统 SHALL 保持 incumbent binding
- **AND** SHALL 将候选保留为 pending reassociation 或 unresolved

#### Scenario: 候选过期
- **WHEN** 候选超过配置 TTL 未获得有效新观测
- **THEN** 系统 SHALL 将其标记 expired 并释放恢复缓存
- **AND** SHALL 保留过期计数与最后有效证据时间

#### Scenario: 视角不可用不推进候选状态
- **WHEN** 某 view 本 tick 解码失败、未执行 perception 或已降级
- **THEN** 系统 SHALL NOT 把该 tick 计为候选 miss 或候选命中
- **AND** 其他可用 view 的 association SHALL 独立继续
