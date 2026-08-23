## ADDED Requirements

### Requirement: Canonical 样本身份状态与隔离
球员轨迹生成 SHALL 为样本判定 `confirmed_observed`、`confirmed_recovered`、`interpolated`、`ambiguous`、`duplicate`、`cross_side` 或 `unresolved`。只有前三类 SHALL 进入正式 canonical trajectory 与 metrics；其余 SHALL 写入 quarantine diagnostics。

#### Scenario: P2 candidate 位于 P3/P4 对侧
- **WHEN** 标为 P2 的 candidate 违反 frozen side mapping 且没有受控换边/恢复证据
- **THEN** 样本 SHALL 标记 `cross_side` 并隔离
- **AND** SHALL NOT 写入 P2、P3 或 P4 的正式轨迹

#### Scenario: 同一 P 槽位短缺口插值
- **WHEN** 同一 canonical player 的前后 confirmed sample 之间存在短缺口且未跨 identity epoch/side
- **THEN** 系统 MAY 生成 `interpolated` 样本
- **AND** MUST NOT 在两个不同 source identity 之间插值

