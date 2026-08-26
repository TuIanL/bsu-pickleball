## MODIFIED Requirements

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
