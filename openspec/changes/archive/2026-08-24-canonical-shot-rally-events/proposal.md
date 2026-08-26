## Why

当前分析链路已经能够产生球轨迹、击球候选、球员归属、移动距离和厨房区等底层产物，但这些事实尚未统一为一个可供报告与评分消费的 Rally/Shot 数据合同。PB Vision 的对标分析表明，可信评分必须建立在逐回合、逐击球、带时间证据和样本量的事实之上；现在补齐这一层，才能为后续的本场表现分和跨场次 Skill Rating 提供稳定输入。

## What Changes

- 新增版本化的 canonical Rally/Shot 事件产物，统一已有击球检测、发球播种、球员归属、弹地/球路和回合边界结果。
- 为每个 Rally 和 Shot 固化 canonical 球员身份、回合内拍序、时间窗、击球阶段、击球类型、轨迹/空间信息、结果、错误、置信度和来源证据。
- 新增基于事件产物的 Metric Snapshot，所有比例类指标同时保存分子、分母、样本量、状态、置信度、单位、版本和证据引用。
- 为事件产物和指标快照提供确定性存储路径、artifact API 入口、status/detail 和 schema 版本，兼容 CaptureTake 任务目录与旧任务 outputs 目录。
- 让 Player Report Evidence 从 canonical 事件和指标快照读取逐拍统计，继续使用 canonical `Player_N`，禁止按展示名称或数组下标关联。
- 增加事件重复、漏检、未归属、时间单位、跨回合拍序和低样本降级的契约测试。
- 保持现有 fail-closed 约束：本变更不生成未经校准的数值技能评分、不把 `null` 或 insufficient evidence 当作 0，也不以 mock 数据填充真实 job。

## Capabilities

### New Capabilities

- `shot-rally-event-metrics`: 提供版本化的 Rally/Shot 事件产物和分母感知的指标快照，作为报告、洞察和未来评分模型的事实输入。

### Modified Capabilities

- `analysis-artifacts`: 增加 canonical Rally/Shot 事件产物及 Metric Snapshot 的存储、状态和 API 合同。
- `player-report-evidence`: 改为优先消费 canonical 事件/指标产物，并将逐拍字段、样本状态和证据来源映射到报告证据层。

## Impact

- 后端分析产物编排、artifact path resolver、artifact API 和 `AnalysisPipelineResult.artifacts` 类型。
- 现有 `ball-contact-event-detector`、`player-hit-attribution`、`ball-shot-assembly`、serve events、rally timeline 和球轨迹产物的只读组合层。
- `PlayerReportEvidence`、Shot Explorer 数据适配器及相关契约/集成测试。
- 需要新增 JSON schema/model、确定性 ID、样本充分度和指标单位定义；不新增视觉检测模型，不改变现有击球检测算法，不修改评分 UI。
- 后续 `performance-score.v1` / `player-skill-rating.v1` 将以本 change 的事件和指标快照为输入，另行设计和提案。
