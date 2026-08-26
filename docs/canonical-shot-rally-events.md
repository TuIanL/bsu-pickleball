# Canonical Rally/Shot 事实层交接说明

本 change 生成两个 job 级 JSON artifact：

- `shot-rally-events.v1`：从 `reconstructed_ball_trajectory.v2`、serve events、球员 roster 和人工 rally 时间轴组合出的去重 Shot/Rally 事实。
- `metric-snapshot.v1`：从 canonical 事件确定性聚合出的描述性指标，保存 `numerator`、`denominator`、`sample_count`、状态、来源和证据 ID。

## 消费约束

1. 真实 job 的报告证据只读取 canonical events 和 Metric Snapshot；缺失、低样本、未适用和失败都保持显式状态。
2. `Player_N`、`rally_id`、`shot_id` 和 `ordinal_in_rally` 是关联主键，不得使用展示名称、数组下标或 track_id 尾号替代。
3. 没有权威 rally 边界时，Shot 仍可作为全局事实保留，但 `rally_id` 与 `ordinal_in_rally` 必须为 `null`。
4. trajectory、bounce 和空间字段是证据或描述，不自动升级为落点、得分、失误或技能结论。

## 后续 performance-score.v1 的输入边界

后续评分 change 可以消费：

- 已确认归属的 Shot/Rally 事件；
- Metric Snapshot 的分子、分母、样本量和充分度状态；
- `evidence_windows` 对应的视频时间窗；
- `product_reference_v1` 及未来经教练标注/跨场次数据校准的版本化配置。

后续评分 change 必须另行定义评分维度、权重、校准集、置信区间和跨场次聚合规则。当前 artifact 不输出 DUPR、Skill Rating、0–10 或 2.0–8.0 技能分，也不得把 `insufficient_evidence` 或 `null` 转成 0 分。
