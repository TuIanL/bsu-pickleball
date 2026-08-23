## ADDED Requirements

### Requirement: 热力图消费身份可信样本
zone heatmap、position heatmap 与 scatter plot SHALL 只消费正式 canonical trajectory 中 `confirmed_observed`、`confirmed_recovered`、`interpolated` 样本，并按球员返回 accepted/quarantined sample count、coverage 与 data sufficiency。下游 MUST NOT 从 raw track ID 或隔离样本重新推断 P 编号。

#### Scenario: P2 轨迹包含跨侧污染样本
- **WHEN** P2 quarantine diagnostics 含落在 P3/P4 side 的 cross-side samples
- **THEN** 这些样本 SHALL NOT 出现在 P2 热力图或散点图
- **AND** P2 统计 SHALL 显示 quarantined count 与覆盖不足提示

#### Scenario: 隔离后数据不足
- **WHEN** P2 accepted coverage 低于 sufficiency threshold
- **THEN** 前端 SHALL 显示“身份可信样本不足”
- **AND** SHALL NOT 把稀疏点计算结果呈现为确定表现结论

