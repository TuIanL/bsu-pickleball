# player-report-evidence — Spec

> 本变更的 spec 聚焦新增能力 `player-report-evidence`。对既有能力 `pb-vision-style-report` / `interactive-performance-report` / `report-detail-pages` 的修改只会改变其"数据来源与可信度契约"，不新增视觉能力，故体现在本 spec 的共享受限要求中，不再重复单列；`multiview-global-player-roster` 仅被只读引用。

## Purpose

定义 Player Report 的证据来源、主体身份、指标可追溯性与 fail-closed 展示契约，确保报告只展示有权威依据的球员分析结果，并兼容演示数据与历史产物。
## Requirements
### Requirement: Player Report 主体仅限 canonical player
系统 SHALL 使 Player Report 的主体选择仅包含 `PerformanceSubject.kind === "player"` 的球员（id 形如 `Player_1..Player_4`）；team subject（`team_near` / `team_far`）SHALL NOT 进入报告主体选择器或默认主体，Team Report SHALL 由后续独立能力实现。

#### Scenario: team 不进入 Player Report
- **WHEN** 报告包含 `performanceInsights.subjects` 且其中含 `kind === "team"` 条目
- **THEN** player selector 与默认主体 SHALL 仅展示 `kind === "player"` 条目
- **AND** team 条目不得成为 `selectedSubject`

#### Scenario: 无 player subject 时
- **WHEN** 报告中没有任何 `kind === "player"` subject
- **THEN** 报告 SHALL 显示"暂无可用球员主体"或可用空态，而 SHALL NOT 把 team/占位主体当默认

### Requirement: 指标使用强类型 EvidenceValue 并携带来源
系统 SHALL 使报告页每个可展示指标为 `EvidenceValue<T>`（`status: available/unavailable/not_applicable/failed`），`available` 时带 `value + provenance[] (+confidence)`，`unavailable/not_applicable/failed` 时带 `reason`（`value` 为 `null`）。SHALL NOT 使用裸 `number | null` 表示缺数据。

#### Scenario: 缺数据可解释
- **WHEN** 某指标无值
- **THEN** 其 `status` 明确为 `unavailable` / `not_applicable` / `failed` 之一
- **AND** 携带 `reason` 说明原因（artifact 未生成 / 加载失败 / 本次不支持 / 无该球员 / 覆盖率不足 / 仍在加载）

#### Scenario: 有值必可追溯
- **WHEN** 某指标 `status === "available"`
- **THEN** 其携带非空 `provenance`（来源 artifact/event/field 链），用于 invariant #5 的可追溯断言

### Requirement: 关联与全局身份解析
系统 SHALL 使用 canonical player id 关联 shot row / heatmap / distance / trajectory / serve-return，SHALL NOT 使用 `row.player === subject.name`（展示名）。`P1 / player_1 / Player_1` 等经 `normalizeCanonicalPlayerAlias` 语法归一化到 `Player_1`；`global_player_N` SHALL 仅经 `resolveGlobalPlayerId` + `global-player-roster.v1` 映射到 canonical，禁止按尾号猜。

#### Scenario: 按 id 而非展示名取数
- **WHEN** 一个组件需要取某球员的 shot 或 heatmap 数据
- **THEN** 其 SHALL 以 canonical id 查找
- **AND** legacy / 全局 id 经上述两条函数解析后再匹配

#### Scenario: 全局身份无映射
- **WHEN** `global_player_N` 在 `global-player-roster.v1` 中无对应映射
- **THEN** 该身份 SHALL 解析为 `unavailable`
- **AND** SHALL NOT 因尾号 N 被猜测为 `Player_N`

### Requirement: source fail-closed（job evidence-only）

系统 SHALL 仅在 `report.source === "demo"` 时允许 mock/Demo Adapter 数据；`job / undefined / unknown` SHALL 一律走 evidence-only。真实 job 的结构化可视化 artifact（包括 `zone_stats`）属于 evidence，必须按 canonical player 读取并携带 provenance；任何缺失或无法读取的 artifact SHALL 返回 unavailable/failed 语义。

#### Scenario: job 报告不生成近似值

- **WHEN** 报告 `source` 为 `job`（或缺失/未知），且缺少某指标或结构化区域数据
- **THEN** 该指标 SHALL 为 `unavailable`，显示 artifact 未生成、加载失败、本次不支持或无该球员等原因
- **AND** SHALL NOT 回退为近似、稳定哈希数值、静态占位热力图或 demo 区域数据

#### Scenario: demo 标注可见且 mock 不泄漏

- **WHEN** 当前报告 `source === "demo"`
- **THEN** 报告页顶部 SHALL 显示可见的“演示数据”标注
- **ELSE**（非 demo）SHALL NOT 使用任何 mock / DemoAdapter 数值或区域可视化

#### Scenario: structured visualization artifact 作为真实证据

- **WHEN** real job 的 `/visualization-data` 返回 selected canonical player 的 `zone_stats`
- **THEN** `PlayerReportEvidence` SHALL 将该区域统计标记为 `available`
- **AND** 该值 SHALL 携带 `structured_visualization` provenance

#### Scenario: structured visualization artifact 缺失

- **WHEN** real job 的 structured visualization 请求返回 404、网络错误、损坏数据或没有匹配球员
- **THEN** 区域统计证据 SHALL 为 `unavailable` 或 `failed` 并携带原因
- **AND** 报告 SHALL 不得从 `metrics.heatmap`、展示名、数组位置或硬编码值猜测区域占用

### Requirement: job 路径禁止 import mock（架构可验证）
系统 SHALL 使报告展示组件（`src/components/pb-vizion/**`）不得 import `pbMockData` 或 Demo Adapter（Demo 数据入口组件除外）；此约束 SHALL 由自动化架构/单测强制，而非仅依赖人工。

#### Scenario: 架构测试拦截 mock 引入
- **WHEN** 任一报告展示组件静态 import 了 mock / DemoAdapter
- **THEN** 架构测试 SHALL 失败告警
- **AND** 仅 Demo 数据入口可 import 上述模块

### Requirement: 3D Court 消费正式 trajectory artifact
系统 SHALL 使报告 3D 球场消费正式 `BallTrajectory` / reconstructed trajectory artifact（经 hit / bounce / segment evidence 组装），再按 `selectedPlayerId` + filter 筛选；SHALL NOT 从轻量 `shotTrajectories` 构造 `points: []` 的空轨迹。

#### Scenario: 球场有真实空间点
- **WHEN** 存在可用且命中筛选的正式轨迹 evidence
- **THEN** 传入 `BallTrajectoryScene` 的轨迹 SHALL 含非空 `points`，能渲染出球路
- **AND** 无可用 evidence 时显示空态而非空轨迹列表

### Requirement: 第三拍（阶段）以 rallyId + ordinalInRally 定义，先裁决后编码
系统 SHALL 使用 `rallyId + ordinalInRally` 表示一击在对应 rally 内的第几拍（`1=发球` `2=接发` `3=第三拍` `4=第四拍` `5+=后段`）；阶段筛选 SHALL 依据 `ordinalInRally`，SHALL NOT 依赖全局 shotRows 下标 `i + 1`。ordinal 的可靠来源 SHALL 在编码前经 contract spike 裁决（adapter-derived 或 backend `ordinal_in_rally`）。

#### Scenario: 阶段按 rally 内序号筛选
- **WHEN** 用户选择"第三拍"或"第五拍及以后"
- **THEN** 筛选 SHALL 依据当前 rally 内的 `ordinalInRally`，而非 shotRows 数组整体序号
- **AND** PB 组件 SHALL NOT 自行 `i + 1`

#### Scenario: ordinal 可靠性裁决
- **WHEN** 存在 hit event 漏检/重复/跨 rally 错连的可能
- **THEN** ordinal 方案 SHALL 先经 authority spike（rally boundary / hit authority / ordering timestamp / duplicate-missing / ownership / multiview-vs-single）裁决后再实施

### Requirement: 发球/接发仅展示底层能力可证明的指标
系统 SHALL 使 `ServeEventsArtifact`（只证明发球开始/发球者/发球起点）不被误用作 In/Out、深度、接发事件；缺失权威的指标 SHALL 为 `unavailable`，SHALL NOT 为保持 PB 模块形态而硬接错误数据。

#### Scenario: 可证明 vs 不可证明
- **WHEN** 需要展示"发球次数 / 发球者"
- **THEN** 基于 ServeEventsArtifact 提供实际值
- **ELSE WHEN** 需要展示"发球 In/Out / 发球深度 / 接发 In/Out / 接发深度"
- **THEN** 在相应 landing/bounce/return 权威建立前 SHALL 为 `unavailable`，显示"暂未生成"

### Requirement: 技能评分暂停仿 PB 换算（fail-closed）
系统 SHALL 仅在存在正式技能评分模型（带 `player-skill-rating.v1` schema + `modelVersion`）时显示"单场技能评分"；否则模块改名为"本场表现概览"或显示"技能评分模型尚未生成"。SHALL NOT 把现有长度=6 的旧 `skillRatings` 当作正式模型，也 SHALL NOT 显示 `LABEL_TO_DIM` 失配后顺序硬塞 + 归一化 + 2.0~5.5 换算出的综合分（如 `4.04`）。

#### Scenario: 无正式模型
- **WHEN** 不存在 `player-skill-rating.v1` 模型 artifact
- **THEN** 展示"本场表现概览"或"技能评分模型尚未生成"
- **AND** 不显示伪 2.0~5.5 综合分，也不因 `skillRatings.length === 6` 误判为正式模型

### Requirement: Coach / LegalThirds evidence-driven
系统 SHALL 使 Coach 卡不扮演真实教练（去掉"匹克球认证教练 · 8 年经验"），而显示"AI 训练洞察·基于本场可观测指标生成"；结论仅来自 `performanceInsights.findings / recommendations` 与真实人工 `coachNotes`；无 evidence 则显示"当前数据不足以生成可靠训练建议"。LegalThirds 仅在存在分子/分母时显示"第三拍成功率 X% · n/m"，否则降级为"第三拍训练建议"或"本次分析暂无第三拍统计"，SHALL NOT 无比例自称"合法第三拍率"。

#### Scenario: 无 coach evidence
- **WHEN** 没有任何 findings / recommendations / 真实 coachNotes
- **THEN** Coach 卡显示"当前数据不足以生成可靠训练建议"，不显示默认兜底建议

#### Scenario: LegalThirds 有比例
- **WHEN** 存在合法的第三拍 numerator / denominator
- **THEN** 显示"第三拍成功率 X% · n/m"
- **ELSE WHEN** 仅存在 recommendation
- **THEN** 标题降级为"第三拍训练建议"
- **AND** 不伪装为"合法第三拍率"

### Requirement: 报告指标可追溯且数据来源单一

系统 SHALL 使报告页展示的每个指标都能追溯到明确 artifact / event / finding（`PlayerReportEvidence` 聚合为组件唯一数据入口），包括区域空间热力图及其占用统计。

#### Scenario: 数据来源单一

- **WHEN** 报告页任一 PB 组件需要展示数值、区域颜色或区域占用率
- **THEN** 该值 SHALL 来自 `PlayerReportEvidence`（或其下的 Demo Adapter，仅 demo 源）
- **AND** 组件 SHALL NOT 私自再查 `report.shotRows`、`mockData`、散落的 pipeline 字段或硬编码回退

#### Scenario: 区域统计来源可审计

- **WHEN** 报告展示 `zone_stats` 的区域占用、NVZ 占用率、站位距离或反馈
- **THEN** 每个 available 区域证据 SHALL 引用 structured visualization artifact 和 canonical player identity
- **AND** evidence 缺失时 SHALL 展示 unavailable 原因而不是 0% 或空白结论

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
