# reconstructed-trajectory-artifact Specification

## Purpose
定义第三套球轨迹重建产物的 JSON 契约、source 分类、坐标语义、存储路径、API slug 与前端接线，作为前端的权威数据来源（前端不再自行分段与估高）。v2 增加球员名单、击球事件归属与 Shot 级归属传播字段；`event_status`（是否为可信击球）与 `ownership_status`（能否确定击球者）严格分离。v1 产物保留不回写，前端兼容降级。
## Requirements
### Requirement: 重建产物 JSON 契约
系统 SHALL 输出结构化重建产物 `reconstructed_ball_trajectory.json`，包含 schema 版本、重建模式、坐标语义、球员名单、事件列表与飞行段列表。schema 版本 SHALL 为 `reconstructed_ball_trajectory.v2`。

#### Scenario: 产物顶层结构
- **WHEN** 系统输出重建产物
- **THEN** 产物顶层 SHALL 包含 `schema_version`、`reconstruction_mode`、`coordinate_semantics`、`player_roster`、`events`、`segments`
- **AND** `coordinate_semantics` SHALL 包含 `xy = court_ft_visual_estimate`、`z = estimated_height_ft` 与 `metric_validity = visualization_only`
- **AND** `player_roster` SHALL 为球员列表，每项含 `player_id`、`render_slot` 与 `initial_side`

#### Scenario: 事件列表
- **WHEN** 产物包含事件
- **THEN** `events` 数组 SHALL 包含击球、弹地与 serve 重置等边界事件，每个事件含 `event_id`、`event_type`、`frame_index`、`timestamp_sec` 与 `confidence`
- **AND** 击球事件 SHALL 含 `event_status ∈ {confirmed, ambiguous}` 与 `hitter_player_id`
- **AND** 击球事件 SHALL 含 `attribution` 对象（status、confidence、method、candidate_scores、attributed_frame_index）
- **AND** `events` 数组 SHALL NOT 包含 `suppressed_by_bounce` 状态的 HIT 事件

#### Scenario: 飞行段结构
- **WHEN** 产物包含飞行段
- **THEN** 每个段 SHALL 包含 `segment_id`、`start_event_id`、`end_event_id`、`start_event_type`、`end_event_type`、`fit_space`、`model`、`anchors`、`quality` 与 `samples`
- **AND** `model` SHALL 记录为 `weighted_huber_anchor_constrained`
- **AND** `fit_space` SHALL 记录为 `image_px`

### Requirement: 重建样本来源分类
系统 SHALL 为每个重建采样点记录来源分类，用于前端视觉编码与质量评估。

#### Scenario: 样本来源枚举
- **WHEN** 系统输出重建采样点
- **THEN** 每个样本 `source` SHALL 为 `detected`、`interpolated`、`model_predicted` 或 `anchor` 之一

#### Scenario: 缺失点保留
- **WHEN** 采样点缺少球场坐标或高度
- **THEN** 样本 SHALL 保留 `court_xy = null` 或 `estimated_height_ft = null`
- **AND** 前端 SHALL 以断开或虚线样式渲染

### Requirement: 高度字段语义
系统 SHALL 对重建采样的高度字段声明估值语义，不声称真实三维测量。

#### Scenario: 高度为视觉估计
- **WHEN** 系统输出 `estimated_height_ft`
- **THEN** 该字段 SHALL 为基于事件边界与弧线先验的视觉估计
- **AND** 配合 `height_source`、`height_confidence` 与 `height_uncertainty_ft` 使用
- **AND** 文档 SHALL 标注 `metric_validity = visualization_only`

### Requirement: 弹地与击球边界高度不变量
系统 SHALL 对事件边界处的高度值施加物理不变量约束。

#### Scenario: 弹地点高度为零
- **WHEN** 飞行段以 bounce 事件为端点锚点
- **THEN** 端点采样高度 SHALL 为 0 英尺（硬锚点）

#### Scenario: 击球点高度受先验约束
- **WHEN** 飞行段以击球事件为端点锚点
- **THEN** 端点采样高度 SHALL 落在可配置接触高度先验范围内
- **AND** 超出范围时 SHALL 以先验值钳制并记录不确定度

### Requirement: 存储路径与 API slug
系统 SHALL 提供重建产物的固定存储路径与 API 访问方式，v2 产物不覆盖 v1。

#### Scenario: 存储路径
- **WHEN** pipeline 写入重建产物
- **THEN** 文件 SHALL 写入 `StorageService.reconstructed_ball_trajectory_json_path(job_id)` 指向的路径（`reconstructed_ball_trajectory.json`）

#### Scenario: API 访问
- **WHEN** 前端请求重建产物
- **THEN** `routes_analysis.py` 的 artifact `Literal` 白名单 SHALL 包含 `reconstructed-ball-trajectory`
- **AND** 该 slug SHALL 映射到上述存储路径

#### Scenario: mock/unavailable/skipped 产物
- **WHEN** 任务未启用球重建或重建不可用
- **THEN** 系统 SHALL 输出与现有 artifact 状态机一致的 `unavailable / skipped / failed` 状态，不破坏已归档任务展示

### Requirement: 第三套数据独立
重建产物 SHALL 作为第三套数据存在，不覆盖原始证据。

#### Scenario: 三套数据并存
- **WHEN** 一次分析同时产生 raw、cleaned 与 reconstructed
- **THEN** `ball_trajectory.json` 与 `cleaned_ball_trajectory.json` SHALL 继续保留
- **AND** 重建产物 SHALL 是第三套独立产物，不得覆盖或混写前两套

### Requirement: 前端接线
前端 SHALL 通过新增类型与 getter 读取重建产物，不再从原始轨迹自行分段与估高。

#### Scenario: 前端类型与 getter
- **WHEN** 前端需要重建数据
- **THEN** `report.ts` SHALL 定义 `ReconstructedBallTrajectoryArtifact`
- **AND** `analysisClient` SHALL 提供对应的 artifact getter

#### Scenario: 球路页读取重建产物
- **WHEN** 球路页渲染
- **THEN** 页面 SHALL 从重建产物加载分段数据
- **AND** 页面 SHALL NOT 自行执行正式分段、生成方向、平均置信度或估算高度

#### Scenario: 无重建产物时降级
- **WHEN** 任务没有重建产物但具有原始/清洗轨迹
- **THEN** 页面 SHALL 降级为读取原始轨迹或以明确状态提示重建不可用
- **AND** 不得以重建产物缺失静默失败

### Requirement: 重建确定性
系统 SHALL 对相同输入产生确定性的重建产物。

#### Scenario: 相同输入相同产物
- **WHEN** 对同一任务重复运行重建
- **THEN** 段 ID、事件 ID、锚点序列与采样点 SHALL 完全一致

### Requirement: ownership_status 四态语义
系统 SHALL 严格区分 `shot_id = null`（无 Shot 上下文）与 `ownership_status = unassigned`（有 Shot 但击球者未知）。

#### Scenario: 无 Shot 上下文的孤立段
- **WHEN** segment 位于视频首拍前或 long loss 后、无任何击球归属
- **THEN** 该 segment 的 `shot_id` SHALL 为 null，`hitter_player_id` SHALL 为 null
- **AND** `ownership_status` SHALL 为 `not_applicable`
- **AND** 该 segment 不参与 Shot 统计

#### Scenario: 有 Shot 但击球者未知
- **WHEN** Shot 已建立但归属判定为 ambiguous/unassigned
- **THEN** 该 Shot 内 segment 的 `shot_id` SHALL 非空
- **AND** `ownership_status` SHALL 为 `ambiguous` 或 `unassigned`，`hitter_player_id` SHALL 为 null
- **AND** 该 Shot 计入总 Shot 数但不计入任何球员击球数

#### Scenario: 归属确认
- **WHEN** 归属判定为 confirmed
- **THEN** segment 的 `ownership_status` SHALL 为 `confirmed`
- **AND** SHALL 携带 `ownership_confidence` 与 `ownership_source_event_id`

### Requirement: 旧 v1 产物兼容
系统 SHALL 保证旧 v1 产物在升级后仍可被前端读取，且不伪造球员归属。

#### Scenario: v1 产物正常展示
- **WHEN** 前端读取 `schema_version = reconstructed_ball_trajectory.v1` 的产物
- **THEN** 球路 SHALL 正常展示（事件、段、锚点与质量信息）
- **AND** 球员筛选 SHALL 隐藏或禁用
- **AND** 前端 SHALL NOT 伪造 `hitter_player_id` 或 `shot_id`

### Requirement: 产物新增 v3 多视角估算三维语义
系统 SHALL 通过统一 `reconstructed_ball_trajectory` 概念保存多视角 3D、稀疏双摄锚定 2.5D 与单摄事件锚定 2.5D 段；v1/v2/v3 历史产物 SHALL 保持只读兼容，新产物 SHALL 按段声明 reconstruction mode，而非要求整个任务只有一种模式。

#### Scenario: 新混合产物顶层语义
- **WHEN** 新任务输出混合重建产物
- **THEN** 顶层 SHALL 声明 schema version、3D overall status 与 `display_trajectory_status`
- **AND** 每段 SHALL 声明 `stereo_estimated_3d`、`stereo_anchored_2_5d`、`single_view_event_anchored_2_5d`、`single_view_visual_arc` 或 `unavailable`
- **AND** coordinate semantics SHALL 明确区分 approximate multiview 与 visualization-only 估算

#### Scenario: 历史产物兼容
- **WHEN** 系统读取历史 v1/v2/v3 任务
- **THEN** SHALL 继续通过统一 slug 解析其原有字段
- **AND** MUST NOT 回写或覆盖历史不可变 artifact

### Requirement: 指标级 validity 分级
系统 SHALL 在产物中为每个指标声明独立的有效性，占用的可信度不同。

#### Scenario: 按指标分级
- **WHEN** 产物包含各类指标
- **THEN** 落点 SHALL 含 `landing_source ∈ {dual_view_ground_fused, single_view_ground}` 与 `landing_validity = high`
- **AND** `flight_z_validity`、`flight_xy_validity` SHALL 为 `dual_view_estimated`
- **AND** `average_speed_validity` SHALL 为 `conditional`（不满足资格时 `unavailable`）
- **AND** `instantaneous_speed_validity` SHALL 为 `not_output_v1`

#### Scenario: 段级覆盖率诊断
- **WHEN** v3 含飞行段
- **THEN** 每段 SHALL 声明 `stereo_coverage` 与 `prediction_ratio`
- **AND** 二者 SHALL 用于 speed eligibility 与前端渲染判断

### Requirement: 前端按版本降级读取
系统 SHALL 使前端通过统一 `reconstructed-ball-trajectory` slug 读取历史与新产物，并按 schema version、segment reconstruction mode 与 metric eligibility 呈现；专项指标不可用 SHALL NOT 自动隐藏合格的估算展示段。

#### Scenario: v3 三维不可用但 2.5D 段存在
- **WHEN** 产物 3D overall status 为 `UNAVAILABLE` 且 `display_trajectory_status` 可用
- **THEN** 前端 SHALL 展示合格 2.5D 段并标记“估算球路/仅用于可视化”
- **AND** 平均球速、真实最高点和权威落点 SHALL 显示不可用

#### Scenario: 没有任何可显示段
- **WHEN** 三维与 2.5D 段均未通过各自最低门槛
- **THEN** 前端 SHALL 展示可解释空态与关键拒绝诊断
- **AND** SHALL NOT 生成伪造曲线

### Requirement: 分层可用状态写入产物
系统 SHALL 同时记录 3D overall status、`display_trajectory_status`、段级 display level 与指标级 validity，供前端分别控制球路和测量指标。

#### Scenario: 状态组合
- **WHEN** 写入混合产物
- **THEN** 3D overall status SHALL 为 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE`
- **AND** `display_trajectory_status` SHALL 为 `available`、`degraded` 或 `unavailable`
- **AND** 每个速度、高度和落点指标 SHALL 自带 validity/reason

### Requirement: 混合轨迹 provenance 与端点分类
每个 segment 和 sample SHALL 保存来源视角、detected/interpolated/predicted/stereo-anchor provenance、质量、时间范围与端点语义；场外端点 SHALL 保存相对于标准球场和比赛环境的分类。

#### Scenario: 保存可能真实界外的 bounce
- **WHEN** bounce 位于边线外但未被判为环境离群点
- **THEN** endpoint SHALL 保存 `court_location = outside_line`、`outcome_classification = legal_out_candidate`、证据置信度和标定不确定度
- **AND** MUST NOT 将 `legal_out_candidate` 解释为自动比赛判罚

