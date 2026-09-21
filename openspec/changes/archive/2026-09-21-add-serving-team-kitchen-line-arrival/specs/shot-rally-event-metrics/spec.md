## MODIFIED Requirements

### Requirement: Metric Snapshot 分母感知

系统 SHALL 从 canonical 事件产物确定性生成 `metric_snapshot.json`，schema SHALL 为 `metric-snapshot.v1`。每条指标 SHALL 包含 `metric_key`、`subject_id`、`value`、`unit`、`numerator`、`denominator`、`sample_count`、`status`、`confidence`、`provenance`、`evidence_ids` 和 `calculation_version`。比例类指标 MUST 能由 numerator/denominator 审计；非 `available` 状态的比例指标 MUST 将 `value` 置为 null。

#### Scenario: 有效比例指标
- **WHEN** 某球员有 8 次合法发球且总发球机会为 10 次
- **THEN** Metric Snapshot SHALL 保存 numerator=8、denominator=10、value=0.8 或等价的明确单位表示
- **AND** SHALL 记录 sample_count=10 和对应的 Shot/Rally evidence IDs

#### Scenario: 分母为零
- **WHEN** 某球员在本场没有发球机会
- **THEN** 该指标 SHALL 使用 `not_applicable` 或 `insufficient_evidence`
- **AND** SHALL 将 value 置为 null
- **AND** MUST NOT 输出 0% 作为合法发球率

#### Scenario: 镜像厨房线到位率
- **WHEN** `kitchen-arrival.v1` 为某球员完成 raw serving-rally 汇总
- **THEN** Metric Snapshot SHALL 写入 `metric_key=serving_team_kitchen_line_arrival_rate`、`scope=player`、相同 numerator、denominator、sample_count、status 和 provenance
- **AND** 在 `insufficient_evidence`、`unavailable` 或 `not_applicable` 时 SHALL 使用 null value
- **AND** evidence_ids SHALL 只引用真实 context、identity audit、窗口计划或输入 artifact
