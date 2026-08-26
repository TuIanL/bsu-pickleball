# metric-normalization Specification

## Purpose
Define versioned metric definitions, normalized metric artifacts, eligibility semantics, evidence provenance, and deterministic regeneration for analysis metrics.
## Requirements
### Requirement: Metric definition and whitelist

系统 SHALL 为每个可规范化指标提供版本化 Metric Definition，至少声明 `metric_key`、单位、canonical 来源字段、适用 scope、适用赛制、`metric_direction`、是否 `descriptive_only`、所需语义级别和最小证据条件。规范化服务 SHALL 只处理白名单中的指标；PB Vision 存在但当前 canonical artifact 没有可靠来源的指标 SHALL 标记为 `unsupported` 或 `display_only`，不得猜测或伪造输入。

#### Scenario: 当前 canonical 指标进入白名单

- **WHEN** `metric-snapshot.v1` 中存在已定义来源、单位和 scope 的指标
- **THEN** 规范化服务 SHALL 生成对应 normalized metric entry
- **AND** entry SHALL 记录其 definition version 和 source metric ID

#### Scenario: PB Vision 指标尚无可靠来源

- **WHEN** PB Vision rawdata 含有 `return_depth`，但当前 canonical artifact 没有可审计的 return depth metric
- **THEN** 该指标 SHALL 为 `unsupported` 或 `display_only`
- **AND** 系统 MUST NOT 从相邻轨迹、数组位置或 PB Vision rawdata 猜测出可评分值

#### Scenario: 上下文无法证明

- **WHEN** 指标的 `metric_direction` 为 `context_dependent` 且比赛格式、角色或阶段上下文缺失
- **THEN** 该指标 SHALL NOT 获得 `eligible` 资格
- **AND** SHALL 记录 `context_missing` 之类的 `eligibility_reasons`

### Requirement: Normalized metric artifact envelope

系统 SHALL 为完成或明确降级的真实分析任务生成可选的 `normalized_metrics.json`，schema SHALL 为 `normalized-metric-snapshot.v1`。artifact SHALL 包含 `job_id`、`status`、`detail`、`generated_at`、输入 artifact 引用、`metric_definition_version`、`evidence_sufficiency_version`、`scoring_reference_version`、`scoring_reference_hash`、`metrics`、`score_coverage` 和 `diagnostics`。该 artifact SHALL 是 `metric-snapshot.v1` 的派生结果，不得覆盖或修改输入文件。

#### Scenario: 规范化产物成功生成

- **WHEN** 真实 job 有可读的 `metric-snapshot.v1` 和对应 definition/profile
- **THEN** 系统 SHALL 写入 `normalized_metrics.json`
- **AND** payload SHALL 声明 `schema_version = "normalized-metric-snapshot.v1"`
- **AND** SHALL 保留输入 artifact 的 job、metric 和 evidence 关联

#### Scenario: 输入指标不可用

- **WHEN** `metric-snapshot.v1` 为 `unavailable`、`failed` 或未生成
- **THEN** normalized artifact SHALL 显式记录对应状态和原因
- **AND** SHALL NOT 生成默认 utility 或用户评分

### Requirement: Separate value semantics

每个 normalized metric entry SHALL 分别表达 `raw_value`、`canonical_value`、`utility_score` 和 `percentile`，不得使用一个 `normalized_value` 字段承载多种语义。`utility_score` SHALL 为内部 `[0,1]` 值，`percentile` SHALL 为 `[0,100]` 或 `null`；本 change SHALL NOT 生成 `dimension_score` 或 `overall_score`。

#### Scenario: 有专家参考但无群体参考

- **WHEN** 指标有可用原始值和专家阈值，但没有 empirical population
- **THEN** entry SHALL 可以生成 `canonical_value` 和 `utility_score`
- **AND** `percentile` SHALL 为 `null`
- **AND** artifact SHALL 标记实际 `reference_mode`

#### Scenario: 内部 utility 不冒充用户分数

- **WHEN** entry 的 `utility_score` 为 `0.71`
- **THEN** API 和前端类型 SHALL 将其标记为内部规范化值
- **AND** SHALL NOT 将其投影为 71/100、0–10 或 PB Vision 技能评分

### Requirement: Direction and context semantics

Metric Definition SHALL 支持 `higher_better`、`lower_better`、`target_range`、`context_dependent` 和 `descriptive_only`。`descriptive_only` 指标 SHALL 保留 canonical value 供展示或后续研究，但 SHALL NOT 生成 utility score；`target_range` SHALL 以目标区间而非简单单调方向计算。

#### Scenario: 描述性移动负载

- **WHEN** 指标为 `total_distance_covered` 且 Definition 将其标记为 `descriptive_only`
- **THEN** 系统 SHALL 保留其 raw/canonical value 和 evidence
- **AND** SHALL 将 `score_eligibility` 标记为 `display_only`
- **AND** SHALL NOT 因距离更大就生成更高能力分

#### Scenario: 目标区间指标

- **WHEN** 指标被定义为 `target_range` 且 canonical value 落在目标区间内
- **THEN** utility 计算 SHALL 依据距离目标区间的偏离程度
- **AND** SHALL NOT 默认采用“越高越好”方向

### Requirement: Derived score eligibility and sufficiency

规范化服务 SHALL 根据输入 artifact status、Metric Definition、evidence semantic level、rule eligibility、比赛上下文、sample_count、分母和参考 profile 派生 `score_eligibility`。允许值 SHALL 包含 `eligible`、`display_only`、`insufficient_evidence`、`not_applicable`、`unsupported` 和 `failed`；非 `eligible` 条目 SHALL 携带一个或多个 `eligibility_reasons`。

#### Scenario: 样本不足

- **WHEN** 指标有值但 sample_count 低于其 Evidence Sufficiency Profile 的最小值
- **THEN** entry SHALL 保留 raw/canonical value（若可证明）
- **AND** `score_eligibility` SHALL 为 `insufficient_evidence`
- **AND** `utility_score` SHALL 为 `null`

#### Scenario: 空分母

- **WHEN** 指标 denominator 为 0 或没有可定义的机会样本
- **THEN** entry SHALL 为 `not_applicable` 或 `insufficient_evidence`
- **AND** SHALL NOT 将 value 或 utility 转换为 0

#### Scenario: 单打不适用双打指标

- **WHEN** `match_format = singles` 且指标为双打协同
- **THEN** entry SHALL 为 `not_applicable`
- **AND** SHALL 记录 `singles_not_applicable`

#### Scenario: 候选证据不可评分

- **WHEN** 指标唯一证据为 `semantic_level = candidate` 或 `rule_eligibility = display_only`
- **THEN** `score_eligibility` SHALL NOT 为 `eligible`
- **AND** SHALL 记录候选证据被排除的原因

### Requirement: Evidence and deterministic regeneration

每个 normalized metric SHALL 保留 source metric ID、source artifact、evidence IDs、provenance、definition/profile 版本和计算版本。相同的 canonical input、Definition、Sufficiency Profile、Scoring Reference 和 calculation version SHALL 生成相同的 metric IDs、字段值、状态和排序（`generated_at` 除外）。不存在的 evidence ID SHALL NOT 写入 normalized artifact。

#### Scenario: 重复生成一致

- **WHEN** 同一个 job 使用相同输入和 profile 重新生成 normalized artifact
- **THEN** 除 `generated_at` 外 payload SHALL 逐字段一致
- **AND** metrics、diagnostics 和 reason 列表 SHALL 保持稳定排序

#### Scenario: 证据 ID 悬空

- **WHEN** 某 metric 引用的 event 或 source artifact 无法解析
- **THEN** entry SHALL 降级为 `failed` 或 `unsupported`
- **AND** SHALL NOT 保留悬空 evidence ID 作为可用证据

### Requirement: Shot quality and PB Vision advice are not formal score inputs

首版规范化 SHALL 将 `ShotQuality.score`、PB Vision `coach_advice.value`、`relevance`、`avg_rank` 和检测置信度视为描述或候选信号，除非未来独立校准并加入白名单，否则 SHALL NOT 让它们单独产生 `eligible` 的正式能力评分输入。

#### Scenario: 轨迹质量与击球质量同时存在

- **WHEN** 某 Shot 同时有 trajectory confidence 和 ShotQuality.score
- **THEN** normalized artifact SHALL 保留二者的来源和语义
- **AND** SHALL NOT 将任一字段直接当作球员 Dimension Score

#### Scenario: PB Vision advice 未知参考系

- **WHEN** 导入 PB Vision `avg_rank` 或 `coach_advice.value` 但没有其 reference population 和 calculation contract
- **THEN** 该值 SHALL 只能作为 display-only 外部事实
- **AND** SHALL NOT 进入本 change 的 utility 计算
