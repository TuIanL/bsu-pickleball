# Metric Normalization → performance-score.v1 交接说明

本文档定义当前 `metric-normalization-and-scoring-reference` change 与后续
`performance-score.v1` 的接口边界。当前实现只生成 metric-level 的规范化输入，
不会生成维度分或总分。

## 输入与输出

- 输入：`metric-snapshot.v1`，可选 `shot-rally-events.v1` 用于 evidence 校验。
- 输出：`normalized-metric-snapshot.v1`，写入 job artifact 目录的
  `normalized_metrics.json`。
- API：`GET /api/analysis/jobs/{job_id}/artifacts/normalized-metrics`。
- 前端读取：`getNormalizedMetrics(result)`；当前不接入旧的 `skillRatings` 或最终评分 UI。

每个 normalized metric 保留 `raw_value`、`canonical_value`、单位、分子/分母、
样本数、来源 metric ID、evidence IDs、provenance、定义版本、充分度版本和参考版本。
`utility_score` 与 `percentile` 是两个独立字段：percentile 不能替代 utility，也不能
在没有真实参考人群分布时被合成。

## 当前首版边界

默认白名单只登记当前 canonical artifact 能证明来源的指标：

- `shot_count`
- `rally_count`
- `serve_count`
- `return_count`
- `third_shot_count`
- `shot_quality_mean`
- `doubles_cooperation`

这些指标当前均为 `descriptive_only`，因此默认只会得到 `display_only`，不会得到正式
utility。PB Vision 的 `coach_advice.value`、`avg_rank`、ShotQuality 单次分数以及检测
置信度不会自动获得评分资格；未进入白名单的指标为 `unsupported`。

## performance-score.v1 的消费约束

后续评分层只能消费同时满足以下条件的 entry：

1. `score_eligibility == "eligible"`；
2. `canonical_value`、单位、方向和参考模式均已通过校验；
3. evidence IDs 能在输入 artifact 中解析，且 provenance 不是 candidate/display-only；
4. 样本数、分母和覆盖率满足 `evidence-sufficiency-profile.v1`；
5. `scoring-reference-profile.v1` 中存在同一 metric 的显式参考配置，且方向匹配。

评分层应把 `utility_score` 视为单指标效用输入，并自行定义维度聚合、缺失指标处理、
置信度展示和版本化审计。`normalized-metric-snapshot.v1` 不提供
`dimension_score`、`overall_score` 或用户等级字段，因此任何总分模型都必须另建
`performance-score.v1` 契约，不得把现有 descriptive metric 直接加权求和。

## Reference profile 使用规则

`scoring-reference-profile.v1` 支持三种模式：

- `expert_threshold`：显式提供上下界，并按指标方向映射到 `[0, 1]`；
- `target_range`：目标区间内为满效用，区间外按显式边界衰减；
- `empirical_percentile`：必须同时提供真实 `population`、`cohort` 和参考分布，缺失时
  `percentile` 与 `utility_score` 都保持空值。

每次生成都记录 reference version 与 profile hash。参考 profile 缺失或配置不一致时，
entry 会降级为 `unsupported`，不会阻塞视觉产物、report 或 insights。

## 评分覆盖率与降级

使用 `score_coverage` 判断本次输入是否足以进入后续评分：

- `eligible_metric_count`：当前可进入评分层的指标数；
- `missing_metric_keys`：所有非 eligible 指标及其 entry-level reasons；
- `insufficient_evidence`、`not_applicable`、`unsupported`、`failed` 分别保留，不能
  统一改写为 0 分。

`null`、空分母、低样本、赛制不适用和不可解析 evidence 都是不同语义。后续评分层应
  读取 eligibility，而不是把缺失值填充为零。

## 推荐的下一步

在拥有足够的标注样本、明确的球员分组和专家共识阈值后，再为少量指标新增显式
`MetricDefinition` 与 `MetricReference`。先验证单指标 utility 与 evidence，再设计
`performance-score.v1` 的维度聚合和最终评分展示。
