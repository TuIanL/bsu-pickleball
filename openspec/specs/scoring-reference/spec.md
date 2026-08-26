# scoring-reference Specification

## Purpose
Define versioned scoring reference profiles and auditable single-metric utility mappings without introducing an overall score model.
## Requirements
### Requirement: Versioned scoring reference profile

系统 SHALL 定义独立的 `scoring-reference-profile.v1` 配置契约。每个 profile SHALL 包含 `reference_version`、`reference_mode`、适用指标、参数、最低样本、fallback 行为、声明文本和 profile hash；其语义 SHALL 与既有 Insights `product_reference_v1` 隔离。profile SHALL 明确声明其为产品参考、专家阈值或经验参考，不得宣称为专业标准。

#### Scenario: 使用专家参考 profile

- **WHEN** normalized metric 使用 `reference_mode = expert_threshold`
- **THEN** profile SHALL 提供对应 metric 的参数、方向和版本
- **AND** normalized artifact SHALL 保存 `reference_version` 和 `scoring_reference_hash`

#### Scenario: profile 缺少指标参数

- **WHEN** 某指标没有当前 profile 的可用参数
- **THEN** 该指标 SHALL 不能生成 utility score
- **AND** `score_eligibility` SHALL 为 `unsupported` 或 `display_only`
- **AND** SHALL 记录 `reference_profile_missing`

### Requirement: Reference mode semantics

profile SHALL 支持 `expert_threshold`、`target_range` 和 `empirical_percentile` 三种 reference mode。`empirical_percentile` 只有在 profile 声明 population、cohort、样本量、计算版本和可复现分布快照时才可使用；不存在这些信息时 percentile SHALL 为 `null`。

#### Scenario: 没有经验参考人群

- **WHEN** profile 为 expert threshold 且没有 empirical population
- **THEN** 系统 SHALL 允许生成 utility_score（若其他资格满足）
- **AND** percentile SHALL 保持 `null`

#### Scenario: 经验百分位缺少 cohort

- **WHEN** profile 声称使用 empirical percentile 但缺少 cohort 或分布快照
- **THEN** 系统 SHALL 将 reference 视为不可用
- **AND** SHALL NOT 合成或猜测 percentile

### Requirement: Direction and threshold mapping

profile SHALL 为每个可评分 metric 明确方向和映射方式。`higher_better`、`lower_better` SHALL 支持有界或分段阈值；`target_range` SHALL 支持目标区间和区间外惩罚；`context_dependent` SHALL 要求上下文选择器；`descriptive_only` SHALL 禁止 utility 映射。

#### Scenario: 高值较好

- **WHEN** metric direction 为 `higher_better` 且 raw/canonical value 位于 profile 定义范围内
- **THEN** utility_score SHALL 按 profile 的单调映射计算并限制在 `[0,1]`
- **AND** SHALL 保留原始值和映射参数版本

#### Scenario: 高值并非总是较好

- **WHEN** 指标 direction 为 `target_range`
- **THEN** 高于或低于目标区间的值 SHALL 根据偏离程度降低 utility
- **AND** SHALL NOT 将最大值自动映射为最高 utility

#### Scenario: 上下文选择器失败

- **WHEN** context-dependent 指标无法选择适用的比赛格式、角色或阶段 profile
- **THEN** utility_score SHALL 为 `null`
- **AND** SHALL 记录 `context_missing` 或 `reference_profile_missing`

### Requirement: Reference profiles are not overall score models

scoring reference profile SHALL 只负责单指标的评价参考和 utility 映射，不定义 Dimension Score、Overall Score、跨指标权重或最低整体覆盖门槛。后续 `performance-score.v1` SHALL 使用独立 schema 和独立版本定义这些行为。

#### Scenario: 规范化阶段不计算综合分

- **WHEN** normalized artifact 包含多个 eligible utility metrics
- **THEN** 系统 SHALL 输出各指标的 utility 和 coverage 信息
- **AND** SHALL NOT 生成 dimension_score、overall_score 或 0–100 用户评分

#### Scenario: 参考 profile 变更

- **WHEN** profile 从 v1 更新为 v2 且输入 metric snapshot 不变
- **THEN** 系统 SHALL 能仅重生成 normalized artifact
- **AND** SHALL NOT 触发视觉 pipeline 或假定历史整体分数自动保持不变

### Requirement: Reference configuration auditability

每个启用的参考参数 SHALL 可追溯到 `reference_version`、定义来源、发布时间或生成时间、profile hash 和适用范围。系统 SHALL 区分产品专家阈值、经验分布和未来人工校准参数，禁止将任一模式表述为专业标准。

#### Scenario: 产品参考文案

- **WHEN** normalized metric 使用专家阈值
- **THEN** artifact 和后续消费者 SHALL 能读取 reference source 文案
- **AND** 文案 SHALL 表述为产品参考基准，而不是行业或专业标准

#### Scenario: 参考 profile 可复核

- **WHEN** 复核者拿到 reference_version 和 profile hash
- **THEN** 系统 SHALL 能定位当时使用的 profile 参数
- **AND** SHALL 能解释 utility_score 的映射来源
