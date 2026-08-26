## Why

视频分析任务当前的三张可视化图主要描述球员在球场上的空间位置：位置热力图、位置散点图和区域空间热力图。它们缺少回合顺序、击球阶段和视频时间之间的关系，用户难以从图表中理解一分球是如何展开的；而后端已经生成 `shot-rally-events.v1`，适合补充这一时间与事件维度。

## What Changes

- 在真实视频分析任务的数据分析区域新增“回合—击球阶段时序图”可视化卡片。
- 按可靠的 `rally_id` 展示回合行，并按 `ordinal_in_rally` 展示发球、接发、第三拍和后续击球事件。
- 使用 `hitter_player_id`、`ownership_status`、`quality.band` 和时间窗表达球员归属、归属不确定性、事件质量和视频时间。
- 提供回合数、击球数、平均每回合击球数以及阶段分布等描述性摘要；样本不足时显示数据有限状态，不生成技能评分。
- 支持点击击球事件跳转到对应视频证据时间窗；无法证明的结果、失误或落点不得被可视化文案强行补全。
- 当 `shot-rally-events.v1` 不可用、没有可靠回合边界或没有可展示 Shot 时，显示明确的不可用/降级状态，不回退到 demo 数据。
- 保持现有位置热力图、位置散点图和区域空间热力图的行为不变。

## Capabilities

### New Capabilities

- `rally-shot-stage-timeline`: 定义回合—击球阶段时序图的数据来源、事件编码、交互、摘要指标和 fail-closed 降级行为。

### Modified Capabilities

- `visual-analysis-workspace`: 真实完成任务的数据分析区域新增回合—击球阶段时序图，并纳入独立加载、任务来源标识和不可用状态展示。

## Impact

- 前端：`VisionPage` 的可视化产物区域、新增时序图组件、`analysisClient` 的事件 artifact 加载状态、视频跳转交互和相关测试。
- 后端/API：复用现有 `shot_rally_events_url` 与 `GET /api/analysis/jobs/{job_id}/artifacts/shot-rally-events`，不新增必需的分析算法或存储 schema。
- 数据契约：消费 `shot-rally-events.v1` 和可选的 `metric-snapshot.v1`；保留 canonical Player 身份、事件质量、归属状态、证据时间窗和描述性指标语义。
- 兼容性：旧任务、缺少事件产物的任务、无 rally 边界的任务和显式 demo 路由均须继续可用，并显示相应降级原因。
