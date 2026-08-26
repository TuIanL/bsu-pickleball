## Why

当前系统已经能够从 canonical shot/rally events 生成带证据引用的描述性 Metric Snapshot，但还没有把“测量事实”“评价参考系”和“能力分数”分开的契约。若直接把 PB Vision 的 raw metric 或 `coach_advice.value` 加权成分数，容易把未校准的排名、检测质量或低样本比例误认为球员能力。现在需要先建立可版本化的指标定义、评分资格和参考配置，为后续 `performance-score.v1` 提供稳定输入。

## What Changes

- 新增 `metric-normalization.v1` 能力，将现有 Metric Snapshot 中的指标表达为明确的 `raw_value`、`canonical_value`、单位、方向、样本充分度、证据引用和可评分资格。
- 新增 `scoring-reference-profile.v1` 能力，独立描述指标方向、参考模式、专家阈值、目标区间、最小样本和 fallback 行为；不复用既有 Insights 的 `product_reference_v1` 语义。
- 派生 `score_eligibility`，区分 `eligible`、`display_only`、`insufficient_evidence`、`not_applicable`、`unsupported` 和 `failed`，并保留可解释的 `eligibility_reasons`。
- 生成可重新计算的 normalized metric artifact，并保留 `raw_value`、`canonical_value`、`utility_score` 和 `percentile` 的语义边界；本 change 不生成用户可见的 Dimension Score 或 Overall Score。
- 仅允许经过指标白名单和证据资格校验的字段进入规范化；PB Vision 中存在但当前 canonical artifact 未可靠提供的字段继续标记为 `unsupported` 或 `display_only`。
- 扩展分析产物路径、Pipeline result 和 artifact API，使 normalized metric artifact 可选、可追溯且不破坏旧 job。
- **不修改**既有 `product_reference_v1` 的 Insights 阈值语义，不把 `ShotQuality.score`、`coach_advice.value` 或 PB Vision 的隐含排名参数直接当作技能评分。

## Capabilities

### New Capabilities

- `metric-normalization`: 定义 raw/canonical/utility/percentile 的分层指标契约、单位、方向、证据资格和样本充分度。
- `scoring-reference`: 定义版本化的专家阈值、目标区间、参考模式和 fallback 配置，为后续维度评分提供评价参考系。

### Modified Capabilities

- `analysis-artifacts`: 增加 normalized metric artifact 的可选路径、状态、API 和旧任务兼容要求。

## Impact

- 后端新增 normalized metric schema、reference profile 配置、规范化服务和产物持久化流程。
- 扩展 `AnalysisPipelineResult.artifacts`、artifact path resolver 和分析产物 API。
- 前端只需新增类型和证据读取边界；本 change 不要求渲染最终评分 UI，也不恢复旧 `skillRatings`。
- 后续 `performance-score.v1` 将消费本 change 的 normalized metric artifact 和 scoring reference version，并独立定义 Dimension Score、Overall Score、权重与覆盖门槛。
- 需要覆盖低样本、空分母、`null` 与 `0`、上下文指标、单打不适用、候选证据和重复生成一致性测试。
