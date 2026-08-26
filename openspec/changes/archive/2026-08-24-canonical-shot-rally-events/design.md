## Context

当前项目已经有多类底层产物和规范：球接触候选检测、球员击球归属、Shot 生命周期、发球事件、球轨迹、回合时间线和 `performance-insights`。这些能力分别解决了检测或解释问题，但报告层仍通过多个 adapter 拼接轻量字段，缺少一个以 job 为边界、可被其他模块稳定消费的 Rally/Shot 事实产物。

PB Vision 的对标结果说明，后续评分需要同时具备三种信息：逐拍事件事实、按球员/球队聚合的分母感知指标、以及能跳回视频的证据引用。本 change 只建立这条事实与指标链，不在本阶段引入未经校准的技能评分。

## Goals / Non-Goals

**Goals:**

- 将已有事件源组合为确定性的 `shot-rally-events.v1` artifact。
- 提供 `metric-snapshot.v1`，保存可供报告和未来评分消费的描述性指标及其分子、分母、样本量、状态、置信度和 provenance。
- 统一 canonical `Player_N`、`rally_id`、`shot_id`、回合内拍序和毫秒时间窗。
- 保留 confirmed、ambiguous、unassigned 等不确定性，不通过名称、数组下标或近邻猜测补齐身份。
- 让 Player Report Evidence 能从新的 artifact 生成逐拍证据和强类型指标值。
- 支持单摄、双摄、CaptureTake 任务和旧 `outputs/<job_id>/` 任务的可选 artifact 读取。

**Non-Goals:**

- 不重写 `ball-contact-event-detector`、`player-hit-attribution` 或 `ball-shot-assembly` 的检测算法。
- 不在本 change 内定义 PB Vision 风格的六维数值评分、DUPR 映射或跨场次 Skill Rating。
- 不把候选 bounce、ball 或低置信度语义自动升级为可评分事实。
- 不修改报告页布局、Shot Explorer 交互或现有评分 UI。
- 不为了填满字段而复用 mock 数据、猜测单位或把缺失值转换为 0。

## Decisions

### D1: 事件产物与指标快照分离

每个 job 生成两个逻辑 artifact：

- `shot_rally_events.json`：接近事实层，包含 rallies、shots、身份、时间、状态、空间/轨迹引用和来源。
- `metric_snapshot.json`：从事件层确定性聚合得到的描述性指标。

两者使用独立 schema 版本 `shot-rally-events.v1` 与 `metric-snapshot.v1`。分离可以避免报告指标重算时修改原始事件，也允许未来升级评分规则而不重跑视觉 pipeline。

替代方案是把事件和所有聚合结果塞进一个超大 JSON；该方案会放大版本耦合、难以局部重算，因此不采用。

### D2: 复用现有检测权威，不创建第二套事件状态机

组合层按以下顺序消费已有产物：

1. `ball-shot-assembly` 提供 Shot 生命周期和 `shot_id` 归属传播；
2. `player-hit-attribution` 提供 canonical `Player_N`、ownership status 和归属置信度；
3. serve events 只作为发球开始/发球者事实；
4. rally timeline 或已有 rally 边界提供 Rally 窗口；
5. ball/bounce/trajectory artifact 只提供空间与轨迹证据，不被伪装成得分或完整击球语义。

如果多个来源冲突，组合层保留冲突诊断并使用权威来源；不得在 adapter 中再次运行最近球员或数组顺序推断。这样可以避免检测器、报告和评分各自维护一套不同的 shot 序列。

### D3: 事件字段允许缺失，但指标状态不可含糊

事件层允许单个字段为 `null`，但必须通过事件级 `quality`、`ownership_status`、`source` 和 diagnostics 表达原因。指标层不使用裸 `number | null`，每项指标至少包含：

```text
metric_key / subject_id / value / unit
numerator / denominator / sample_count
status / confidence / provenance / evidence_ids
calculation_version
```

指标状态沿用项目的 fail-closed 语义：`available`、`insufficient_evidence`、`not_applicable`、`unavailable`、`failed`。分母为 0 时不能显示百分比；样本不足时不能把结果投影成确定性评分。

### D4: 以 canonical ID 和时间窗建立证据链

Rally 和 Shot 使用稳定 ID，并通过 `rally_id`、`shot_id`、`player_id` 和 `evidence_windows` 关联。所有前端跳转时间使用 `start_ms/end_ms`；底层秒单位只在组合边界转换一次。

所有事件和指标保留 `source_artifacts`、`provenance` 和 `evidence_ids`。指标只能引用实际存在的事件或 artifact，不能只引用展示名称。双摄任务只消费 public Parent 已发布的最终产物，并区分 `fused_multiview` 与 `reference_view`。

### D5: Metric Snapshot 先做描述性指标，不做评分

首版 Metric Snapshot 只输出可审计的事实聚合，例如击球数、回合长度、发接发数量、击球类型分布、质量均值、失误分布、速度/深度/空间覆盖和厨房区机会率。每个指标必须能回答“统计了哪些事件、分母是什么、样本是否足够”。

未来 `performance-score.v1` 可以在此之上增加维度权重和校准，但不能把本 change 的描述性指标直接当成 0–10、2.0–8.0 或 Skill Rating。

### D6: Artifact API 与旧任务兼容

新的公开 artifact slug 为 `shot-rally-events` 和 `metric-snapshot`。路径遵循既有规则：关联 CaptureTake 的 job 写入 `analysis/<job_id>/`，旧任务写入 `outputs/<job_id>/`。artifact 缺失、跳过或不可用时返回既有 status/detail 语义；请求已知但未生成的 artifact 返回 404，不返回 422。

### D7: 先接报告证据层，再开放其他消费者

Player Report Evidence 作为首个消费者，只读取 canonical artifact 并映射到已有 `EvidenceValue`。Insight Engine 和评分模型暂不直接读取散落的底层文件。这样可保证报告、未来评分和调试工具共享同一事实入口，也避免多处重复计算。

## Risks / Trade-offs

- [现有来源的 rally 边界或 shot 序列不一致] → 组合层记录来源和冲突 diagnostics；无法裁决时保留不可用状态，不静默修复。
- [短视频导致大量指标样本不足] → 强制保存分子/分母和 `insufficient_evidence`，报告展示数据有限而非 0 分。
- [单摄与双摄字段能力不同] → 每个 artifact 声明 provenance 和字段可用性；融合产物缺失时不借用 internal child 或其他视图补值。
- [schema 过早锁定导致后续评分受限] → 事件层和指标层独立版本化，新增字段向后兼容，评分规则另行版本化。
- [重复落盘增加存储与读取成本] → 事件和快照按 job 懒加载，报告只读取 manifest/需要的子集，不把原始轨迹复制进每个 Shot。
- [指标单位混用] → schema 强制单位和 coordinate system 元数据；未声明单位的字段只能以 unavailable 进入指标层。
- [历史任务缺少完整事件源] → 新 artifact 可为 unavailable/partial，提供显式 detail；不阻塞旧报告和旧 artifact 读取。

## Migration Plan

1. 增加事件与指标快照的类型、schema、路径解析和 artifact API，但保持字段可选，旧任务继续按原路径工作。
2. 在 post-pipeline 组合阶段读取现有 shot、serve、rally、trajectory 和 roster artifact，生成两个新 JSON；失败时只记录状态，不使视觉 pipeline 失败。
3. 为新 job 默认生成 artifact；历史 job 先提供按需 regenerate/读取能力，不做一次性全量迁移。
4. 将 Player Report Evidence 的 job 路径切换到新 artifact，并补充空态、低样本和跨摄 provenance 测试。
5. 验证报告和现有视频/轨迹页面无回归后，再以单独 change 设计 `performance-score.v1`。

回滚时停止生成新 artifact 并移除 adapter 消费即可；旧的 tracking、pose、serve、trajectory、performance-insights artifact 不需要迁移或删除。

## Open Questions

- 当前 rally boundary 的最终权威是已有 timeline、pipeline result 还是两者的合并结果，需要在实现前用现有 fixture 做一次 authority spike。
- PB Vision 的 shot type taxonomy 与项目现有中文 `ShotType` 的映射需要先固定字典；未知类型必须保留原始值并标记 unsupported，而不是强行归类。
- Metric Snapshot 首版的最低样本阈值需要作为 `product_reference_v1` 配置确定，之后再由教练标注或跨场次数据校准。
