## Context

当前视频分析页由 `VisionPage` 负责加载任务、报告、pipeline result、视频 overlay 和位置可视化产物。`VisualizationArtifactGallery` 已展示位置热力图、位置散点图和区域空间热力图，三者都以球员球场坐标为主要信息，因此缺少回合顺序、击球阶段和视频时间之间的关系。

后端已经生成可选的 `shot-rally-events.v1` artifact，并通过 `AnalysisPipelineResult.artifacts.shot_rally_events_url` 和现有 artifact API 暴露。前端 `analysisClient` 已有 `getShotRallyEvents`，但视觉分析页尚未加载该产物。该变更优先做前端消费和可视化，不改变 Shot/Rally 识别算法或现有 artifact schema。

## Goals / Non-Goals

**Goals:**

- 在真实完成任务的数据分析区域增加一个回合—击球阶段时序图。
- 使用 canonical `rally_id`、`shot_id`、`ordinal_in_rally`、`stage`、`hitter_player_id`、`ownership_status`、`quality` 和 `evidence_windows` 展示可追溯事件。
- 支持按可靠回合分行展示，也支持没有可靠回合边界时的单行击球事件降级视图。
- 允许用户从时序图点击事件，回到视频对应的证据时间窗。
- 保持加载、无数据、缺少回合边界和 artifact 请求失败时的 fail-closed 语义。
- 让图表摘要只表达描述性统计，不把事件数量或质量转成技能评分。

**Non-Goals:**

- 不修改 `shot-rally-events.v1`、`metric-snapshot.v1` 或 reconstructed trajectory 的后端生成算法。
- 不根据数组顺序、最近球员或展示名猜测 rally、击球者、击球阶段或结果。
- 不把 `spatial.end_xy` 直接命名为确认落点；不把 bounce candidate 呈现为已确认落点、比分或犯规。
- 不新增 0–10、雷达图、DUPR 或其他未经校准的技能评分。
- 不替换或合并现有位置热力图、位置散点图和区域空间热力图。
- 不要求 demo 路由伪造一套真实 Shot/Rally 事件；真实任务和 demo 数据继续分离。

## Decisions

### 1. 以 `shot-rally-events.v1` 作为唯一时序事件来源

时序图的事件列表、回合关系、阶段和证据时间窗 SHALL 直接来自 `ShotRallyEventsArtifact`。这样可以复用后端已经完成的去重、canonical identity、归属状态和 authority gate，避免从球员轨迹或 reconstructed segment 在前端重新推断回合。

备选方案是从 `result.tracks` 或 `reconstructedBallTrajectory.segments` 在前端自行推断击球顺序。该方案会重复后端语义组合逻辑，并可能把无 rally 边界的数据错误编号，因此不采用。

### 2. 在视觉分析加载层独立加载时序 artifact

扩展 `useVisualAnalysisReport` 的异步状态，使用已有 `getShotRallyEvents(result)` 在任务、报告和视频结果加载后独立请求事件 artifact。事件加载失败只影响时序图，不阻塞视频、overlay 或其他三张位置图。

新增状态至少区分 `loading`、`available`、`unavailable` 和 `failed`，并把后端 `status/detail` 传递给图表空态。无 job 的显式 demo 路由不发真实 artifact 请求。

备选方案是在 `VisualizationArtifactGallery` 内部按 `jobId` 再请求一次。该方案会让 gallery 同时管理多个数据源和重复的任务生命周期判断，因此不采用。

### 3. 时序图采用“回合行 + 击球节点”的二维布局

- 当存在 `rallies` 且 Shot 能通过 `rally_id` 关联时：每个 Rally 一行，按 `ordinal_in_rally` 排列节点；横向位置使用事件的 `contact_ms`，缺失时依次回退到 `start_ms`、`end_ms`。
- 当没有唯一 authoritative rally 边界但存在 Shot：显示一条按事件时间排序的“击球事件时间轴”，并明确标注“未提供可靠回合边界”；不得展示伪造的回合编号或拍序。
- 当没有可展示 Shot：显示明确空态和 artifact detail，不渲染静态或 demo 时间轴。

该布局比单纯柱状图更能表达一分球的顺序和间隔，同时比在球场底图上叠加轨迹更少地重复现有空间可视化。

### 4. 事件视觉编码只表达事实和质量

- `stage` 映射为发球、接发、第三拍、后续击球；缺失 stage 使用“未分类”，不根据 ordinal 在前端补标。
- `hitter_player_id` 使用 canonical 球员颜色；`ambiguous`、`unassigned` 或缺少击球者时使用中性颜色，并显示“击球者不明”。
- `quality.band` 影响节点透明度或质量徽标；`none` 显示为质量未知，不映射成失败。
- `result`、`error_type`、`shot_type` 只有在 artifact 明确提供时才显示；否则不显示推断文案。
- `trajectory.path_distance_ft` 可作为事件详情中的描述性距离，不能被解释为球速或击球质量。

### 5. 证据跳转复用现有视频 seek 语义

点击节点时使用该 Shot 的 `evidence_windows`，优先取第一个有效 `start_ms`，通过现有视觉分析路径的 `t` 查询参数或等价导航状态触发 `VideoAnalysisCard` 的 `seekToMs`。在多视角任务中，跳转继续使用 canonical 时间，不改变 `displayViewId`、reference view 或 canonical frame。

没有有效证据窗的节点仍可选中并显示详情，但按钮必须提示“暂无可跳转证据”，不得跳到 0 秒或任意默认时间。

### 6. 摘要指标从当前 artifact 可审计地生成

首版摘要显示可从当前事件集确定的描述性统计：可见 Shot 数、可见 Rally 数、平均每 Rally Shot 数、各 stage 数量，以及归属不明数量。统计按唯一 `shot_id` 去重。

如果后续同时读取 `metric-snapshot.v1`，只有 `status=available` 且 subject/scope 匹配时才可用其审计字段；artifact 不可用时不能用 0 填充。任何“数据有限”状态都要保留 numerator/denominator 或 sample count（如果后端提供）。

### 7. 组件边界和测试策略

新增 `RallyShotTimeline` 作为纯展示组件，输入已经加载的 artifact、加载状态和视频跳转回调；分组、排序、stage 标签、质量显示和摘要计算优先抽成纯函数，便于单元测试。

`VisualizationArtifactGallery` 继续负责卡片编排和统一空态，不让时序组件读取网络或直接访问全局任务状态。现有三张位置图的 fallback 行为保持不变。

## Risks / Trade-offs

- **[回合边界缺失导致无法按回合分行]** → 降级为单行击球事件时间轴，并明确显示缺少 authoritative rally boundary，不伪造 rally/ordinal。
- **[Shot 归属不确定]** → 保留中性节点和 `ownership_status` 文案，不强行分配到某个球员；全局 Shot 统计仍可按唯一 `shot_id` 计数。
- **[事件 artifact 较大或加载较慢]** → 与视频和其他 overlay 独立加载；首版限制渲染数量或按回合折叠时，统计仍基于完整已加载 artifact，并明确可视范围。
- **[用户误解 trajectory end 为落点]** → 组件文案统一使用“击球事件”“轨迹起止”或“证据时间窗”；只有后端明确提供 authoritative landing 时才允许使用“落点”。
- **[多摄展示时间与事件时间不一致]** → 事件使用 canonical 毫秒时间，跳转复用现有 display time mapping，不参与视角重新计算。
- **[历史任务没有 artifact]** → 通过 `status/detail` 展示“当前任务未生成回合事件”，不影响其他图表和视频分析页面。

## Migration Plan

1. 新增时序图能力规格和前端组件契约，先用现有 shot-rally fixture 与无数据 fixture 覆盖纯函数行为。
2. 在视觉分析加载状态中接入 `getShotRallyEvents`，在数据分析 gallery 中增加卡片，并接入事件点击到现有视频 seek 导航。
3. 增加真实任务可用、无回合边界、归属不明、请求 404、请求失败和 demo 路由测试。
4. 发布后若时序 artifact 请求或渲染异常，可通过卡片级 unavailable/failed 状态回滚展示，不需要回滚后端 pipeline 或删除已有 artifact。

## Open Questions

- 首版是否默认只展示前 N 个 Rally，还是在卡片内部支持滚动容器；实现时可依据真实任务的 Shot 数量和页面高度决定，但不得截断摘要统计。
- 是否在同一节点详情中显示 `path_distance_ft`；如果展示，需确认产品文案采用“轨迹长度”而不是“击球距离”或“球速”。
