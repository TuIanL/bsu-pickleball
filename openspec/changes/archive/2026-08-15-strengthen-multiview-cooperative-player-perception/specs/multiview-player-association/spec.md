## ADDED Requirements

### Requirement: pre-association 一对一匹配 + ambiguity rejection（只读）

系统 SHALL 提供只读 pre-association 候选归属先验，SHALL 采用每 view 一对一匹配（min-cost）+ gate + ambiguity rejection：`residual ≤ pre_association_gate_ft` 且 second-best margin 足够（> `ambiguity_margin`）→ strong candidate；否则 `ambiguous`。`PreAssociationCandidate` SHALL 含 `matched_global_id / residual_ft / match_status / ambiguity_margin / projection_status / intrinsic_quality / origin`。pre-association SHALL 只读 `GlobalState(t-1)` 预测（与 guidance 同源），MUST NOT 产生 AssociationUpdate、MUST NOT 写 mapping。`GlobalPlayerAssociator.process_tick` 的算法、门限、候选晋升逻辑 SHALL 保持不变。

#### Scenario: 一对一匹配 + ambiguity rejection

- **WHEN** 某 candidate 与两个 global 预测的 residual 均 ≤ gate 且 margin 不足
- **THEN** 该 candidate SHALL 标记 `ambiguous`
- **AND** SHALL NOT 作为 same-tick donor（防双打 NVZ 密集时 P1/P2 互换）

#### Scenario: 归属先验不写 mapping

- **WHEN** pre-association 判定某 raw candidate 大概率属于 P1
- **THEN** 该判定 SHALL 只作为 same-tick ROI 决策的输入
- **AND** SHALL NOT 修改 mapping / 产生 AssociationUpdate / 影响 process_tick 内部状态

#### Scenario: 正式关联仍走 process_tick

- **WHEN** same-tick 补检形成新的 formal observation
- **THEN** 该 observation SHALL 由现有 `GlobalPlayerAssociator.process_tick` 正式关联
- **AND** 关联算法与门限 SHALL 与实施前一致
