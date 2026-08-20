## ADDED Requirements

### Requirement: performance_insights 产物契约

系统 SHALL 为每个完成的真实分析任务生成 `performance_insights.json` 产物（schema `performance-insights.v1`），包含 `job_id`、`match_format`、`rule_profile_version`、`generated_at`、`evidence_input_signature`（Insight Engine 实际消费的 evidence 输入指纹，MUST NOT 复用 `AnalysisJobSummary.inputSignature`——job signature 描述输入视频与配置，无法感知 artifact 修复/重生成导致的 evidence 变化）、`data_quality`、`subjects`（canonical `Player_1`..`Player_4` 及双打 `team_near` / `team_far`）、`dimensions[]`、`evidence[]`、`findings[]`、`recommendations[]` 与可选 `primary_focus_finding_id`。维度整体状态 SHALL 由 `DimensionAssessment`（dimension / subject_id / status / confidence / evidence_ids / finding_ids / summary）表达，`status ∈ {strength, stable, needs_improvement, insufficient_evidence, not_applicable, unsupported}`；维度状态由 Rule Engine 权威输出，报告投影层 MUST NOT 自行推导。

#### Scenario: 真实任务生成洞察产物

- **WHEN** 一个 source=job 的分析任务完成且视觉产物落盘成功
- **THEN** 系统 SHALL 写入 `performance_insights.json`，且 `AnalysisReport`（source=job）SHALL 通过 projector 携带投影后的 `performanceInsights` 用户可读子集
- **AND** demo 任务 SHALL NOT 生成该产物（demo 报告继续走独立 demo builder）

#### Scenario: 洞察生成失败不拖垮报告

- **WHEN** insights 生成抛出异常或所需 artifact 缺失
- **THEN** 报告 SHALL 显式降级为"移动数据 + 洞察暂不可用"状态
- **AND** MUST NOT 回退填充 demo 性能结论，也 MUST NOT 导致整个报告请求失败

#### Scenario: 维度状态由 DimensionAssessment 权威表达

- **WHEN** Rule Engine 产出某 subject 的维度评估
- **THEN** 该维度状态 SHALL 记录在 `dimensions[]` 的 `DimensionAssessment.status`（6 态，含 `not_applicable` / `unsupported`）
- **AND** 单条 finding 的 `assessment` SHALL 保持 4 态（strength / stable / needs_improvement / insufficient_evidence），不承载维度级 not_applicable 语义
- **AND** 报告投影层 SHALL 直接展示维度状态，MUST NOT 综合多条 findings 自行推导维度结论

### Requirement: Evidence 可追溯性与 provenance

每条 performance finding SHALL 至少绑定 1 条真实 evidence；每条 evidence SHALL 能追溯到 `source_artifacts`（artifact 名列表）、`metric` 与可选时间窗，并携带 `provenance ∈ {pipeline_metric, structured_visualization, manual_timeline, fused_multiview, reference_view, derived_rule}`、`semantic_level ∈ {descriptive, confirmed, candidate}` 与 `rule_eligibility ∈ {eligible, display_only}`。所有用户可跳转时间 SHALL 以毫秒（`start_ms` / `end_ms`）为权威单位，底层 `timestamp_seconds` 在 Evidence Assembler 边界统一转换。

#### Scenario: Finding 绑定证据

- **WHEN** Rule Engine 输出一条 assessment 不为 `insufficient_evidence` 的 finding
- **THEN** 该 finding 的 `evidence_ids` MUST 非空，且每个 id 能在 `evidence[]` 中解析到对应记录

#### Scenario: 候选证据被规则引擎排除

- **WHEN** 一条 evidence 标注 `semantic_level = candidate` 且 `rule_eligibility = display_only`（如 bounce/ball 候选）
- **THEN** InsightRuleEngine SHALL 在入口统一过滤该 evidence，任何规则 MUST NOT 消费它产出 finding
- **AND** 该 evidence MAY 仅用于报告的算法候选事实展示区

#### Scenario: 双摄 provenance 区分

- **WHEN** Insight Engine 消费双摄任务的产物
- **THEN** 其输入 MUST 仅为 public Parent 的最终产物，MUST NOT 直接读取 internal child 自行拼装
- **AND** 来自参考机位的 evidence SHALL 标注 `provenance = reference_view`，来自融合轨迹的 evidence SHALL 标注 `provenance = fused_multiview`

#### Scenario: 时间单位统一

- **WHEN** Evidence 携带时间窗
- **THEN** `start_ms` / `end_ms` SHALL 为毫秒整数，前端可直接用于 `/analysis/{job_id}/vision?t={ms}` 跳转
- **AND** Rule Engine 内部 MUST NOT 出现秒/毫秒混用

### Requirement: 数据不足与适用性降级

Rule Engine SHALL 在数据不充分时输出 `assessment = insufficient_evidence` 而不是硬算结论；维度不适用时在 `DimensionAssessment.status` 输出 `not_applicable`：单打任务的双打协同维度 MUST 为 `not_applicable`；某类数据（球/弹跳/姿态）缺失时对应维度 SHALL 降级（`insufficient_evidence` 或 `unsupported`），MUST NOT 导致整个洞察产物失败。

#### Scenario: 轨迹覆盖率不足

- **WHEN** 某球员 `tracked_seconds / denominator_seconds` 低于数据充分性阈值
- **THEN** 该球员相关 finding 的 assessment SHALL 为 `insufficient_evidence` 或 confidence 降级
- **AND** UI SHALL 显示"数据有限"而非确定结论

#### Scenario: 单打任务

- **WHEN** `match_format = singles`
- **THEN** 双打协同类维度的 `DimensionAssessment.status` SHALL 输出 `not_applicable`
- **AND** 双打团队 scope（`team_near` / `team_far`）SHALL NOT 出现在 subjects 中

#### Scenario: 球数据缺失

- **WHEN** ball trajectory / bounce artifacts 为 skipped 或 unavailable
- **THEN** 落点相关维度 SHALL 显示"数据有限/暂不评价"
- **AND** 移动类维度 findings MUST NOT 受影响

### Requirement: 版本化规则与确定性再生成

洞察规则 SHALL 以版本化 `rule_profile`（V1 为 `product_reference_v1` 阈值来源）在后端维护，每条规则声明适用赛制、所需 artifacts、最低数据覆盖率与触发阈值；Insight Engine SHALL 支持仅凭已落盘的 `result.json + artifacts` 独立再生成，无需重跑视觉 pipeline。相同输入 + 相同 `rule_profile_version` SHALL 产出相同的 dimensions / evidence / findings / recommendations（`generated_at` 除外）。产物 id SHALL 采用确定性命名（如 `ev:{subject}:{metric}:{window_start_ms}`、`finding:{rule_id}:{subject}`、`rec:{rule_id}:{subject}`），MUST NOT 使用随机 uuid；`subjects / dimensions / evidence / findings / recommendations` SHALL 固定排序。

#### Scenario: 规则版本升级再生成

- **WHEN** rule_profile 从 v1 升级到 v2 且视觉产物不变
- **THEN** 系统 SHALL 仅重新生成 `performance_insights.json` 与报告投影
- **AND** MUST NOT 触发任何视觉分析阶段重跑

#### Scenario: 确定性回归

- **WHEN** 同一 job 的同一组输入产物用同一 `rule_profile_version` 重新生成洞察
- **THEN** 除 `generated_at` 外的产物内容 SHALL 逐字段一致
- **AND** 所有 id SHALL 保持稳定，集合排序 SHALL 一致

#### Scenario: 阈值来源标注

- **WHEN** 规则触发输出 finding 或建议文案
- **THEN** 文案与产物 SHALL 标注 `threshold_source`（V1 为产品参考基准）
- **AND** MUST NOT 表述为"专业标准"或同水平规范数据

### Requirement: 真实报告零 demo 结论

source=job 的报告 SHALL 端到端（后端构建、API 响应、前端渲染与降级路径）不包含任何 demo 性能结论；real report 构建模块 MUST NOT import `DEMO_REPORT` 或 `demoAnalysisReport`。

#### Scenario: 构建层隔离

- **WHEN** real report builder / projector / insights 链路的模块被加载
- **THEN** import 守卫测试 SHALL 断言这些模块不引用 demo 报告常量

#### Scenario: 前端降级路径

- **WHEN** real job 的 `GET /report` 请求暂无报告或失败
- **THEN** 前端 SHALL 显示"报告生成中 / 报告加载失败"显式状态
- **AND** MUST NOT 以 demo 数据或前端自行拼装的近似报告兜底

### Requirement: 禁止未校准评分与伪造趋势

V1 洞察 SHALL 只输出维度状态（待改进 / 稳定 / 数据有限 / 暂不评价）与文本 finding，MUST NOT 输出数值技能评分、等级分（如 "8.3 分" / "3.7 级"）或未经跨场次数据支撑的历史提升百分比；训练目标 SHALL 仅包含本次 baseline 与下次 target。

#### Scenario: 维度卡片无数值分

- **WHEN** Performance Report 展示六维表现
- **THEN** 每个维度 SHALL 展示状态与证据充分度标识
- **AND** MUST NOT 展示未校准的数值评分或雷达分值

#### Scenario: 无伪造趋势

- **WHEN** 系统尚无稳定的运动员跨场次身份档案
- **THEN** 报告 SHALL NOT 展示"较上次提升 X%"类历史对比
- **AND** 训练建议 SHALL 只包含本次 baseline 与下一次可度量 target
