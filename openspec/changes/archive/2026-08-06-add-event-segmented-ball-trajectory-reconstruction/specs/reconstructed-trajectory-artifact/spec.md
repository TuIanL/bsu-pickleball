## ADDED Requirements
### Requirement: 重建产物 JSON 契约
系统 SHALL 输出结构化重建产物 `reconstructed_ball_trajectory.json`，包含 schema 版本、重建模式、坐标语义、事件列表与飞行段列表。

#### Scenario: 产物顶层结构
- **WHEN** 系统输出重建产物
- **THEN** 产物顶层 SHALL 包含 `schema_version`、`reconstruction_mode`、`coordinate_semantics`、`events`、`segments`
- **AND** `coordinate_semantics` SHALL 包含 `xy = court_ft_visual_estimate`、`z = estimated_height_ft` 与 `metric_validity = visualization_only`

#### Scenario: 事件列表
- **WHEN** 产物包含事件
- **THEN** `events` 数组 SHALL 包含击球、弹地与 serve 重置等边界事件，每个事件含 `event_id`、`event_type`、`frame_index`、`timestamp_sec` 与 `confidence`

#### Scenario: 飞行段结构
- **WHEN** 产物包含飞行段
- **THEN** 每个段 SHALL 包含 `segment_id`、`start_event_id`、`end_event_id`、`start_event_type`、`end_event_type`、`fit_space`、`model`、`anchors`、`quality` 与 `samples`
- **AND** `model` SHALL 记录为 `weighted_huber_anchor_constrained`
- **AND** `fit_space` SHALL 记录为 `image_px`

### Requirement: 重建样本来源分类
系统 SHALL 为每个重建样本标记来源，模型推算点不得伪装成真实检测点。

#### Scenario: 来源取值
- **WHEN** 系统输出重建样本
- **THEN** 每个样本的 `source` SHALL 为 `detected / interpolated / model_predicted / anchor` 之一

#### Scenario: 检测点来源
- **WHEN** 样本由真实检测观测构成
- **THEN** 样本 `source` SHALL 为 `detected` 且携带原始 `confidence`

#### Scenario: 推算点来源
- **WHEN** 样本由模型补齐或拟合生成
- **THEN** 样本 `source` SHALL 为 `model_predicted` 或 `interpolated`
- **AND** 样本 SHALL 携带 `gap_length_frames`（若适用）
- **AND** 前端 SHALL 以可区分样式（虚线/浅色）绘制推算点

#### Scenario: 锚点来源
- **WHEN** 样本对应事件锚点位置
- **THEN** 样本 `source` SHALL 为 `anchor`

### Requirement: 高度字段语义
系统 SHALL 在每个重建样本中保存估算高度、高度来源、高度置信度与高度不确定度。

#### Scenario: 样本高度字段
- **WHEN** 系统输出重建样本
- **THEN** 样本 SHALL 包含 `estimated_height_ft`、`height_source`、`height_confidence` 与可选的 `height_uncertainty_ft`

#### Scenario: 先验高度标注
- **WHEN** 高度来源为全局先验
- **THEN** `height_source` SHALL 为 `global_contact_prior`
- **AND** `height_confidence` SHALL 为低值（如 0.25 量级）

#### Scenario: serve 先验标注
- **WHEN** 高度来源为 serve 先验
- **THEN** `height_source` SHALL 为 `serve_prior`

### Requirement: 弹地与击球边界高度不变量
系统 SHALL 保证弹地边界高度严格为零，击球边界不得被默认设为零。

#### Scenario: 弹地边界高度为零
- **WHEN** 样本位于弹地事件锚点
- **THEN** `estimated_height_ft` SHALL 严格为 0

#### Scenario: 击球边界高度非零
- **WHEN** 样本位于击球事件锚点
- **THEN** `estimated_height_ft` SHALL 为接触高度先验值而非 0
- **AND** MUST NOT 被前端统一高度公式强制置零

### Requirement: 存储路径与 API slug
系统 SHALL 提供重建产物的固定存储路径与 API 访问方式。

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
系统 SHALL 保证重建产物中事件 ID、段 ID 与重建结果在相同输入下确定。

#### Scenario: 重复运行结果一致
- **WHEN** 对同一输入重复运行完整重建链
- **THEN** 事件 ID、`segment_id` 与重建样本序列 SHALL 完全一致
