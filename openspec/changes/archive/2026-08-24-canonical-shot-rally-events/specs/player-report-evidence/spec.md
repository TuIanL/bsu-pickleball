## ADDED Requirements

### Requirement: Player Report consumes canonical event evidence

真实 job 的 Player Report SHALL 优先从 `shot-rally-events.v1` 和 `metric-snapshot.v1` 组装逐拍证据与聚合指标。报告组件 SHALL 继续只使用 canonical `Player_N` 关联球员，并 SHALL NOT 直接拼接散落的 tracking、trajectory 或 mock 字段作为第二数据源。

#### Scenario: 事件产物可用

- **WHEN** 真实 job 存在可读的 canonical 事件和指标 artifact
- **THEN** Player Report Evidence SHALL 从这些 artifact 生成 `ShotEvidence`、发接发统计、回合统计和空间/质量指标
- **AND** 每个 available 指标 SHALL 携带 provenance 和 evidence 引用

#### Scenario: 事件产物不可用

- **WHEN** canonical artifact 为 unavailable、failed 或未生成
- **THEN** 报告 SHALL 显示对应指标的 unavailable/failed 状态和原因
- **AND** SHALL NOT 回退到 mock、展示名匹配、数组位置或硬编码默认值

### Requirement: Shot evidence exposes rally context

由 canonical 事件映射的 `ShotEvidence` SHALL 能表达 `shot_id`、`rally_id`、`ordinal_in_rally`、canonical `player_id`、阶段、击球类型、时间窗、质量、结果/错误（若可用）和来源引用。字段不可用时 SHALL 保留明确的不可用原因。

#### Scenario: 按第三拍筛选

- **WHEN** 用户选择第三拍过滤器
- **THEN** 报告 SHALL 按 `rally_id + ordinal_in_rally = 3` 筛选
- **AND** SHALL NOT 使用全局 shotRows 数组下标推断第三拍

#### Scenario: 未归属击球

- **WHEN** Shot 的 ownership status 为 ambiguous 或 unassigned
- **THEN** ShotEvidence SHALL 保留该 Shot 的时间和 rally context
- **AND** SHALL 不把它归入任意球员的个人统计

### Requirement: Metric Snapshot maps to strong evidence values

Metric Snapshot 中的每一项指标 SHALL 映射为 `EvidenceValue<T>`。`available` 必须携带 value、provenance、confidence（若有）和 numerator/denominator 事实；`insufficient_evidence`、`not_applicable`、`unavailable` 或 `failed` 必须携带 reason 且 value 为 null。

#### Scenario: 可审计的合法率

- **WHEN** 指标快照提供合法发球 numerator=8、denominator=10
- **THEN** Player Report SHALL 展示 80% 或等价格式
- **AND** SHALL 同时保留 8/10、样本量和证据引用

#### Scenario: 没有机会样本

- **WHEN** 指标 denominator=0 或低于最低样本阈值
- **THEN** Player Report SHALL 展示数据不足/不适用状态
- **AND** SHALL NOT 展示 0% 作为球员能力结论
