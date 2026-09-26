## Context

现有真实分析链路已经生成球轨迹、正式事件切段、canonical Shot/Rally 事实与球场投影坐标。`BallShotAssembler` 允许 Bounce 切分 Flight Segment 但不切断 Shot；`shot-rally-events.v1` 已将 `shot_id`、`rally_id`、`ordinal_in_rally`、`contact_ms` 和 `trajectory.segment_ids` 固定为公开关联契约。现有 `bounce_events.json` 和散点图仍表达弹跳候选，不能直接视为 Shot 落点。

本变更横跨 canonical artifact 组合、存储与 API 发布、素材工作区 capability 门控、可视化与视频深链。设计必须保持以下约束：

- Shot 身份只来自 `shot-rally-events.v1`，不重新编号或通过时间最近邻猜测。
- 绝对 `court_ft` 是长期空间真值；标准化坐标和分区都是可重算派生值。
- 不能把界外位置、落在己方半场和落点不可用混成一个状态。
- 标准化方向证据不足时 fail closed，不根据落点半场反推进攻方向。
- 三维球路不可用不得自动导致地面落点不可用。

## Goals / Non-Goals

**Goals:**

- 建立确定性的 `shot-landings.v1` Shot 落点事实层。
- 对有落点、无弹地、无坐标、事件含糊与证据不可用做可审计区分。
- 在动态击球侧证据充足时生成 attacker-relative 目标半场坐标。
- 使用版本化 `project12.v1` 产生十二区标签与分区聚合。
- 将 artifact 发布为稳定可消费的 API/manifest capability，并在素材工作区提供专用落点视图。
- 让每个落点可回溯到 Shot、Segment、Event 和对应视频时刻。

**Non-Goals:**

- 不修改 BallTracker、BounceDetector、BallEventResolver 或 BallShotAssembler 的检测与身份权威。
- 不在本变更冻结 `paper6.v1` 的边界或论文来源。
- 不做自动裁判、得分/失误归因、落点评分、战术优劣或训练建议。
- 不把现有顶层单个 `landing_point` 扩展为整场集合，也不在本轮完成 per-Shot 双摄全量融合。
- 不回填历史任务或伪造旧任务缺失的证据。

## Decisions

### 1. 在 canonical 事件组合后生成独立 artifact

Shot Landing Composer 作为 job 完成后的可选组合阶段，消费已持久化的 `shot-rally-events.v1` 与对应 reconstructed trajectory/events，写入独立 `shot_landings.json`。它不嵌入 `ShotEvent.spatial`，也不复用整场顶层单个 `landing_point`。

选择该方案是因为落点有独立状态、坐标标准化、分区 profile 和可视化生命周期。备选方案“直接扩展 ShotEvent”会将 canonical Shot 权威与可重算分区耵合；“复用 bounce_events”则缺少 Shot 语义和正式事件质量门。

### 2. 严格从 canonical Shot 向证据导航

每个 `ShotEvent` 只能沿自身 `trajectory.segment_ids` 定位 reconstructed segments，再将段按事件时间和稳定 `segment_id` 排序，取第一个 `end_event_type == bounce` 的正式段终点，并使用 `end_event_id == event_id` 精确关联事件。Composer SHALL NOT 创建、重新编号、推断或替换 canonical Shot 身份，也不使用最近时间匹配。

已被 suppressed/rejected 或仅存在于 diagnostics 的 Bounce 不进入正式 reconstructed event/segment 关系，Composer 不从旁路诊断数据捞回。多次 Bounce 只保留首次正式 Bounce。

### 3. 使用三个正交状态维度

`landing_status` 只表达落点事实是否存在及为何不可用：`available | no_bounce_before_next_contact | bounce_without_court_coordinate | ambiguous_bounce | unavailable`。

`court_location` 只表达几何位置：`inside_court | outside_court | unknown`。`target_relation` 只表达落点与动态击球侧的关系：`target_half | own_half | unknown`。只有同时满足 `available + inside_court + target_half` 且标准化成功的项才能进入六区/十二区映射。

这避免将有价值的界外坐标降级为“无落点”，也避免将己方半场异常球洗成正常分区落点。

### 4. 绝对坐标为真值，界线附近不做裁判式断言

`landing_x_ft/landing_y_ft`、`frame_index` 与 `timestamp_ms` 保留事件证据。坐标不 clamp 到 `[0,20] × [0,44]` 或 `[0,1]`。`court_location` 是描述性几何分类，不是比赛裁判：当点到边界的距离小于等于该点可用的 calibration uncertainty（若缺失则使用 `landing-classification.v1` 的保守默认容差 0.1 ft）时标记 `unknown`，而不宣告界内或界外。

界外但坐标可用的点保留于连续落点数据中；前端可在有限 tracking buffer 中显示，但不计入分区分母。

### 5. 目标半场标准化使用动态证据且 fail closed

标准化权威顺序为：

1. `hitter_position_at_contact`：在 selected Job 冻结的 canonical Player_N 球员球场轨迹中，查找 `contact_ms` 附近最近的有效动态位置。单摄消费 `player_render_trajectory.v2`，双摄 Parent 消费已公开为 canonical Player_N 的 fused trajectory。`landing-orientation.v1` 默认最大时差为 250 ms，只接受有限 court coordinate 且未被标记为投影失败的样本。
2. `trajectory_direction`：只在击球者动态位置不可用时，由 Shot 的正式轨迹起点至首次 Bounce 的纵向净位移判定；位移必须超过 profile 中的最小方向证据门。
3. `unavailable`：两者都不足时不生成 `target_x_ft/target_y_ft/u/v` 或分区标签。

远端为目标半场时使用 `identity`；近端为目标半场时使用 `rotate_180`：`target_x=20-x`、`target_y=44-y`。标准化后 `u=target_x/20`、`v=(target_y-22)/22`，其中左右始终是击球者面向目标半场的左右。不使用落点所在半场反推方向。

### 6. `project12.v1` 是版本化派生 profile

横向使用 `L=[0,1/3)`、`C=[1/3,2/3)`、`R=[2/3,1]`；纵向以距球网距离划分 `K=[0,7)`、`T=[7,12)`、`D=[12,17)`、`VD=[17,22]` ft。中间边界归入后一区，最后区包含上界。`K` 的 7 ft 来自物理 NVZ，12/17 ft 标记为项目分析阈值。

profile 在 artifact 顶层保留完整快照/标识，每条 Landing 同时保留所用 `zone_12_profile`。`zone_6` 与 `zone_6_profile` 在首版为 null，不用临时六区填充。

### 7. Artifact 使用完整发布契约

StorageService 提供确定性 `shot_landings_json_path(job_id)`；Pipeline Result Manifest 增加可选 `shot_landings_json_path/url/status/detail`；API 发布 `GET /api/analysis/jobs/{job_id}/artifacts/shot-landings`；前端定义 `ShotLandingsArtifact` 并通过 `getShotLandings` 读取。

Composer 失败只将该可选 artifact 置为 `failed/unavailable`，不把已完成的主视觉分析改为失败。对 CaptureTake 任务公开 result 只暴露逻辑 URL，不泄漏本地绝对路径。

### 8. 新增独立 Library `landing` view

素材工作区顺序为“概览 / 视频 / 数据分析 / 球路 / 落点 / 报告 / 片段 / 技术详情”。`landingReady` 只根据 selected Job manifest 的 `shot_landings_url` 和 artifact 可读状态判定，不复用 `trajectoryReady`。

页面使用专用数据契约，不复用以球员停留时间为分母的 `StructuredHeatmap`。首版提供“连续落点”和“项目十二区”；“论文六区·待配置”可见但禁用。界外可用点可在连续图的 buffer 内显示，但分区矩阵仅聚合合格目标半场落点。

点击落点选中 `shot_id` 并展示详情；用户触发“查看视频”时，在同一 Library Item 内以 replace 语义转到 `view=video`，保留 selected `analysisJob`，并以 `t=max(0, landing_timestamp_ms-1200)` 预滚动到落点前 1.2 秒。

### 9. 统计保持分母语义

“有效落点数”只计 `landing_status=available`且坐标有限的项；“空间可测率”的分母是已具有正式 Bounce 语义的 Shot，分子是其中有可用 court coordinate 的 Shot；`no_bounce_before_next_contact` 单独计数，不当作检测失败。分区占比的分母只是可进入分区的落点。本轮不生成落点质量分。

## Risks / Trade-offs

- [Shot 与 segment 关联缺失] → 该 Shot 显式输出 `unavailable`和 diagnostics，不使用时间最近邻补链。
- [动态击球侧位置在接触时刻附近缺失] → 按权威顺序退化到轨迹方向，仍不足时保留绝对坐标但不做标准化/分区。
- [Homography 误差造成边线附近错分] → 使用 uncertainty/保守容差产生 `court_location=unknown`，不把几何分类宣传为裁判。
- [旧任务没有新 artifact] → 落点 Tab 保持可理解的禁用/空态，不动态伪造或回写历史产物。
- [十二区 12/17 ft 边界属项目阈值] → profile 明确标记 basis 和版本，保留绝对坐标以便日后重算。
- [前端同时显示过多落点] → 使用客户端筛选、聚合和点数阈值保持交互性，不引入新的重型可视化依赖。
- [首版不做 per-Shot 双摄融合] → schema 预留 `landing_source`、`geometry_quality` 和 provenance，后续独立 Change 升级证据来源。

## Migration Plan

1. 先新增 schema、profile 和纯函数 Composer，通过 fixture 验证确定性、状态机、边界与方向处理。
2. 将 Composer 接入 canonical Shot/Rally 生成后的可选 post-processing，失败时仅降级新 artifact。
3. 增加确定性存储路径、manifest 字段和 API，验证 CaptureTake/上传任务的路径与安全边界。
4. 增加前端类型/client/capability，再上线独立 Landing view 与视频联动。
5. 对历史任务保持新字段可选；不执行批量回填。

回滚时可移除前端 `landing` capability 和停止新 Composer；新 JSON 是独立可选产物，保留在磁盘上不会改变旧 schema 的解析结果。

## Open Questions

- `paper6.v1` 的文献来源、纵向边界、FZ1–FZ6 编号方向和左右视角留待后续单独冻结。
- per-Shot 双摄落点融合何时替换单视角 ground evidence，由后续 `upgrade-shot-landings-with-multiview-authority` 类变更决定。
