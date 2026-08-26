# shot-rally-event-metrics Specification

## Purpose
TBD - created by archiving change canonical-shot-rally-events. Update Purpose after archive.
## Requirements
### Requirement: Canonical Rally/Shot artifact envelope

系统 SHALL 为完成或明确降级的分析任务生成可选的 `shot_rally_events.json`，其 schema SHALL 为 `shot-rally-events.v1`，并包含 `job_id`、`video_id`、`status`、`detail`、`generated_at`、`time_unit`、`coordinate_system`、`rallies`、`shots` 和 `diagnostics`。`time_unit` SHALL 为 `ms`；court 坐标单位 SHALL 明确为 `ft`，image 坐标单位 SHALL 明确为 `px`。

#### Scenario: 事件产物成功生成

- **WHEN** 一个真实 job 已完成，且存在可消费的 rally/shot 输入产物
- **THEN** 系统 SHALL 写入 `shot_rally_events.json`
- **AND** `status` SHALL 为 `available`
- **AND** payload SHALL 声明 `schema_version = "shot-rally-events.v1"`
- **AND** `rallies` 与 `shots` SHALL 即使为空也保持数组类型

#### Scenario: 事件源不足

- **WHEN** job 完成但没有足够输入构造可靠事件
- **THEN** 系统 SHALL 保留 artifact 状态为 `unavailable`、`skipped` 或 `failed`
- **AND** `detail` SHALL 说明缺少的输入或失败原因
- **AND** SHALL NOT 用 ball trajectory 或 mock 数据伪造 shot 事件

### Requirement: Rally/Shot 关系与回合内拍序

系统 SHALL 以 `rally_id` 和 `shot_id` 建立稳定关系。每个正式 Shot SHALL 只属于一个 Rally，`shot_id` 在 job 内 SHALL 唯一；当 rally 边界和事件顺序可靠时，系统 SHALL 提供从 1 开始的 `ordinal_in_rally`，否则 SHALL 将其置为 null 并标记原因。Shot 统计 SHALL 按 `shot_id` 去重，不得按 flight segment 数量计数。

#### Scenario: 正常回合序列

- **WHEN** 一个 Rally 包含发球、接发和后续击球
- **THEN** 其 Shot SHALL 共享同一个 `rally_id`
- **AND** `ordinal_in_rally` SHALL 依次为 1、2、3……
- **AND** 第 1 拍 SHALL 标记为 `serve`，第 2 拍 SHALL 标记为 `return`，第 3 拍 SHALL 标记为 `third`（当阶段映射可用）

#### Scenario: 重复或缺失候选

- **WHEN** 输入事件出现重复、漏检或无法确定的跨回合连接
- **THEN** 组合层 SHALL 保留诊断信息
- **AND** 不得通过数组下标强行重新编号
- **AND** 受影响 Shot 的 `ordinal_in_rally` 或关联指标 SHALL 降级为不可用状态

### Requirement: Canonical 球员身份与不确定性保留

系统 SHALL 只使用 canonical `Player_1` 至 `Player_4` 作为 `hitter_player_id` 和 subject ID。`ambiguous` 或 `unassigned` 的 Shot SHALL 保留 `ownership_status`、`ownership_confidence`、`ownership_source` 和 diagnostics；`hitter_player_id` 可为 null，但不得根据展示名、track_id 尾号、最近球员或数组顺序猜测归属。

#### Scenario: 已确认归属

- **WHEN** 现有 player-hit-attribution 输出 `confirmed` 的 canonical 球员
- **THEN** Shot SHALL 使用该 `Player_N` 作为 `hitter_player_id`
- **AND** SHALL 保留原始归属方法和置信度

#### Scenario: 归属无法裁决

- **WHEN** 两名球员证据接近或附近没有足够球员证据
- **THEN** Shot SHALL 标记为 `ambiguous` 或 `unassigned`
- **AND** SHALL NOT 强制选择任意球员
- **AND** 该 Shot 仍可计入全局 Shot 数，但不得计入某个球员的归属击球数

### Requirement: Shot 事件字段与来源证据

每个 Shot SHALL 能表达 `start_ms`、`end_ms`、`rally_id`、`ordinal_in_rally`、`hitter_player_id`、`team_id`、`stage`、`shot_type`、`stroke_type`、`is_volley`、`result`、`error_type`、`quality`、`trajectory`、`spatial` 和 `evidence_windows`。无法由现有 artifact 证明的字段 SHALL 为 null 或 unavailable，并 SHALL 记录 `source_artifacts` 和 `provenance`。

#### Scenario: 轨迹字段可用

- **WHEN** Shot 关联到有效球轨迹或重建轨迹
- **THEN** 事件 SHALL 保存速度、距离、深度/落点、方向或过网高度中实际可用的字段
- **AND** 每个字段 SHALL 声明单位或引用 artifact 的坐标单位
- **AND** SHALL 保留轨迹的 source 和 confidence

#### Scenario: 语义字段未实现

- **WHEN** 当前输入不能证明 shot type、error type 或 result
- **THEN** 对应字段 SHALL 为 null 或状态为 unavailable
- **AND** 系统 SHALL NOT 把未知事件映射成默认的 drive、clean 或 unforced error

### Requirement: Metric Snapshot 分母感知

系统 SHALL 从 canonical 事件产物确定性生成 `metric_snapshot.json`，schema SHALL 为 `metric-snapshot.v1`。每条指标 SHALL 包含 `metric_key`、`subject_id`、`value`、`unit`、`numerator`、`denominator`、`sample_count`、`status`、`confidence`、`provenance`、`evidence_ids` 和 `calculation_version`。比例类指标 MUST 能由 numerator/denominator 审计。

#### Scenario: 有效比例指标

- **WHEN** 某球员有 8 次合法发球且总发球机会为 10 次
- **THEN** Metric Snapshot SHALL 保存 numerator=8、denominator=10、value=0.8 或等价的明确单位表示
- **AND** SHALL 记录 sample_count=10 和对应的 Shot/Rally evidence IDs

#### Scenario: 分母为零

- **WHEN** 某球员在本场没有发球机会
- **THEN** 该指标 SHALL 使用 `not_applicable` 或 `insufficient_evidence`
- **AND** SHALL 将 value 置为 null
- **AND** MUST NOT 输出 0% 作为合法发球率

### Requirement: 数据充分度与指标降级

系统 SHALL 为指标和维度保存可解释的充分度状态。最低样本阈值 SHALL 由版本化 `product_reference_v1` 配置提供；低于阈值时 SHALL 输出 `insufficient_evidence`，不输出确定性结论。单打任务的双打协同指标 SHALL 为 `not_applicable`。

#### Scenario: 短视频样本不足

- **WHEN** 一个视频只有少量回合或某类击球样本低于配置阈值
- **THEN** 相关指标 SHALL 保留 numerator/denominator（若存在）并标记 `insufficient_evidence`
- **AND** 报告消费方 SHALL 能显示“数据有限”而不是 0 分或 N/A 以外的确定评级

#### Scenario: 不适用维度

- **WHEN** `match_format = singles`
- **THEN** 双打协同 subject 和指标 SHALL 标记 `not_applicable`
- **AND** SHALL NOT 因缺少搭档而判定为防守或移动能力为零

### Requirement: 确定性生成与证据引用

系统 SHALL 对相同输入 artifact、相同 `calculation_version` 和相同配置生成相同的事件 ID、指标 ID、字段值和排序结果（`generated_at` 除外）。每个可用指标 SHALL 至少引用一个真实事件或输入 artifact；不存在的 evidence ID 不得写入快照。

#### Scenario: 重复生成

- **WHEN** 同一个 job 在相同输入和版本下重新生成事件与指标快照
- **THEN** 除 `generated_at` 外，两份产物 SHALL 逐字段一致
- **AND** 事件、指标和 evidence 的排序 SHALL 保持一致

#### Scenario: 证据不可解析

- **WHEN** 指标计算引用的事件或 artifact 不存在
- **THEN** 该指标 SHALL 降级为 `failed` 或 `unavailable`
- **AND** SHALL NOT 写入悬空的 evidence ID

### Requirement: 首版指标不等同于技能评分

`metric-snapshot.v1` SHALL 只表达可审计的描述性指标和数据质量，不得包含未经独立校准的 Skill Rating、DUPR 映射或 0–10/2.0–8.0 数值技能评分。未来评分模型 SHALL 使用独立 schema 和独立版本。

#### Scenario: 真实 job 尚无评分模型

- **WHEN** 报告读取到 `metric-snapshot.v1` 但不存在正式评分 artifact
- **THEN** 系统 SHALL 展示可用的描述性指标或“评分模型尚未生成”
- **AND** SHALL NOT 将指标快照直接投影为球员综合分
