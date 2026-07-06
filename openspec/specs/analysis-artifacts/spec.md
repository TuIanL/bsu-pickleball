# analysis-artifacts Specification

## Purpose
Define stable storage paths, API artifact names, PipelineResult references, and JSON / JSONL contracts for analysis artifacts that can be produced by current and future match-analysis modules.

## Requirements
### Requirement: Deterministic artifact paths

系统 SHALL 为新增分析产物提供确定性的本地存储路径，并且这些路径 MUST 位于对应任务的 `outputs/{job_id}/` 目录下。

#### Scenario: Resolve new ball artifact paths

- **WHEN** 后端为任务 `job-123` 解析新增球相关 artifact 路径
- **THEN** `ball-overlay` MUST 映射到 `outputs/job-123/ball_overlay.json`
- **AND** `detections` MUST 映射到 `outputs/job-123/detections.jsonl`
- **AND** `ball-trajectory` MUST 映射到 `outputs/job-123/ball_trajectory.json`
- **AND** `cleaned-ball-trajectory` MUST 映射到 `outputs/job-123/cleaned_ball_trajectory.json`
- **AND** `bounce-events` MUST 映射到 `outputs/job-123/bounce_events.json`

#### Scenario: Resolve new visualization artifact paths

- **WHEN** 后端为任务 `job-123` 解析新增可视化 artifact 路径
- **THEN** `analysis-overlay-video` MUST 映射到 `outputs/job-123/analysis_overlay.mp4`
- **AND** `position-heatmaps` MUST 映射到 `outputs/job-123/position_visualizations/heatmaps/manifest.json`
- **AND** `position-scatter-plots` MUST 映射到 `outputs/job-123/position_visualizations/scatter_plots/manifest.json`

### Requirement: Pipeline result references new artifacts

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中描述新增分析产物的 path、url、status 和 detail 字段，且所有新增字段 MUST 可选以保持旧结果兼容。

#### Scenario: Completed result can reference generated artifacts

- **WHEN** 分析任务生成任一新增 artifact 文件
- **THEN** `AnalysisPipelineResult.artifacts` MUST 能包含该 artifact 的本地 path
- **AND** MUST 能包含对应 `/api/analysis/jobs/{job_id}/artifacts/{artifact_name}` URL
- **AND** MUST 能包含该 artifact 的 status 和 detail

#### Scenario: Completed result remains compatible without generated artifacts

- **WHEN** 分析任务没有生成新增球相关或可视化 artifact
- **THEN** `AnalysisPipelineResult` MUST 仍可序列化为成功结果
- **AND** 新增 artifact 字段 MUST 允许为 `null`
- **AND** 现有 tracking、pose、serve、player trajectory 和 court-view ROI 字段 MUST 不被移除或重命名

### Requirement: Artifact API accepts new artifact names

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受新增 artifact name，并按照产物类型返回合适响应。

#### Scenario: Read generated JSON artifact

- **WHEN** 客户端请求已存在的 `ball-overlay`、`ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events`、`position-heatmaps` 或 `position-scatter-plots`
- **THEN** API MUST 返回 200
- **AND** 响应 MUST 是 JSON

#### Scenario: Read generated JSONL artifact

- **WHEN** 客户端请求已存在的 `detections`
- **THEN** API MUST 返回 200
- **AND** 响应 MUST 保留逐行 JSONL 内容，或返回等价的逐帧记录集合
- **AND** 响应 MUST 不通过 JSON object 解析单行以外的整个文件而丢失记录边界

#### Scenario: Read generated video artifact

- **WHEN** 客户端请求已存在的 `analysis-overlay-video`
- **THEN** API MUST 返回 200
- **AND** 响应 MUST 使用 `video/mp4` media type

#### Scenario: Known artifact is not generated

- **WHEN** 客户端请求已知但当前任务未生成的新增 artifact
- **THEN** API MUST 返回 404
- **AND** MUST NOT 返回 422

#### Scenario: Existing artifact behavior is preserved

- **WHEN** 客户端请求现有 artifact name，例如 `tracking-overlay`、`pose-overlay`、`player-trajectories`、`serve-events` 或 `court-view-roi`
- **THEN** API MUST 保持现有成功和缺失文件行为

### Requirement: Detection JSONL schema is stable

系统 SHALL 定义 `detections.jsonl` 的逐帧记录 schema，用于保存球员、球和事件的原始检测事实。

#### Scenario: Detection record includes frame identity

- **WHEN** 后续算法写入 `detections.jsonl` 的任一行
- **THEN** 该行 MUST 是独立 JSON object
- **AND** MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `frame_index`
- **AND** MUST 包含 `timestamp_sec`
- **AND** MUST 包含 `fps`

#### Scenario: Detection record can describe players and ball

- **WHEN** 后续算法写入一帧检测记录
- **THEN** 记录 MUST 能包含 `players` 数组
- **AND** 每个 player 记录 MUST 能表达 `player_id`、`track_id`、`bbox_xyxy`、`footpoint_image_xy`、`court_xy` 和 `confidence`
- **AND** 记录 MUST 能包含 `ball` object
- **AND** ball 记录 MUST 能表达 `detected`、`image_xy`、`court_xy`、`confidence`、`candidate_count`、`accepted` 和 `rejection_reason`

#### Scenario: Detection record can describe frame events

- **WHEN** 后续算法写入一帧检测记录
- **THEN** 记录 MUST 能包含 `events`
- **AND** `events` MUST 能表达该帧是否包含 `bounce`、`serve` 或 `rally_id`

### Requirement: Ball trajectory schemas are stable

系统 SHALL 定义原始球轨迹、清洗球轨迹和球 overlay 的 JSON schema，使后续算法和前端可以消费一致字段。

#### Scenario: Raw ball trajectory can store samples

- **WHEN** 后续算法写入 `ball_trajectory.json`
- **THEN** 文件 MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含 `samples` 数组
- **AND** 每个 sample MUST 能表达 `frame_index`、`timestamp_sec`、`image_xy`、`court_xy`、`confidence` 和 `source`

#### Scenario: Cleaned ball trajectory can store filtering metadata

- **WHEN** 后续算法写入 `cleaned_ball_trajectory.json`
- **THEN** 文件 MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含 `samples` 数组
- **AND** MUST 能表达 `filtering` metadata，包括使用的平滑、插值或异常点剔除策略

#### Scenario: Ball overlay can drive browser rendering

- **WHEN** 后续算法写入 `ball_overlay.json`
- **THEN** 文件 MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含视频 source metadata
- **AND** MUST 包含可按帧渲染的 ball overlay 数据

### Requirement: Bounce events schema is stable

系统 SHALL 定义 `bounce_events.json` schema，用于保存弹跳事件和弹跳检测状态。

#### Scenario: Bounce event artifact can store no candidates

- **WHEN** 后续算法完成弹跳检测但没有发现弹跳事件
- **THEN** `bounce_events.json` MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含空的 `events` 数组

#### Scenario: Bounce event artifact can store candidate events

- **WHEN** 后续算法发现弹跳事件
- **THEN** 每个 event MUST 能表达 `event_id`
- **AND** MUST 能表达 `frame_index`
- **AND** MUST 能表达 `timestamp_sec`
- **AND** MUST 能表达 `image_xy`
- **AND** MUST 能表达 `court_xy`
- **AND** MUST 能表达 `confidence`
- **AND** MUST 能表达 `rally_id`
- **AND** MUST 能表达 `detection_method`

### Requirement: Visualization manifests are stable

系统 SHALL 使用 manifest JSON 描述位置热力图和散点图，而不是把目录 listing 作为 API 契约。

#### Scenario: Heatmap manifest describes generated images

- **WHEN** 后续可视化模块生成位置热力图
- **THEN** `position_visualizations/heatmaps/manifest.json` MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含 `items` 数组
- **AND** 每个 item MUST 能表达 `id`、`kind`、`label`、`file_name`、`url`、`width` 和 `height`

#### Scenario: Scatter plot manifest describes generated images

- **WHEN** 后续可视化模块生成位置散点图
- **THEN** `position_visualizations/scatter_plots/manifest.json` MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含 `items` 数组
- **AND** 每个 item MUST 能表达 `id`、`kind`、`label`、`file_name`、`url`、`width` 和 `height`

### Requirement: Analysis artifact configuration is available

系统 SHALL 提供后续新增分析产物所需的配置入口，且默认配置 MUST 不强制启用尚未实现的算法输出。

#### Scenario: Settings expose ball and visualization controls

- **WHEN** 后端加载 Settings
- **THEN** Settings MUST 能表达球模型路径
- **AND** MUST 能表达是否启用球检测
- **AND** MUST 能表达是否启用弹跳检测
- **AND** MUST 能表达是否启用分析叠加视频
- **AND** MUST 能表达是否启用位置可视化输出
- **AND** MUST 能表达可视化语言

#### Scenario: Defaults do not require unavailable algorithms

- **WHEN** 后端在没有新增环境变量的情况下启动
- **THEN** Settings MUST 不要求球模型文件存在
- **AND** MUST 不强制生成弹跳事件
- **AND** MUST 不强制生成标注视频
- **AND** MUST 不强制生成位置图
