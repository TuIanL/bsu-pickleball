## ADDED Requirements

### Requirement: Candidate recovery funnel is part of four-player quality evidence

真实 doubles 的 `four-player-identification-quality.v1` SHALL 记录 candidate recovery 的 eligible、跨 tick 累积、accepted、ambiguous、rejected 和 expired 计数，并按 P1–P4 报告正式锚点是否确认。候选轨迹 SHALL NOT 被计入正式 P1–P4 coverage，除非它已通过既有 identity/association 门并归属于对应 canonical player。

#### Scenario: 质量产物反映候选恢复
- **WHEN** doubles Job 处理过 candidate evidence
- **THEN** 质量产物 SHALL 包含候选恢复漏斗计数、配置阈值和拒绝原因
- **AND** SHALL 区分正式 coverage 与候选命中

#### Scenario: 身份锚点未确认
- **WHEN** 某 canonical player 仍由 slot fallback 映射且无正式 reference binding
- **THEN** 质量产物 SHALL 将其 mapping 标记为 unconfirmed
- **AND** SHALL NOT 将候选命中计为正式覆盖或身份确认

#### Scenario: 历史产物兼容
- **WHEN** 历史 Job 没有 candidate recovery 字段
- **THEN** API SHALL 返回结构化 unavailable/partial reason
- **AND** SHALL NOT 将缺失字段表示为计数零
