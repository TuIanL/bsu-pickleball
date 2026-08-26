## Context

当前系统已经归档了 `shot-rally-events.v1` 和 `metric-snapshot.v1`。前者保存去重后的 Shot/Rally 事实，后者保存带分子、分母、样本量和 evidence ID 的描述性指标。`metric-snapshot.v1` 的 `product_reference_v1` 只承担现有产品阈值和样本充分度语义；`performance-insights.v1` 另有同名的产品诊断阈值，且明确禁止未经校准的数值技能评分。

PB Vision 的 rawdata 展示了从事件到大量派生指标、排名/参考和建议的分层结构，但其 JSON 没有可复制的 Rating 参数；Excel 在当前短样本下将 Rating 显示为 `N/A`。因此本 change 只建立从描述性指标到“可评价输入”的中间层，不实现最终 Dimension Score 或 Overall Score。

## Goals / Non-Goals

**Goals:**

- 定义 metric definition、证据资格、样本充分度和评价方向的稳定契约。
- 将 `raw_value`、`canonical_value`、`utility_score` 和 `percentile` 分开表达。
- 提供版本化 `scoring-reference-profile.v1`，支持专家阈值、目标区间和未来经验百分位。
- 派生可解释的 `score_eligibility`，并保留缺失原因、参考版本、置信度和 evidence IDs。
- 只对白名单中具有可靠 canonical 来源的指标生成规范化结果；PB Vision 专有或当前来源不足的指标显式降级。
- 让规范化结果可以从已落盘 artifact 确定性重生成，不重跑视觉 pipeline。

**Non-Goals:**

- 不生成 `performance-score.v1`、Dimension Score、Overall Score 或长期 `player-skill-rating.v1`。
- 不修改既有 `product_reference_v1` 的 Insights 或 Metric Snapshot 语义。
- 不把 `ShotQuality.score`、`coach_advice.value`、检测置信度或 PB Vision 的隐含 rank 参数直接当作球员能力分。
- 不为当前 canonical artifact 尚未证明的 `serve_legal_rate`、`fault_rate`、`return_depth` 等 PB Vision 指标伪造输入。
- 不恢复或改造旧 `skillRatings` UI，不将内部 `utility_score=0.71` 直接展示为 71 分。

## Decisions

### 1. 保持输入不可变，新增派生 normalized artifact

`metric-snapshot.v1` 作为唯一描述性输入，不在原文件上追加评分字段。新增 `normalized-metric-snapshot.v1` 保存规范化结果、资格状态和参考 profile 版本。这样可以在不重跑视觉分析的情况下更换参考 profile 并重新生成。

备选方案是直接扩展 Metric Snapshot。该方案会把事实聚合、评价参考和规范化结果耦合在同一版本中，导致历史指标无法按新参考系重算，因此不采用。

### 2. 用三个职责明确的注册表替代万能配置对象

- `MetricDefinitionProfile`：定义 metric key、单位、来源字段、上下文、方向、是否描述性、适用赛制和可接受语义。
- `EvidenceSufficiencyProfile`：定义最小样本、分母规则、覆盖率、空分母和低样本降级行为。
- `ScoringReferenceProfile`：定义参考模式、专家阈值/目标区间、经验参考人群、映射参数、fallback 和版本。

三者通过 `metric_key` 和版本字段关联，但不互相替代。当前 change 可以将前两个作为后端配置，并将 scoring reference 的快照版本和 hash 写入 normalized artifact。

备选方案是一个包含所有字段的 `ScoringReference` 对象。该方案会把“指标是什么”“数据够不够”和“什么算好”混在一起，难以审计和迁移，因此不采用。

### 3. 明确五种数值语义，禁止复用 normalized_value

规范化条目分别表达：

- `raw_value`：上游实际产出的值；
- `canonical_value`：单位和表示形式统一后的测量事实；
- `utility_score`：参考规则映射到 `[0, 1]` 的内部效用值；
- `percentile`：在明确参考人群中的相对位置，缺少人群时为 `null`；
- `dimension_score`：本 change 不生成的用户可见维度分。

`utility_score` 只作为后续评分输入，不能被报告投影层当作能力评分展示。

### 4. 采用白名单和上下文方向

metric definition 必须显式声明 `metric_direction`，至少支持 `higher_better`、`lower_better`、`target_range`、`context_dependent` 和 `descriptive_only`。`context_dependent` 在上下文无法证明时只能进入 `display_only` 或 `unsupported`，不得默认按“越高越好”计算。

初始白名单以当前 canonical artifact 实际提供并可证明的字段为准。PB Vision rawdata 中存在但本系统没有可靠 canonical 来源的指标只记录为 planned/unsupported，不进入 utility 计算。

备选方案是对所有 Metric Snapshot 条目自动使用单调归一化。该方案会误把移动负载、NVZ occupancy、平均速度等上下文指标变成能力分，因此不采用。

### 5. score_eligibility 是派生状态，不是新的事实来源

规范化服务读取已有的 `status`、`provenance`、evidence semantic level、rule eligibility、样本和比赛上下文，派生：

`eligible`、`display_only`、`insufficient_evidence`、`not_applicable`、`unsupported`、`failed`。

每个非 eligible 条目必须保留 `eligibility_reasons`，例如 `sample_count_below_minimum`、`zero_denominator`、`semantic_level_candidate`、`singles_not_applicable` 或 `reference_profile_missing`。该状态不替代已有 artifact status，也不改变原始 evidence 的语义。

### 6. 首版使用版本化专家参考，预留经验百分位但不伪造群体数据

`scoring-reference-profile.v1` 支持 `expert_threshold`、`target_range` 和 `empirical_percentile` 模式。首版只能启用有明确参数的专家参考；没有参考人群时 `percentile` 必须为 `null`，不得使用 PB Vision 的隐含 rank 或自行生成群体分布。未来经验参考必须携带 population、cohort、样本量、生成版本和 profile hash。

### 7. 整体评分门槛留给后续 performance-score change

本 change 输出 `score_coverage`、适用维度/指标和缺失原因，但不计算综合分。后续 `performance-score.v1` 再定义维度权重、`eligible_weight_coverage`、最小维度数量、区间和 UI 语义。

## Risks / Trade-offs

- [Risk] 当前 canonical metric dictionary 较小，第一版可能只有少量可规范化指标。→ [Mitigation] 以 `unsupported`/`display_only` 显式表达，先扩展可靠事实来源，再加入 reference entry。
- [Risk] 专家阈值会带有人为偏差。→ [Mitigation] 所有阈值必须版本化、声明为产品参考基准，并保留原始值；未来可切换经验 percentile。
- [Risk] `0`、`null`、空分母和低样本语义混淆。→ [Mitigation] schema 校验 numerator/denominator、status/value 一致性，并为每个降级状态提供 reason。
- [Risk] 上游候选 evidence 被误用于评分。→ [Mitigation] 入口读取现有 semantic level/rule eligibility，候选或 display-only evidence 不能成为 eligible 指标的唯一证据。
- [Risk] 参考 profile 更新导致历史规范化结果变化。→ [Mitigation] 每份 artifact 保存 reference version、profile hash、calculation version，并支持按旧版本重生成。
- [Risk] normalized artifact 被前端误当成最终分数。→ [Mitigation] 明确 `utility_score` 的内部语义，暂不接入现有评分 UI，并在 API/类型测试中禁止暴露 Dimension/Overall Score 字段。
