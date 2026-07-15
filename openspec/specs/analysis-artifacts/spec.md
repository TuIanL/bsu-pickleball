# analysis-artifacts Specification

## Purpose
Define stable storage paths, API artifact names, PipelineResult references, and JSON / JSONL contracts for analysis artifacts that can be produced by current and future match-analysis modules.
## Requirements
### Requirement: Deterministic artifact paths

系统 SHALL 为新增分析产物提供确定性的本地存储路径。对于关联 CaptureTake 的录制任务，路径 MUST 位于对应会话目录的 `analysis/<job_id>/` 下；对于无 CaptureTake 的旧任务或上传任务，继续使用兼容的 `outputs/<job_id>/` 目录。

#### Scenario: Resolve capture analysis artifact paths
- **WHEN** 后端为关联 capture_take_id 的任务 `job-123` 解析分析产物路径
- **THEN** `ball-overlay`、`detections`、`ball-trajectory`、`bounce-events` 和可视化产物 MUST 位于该 take 目录的 `analysis/job-123/` 对应子路径
- **AND** 路径解析 SHALL 使用 SQLite 索引中的会话目录，不得重新猜测默认目录

#### Scenario: Preserve legacy artifact paths
- **WHEN** 后端为没有 capture_take_id 的旧任务解析 artifact 路径
- **THEN** 系统 SHALL 继续使用 `outputs/job-123/`
- **AND** 现有 API artifact 名称和读取行为 SHALL 保持兼容

### Requirement: Pipeline result references new artifacts

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中描述会话目录内新增分析产物的 path、url、status 和 detail 字段，且所有新增字段 MUST 可选以保持旧结果兼容。

#### Scenario: Capture analysis result references session artifacts
- **WHEN** 录制会话的分析任务生成 artifact 文件
- **THEN** `AnalysisPipelineResult.artifacts` MUST 包含该 artifact 的逻辑引用和实际文件状态
- **AND** artifact API SHALL 通过 job_id 和 SQLite 索引解析到对应 capture 会话目录

#### Scenario: Missing capture artifact remains compatible
- **WHEN** 录制会话没有生成某个可选 artifact
- **THEN** 对应 artifact 字段 MUST 允许为 `null`
- **AND** API MUST 返回 404 而不是暴露绝对路径或返回 422

### Requirement: Artifact API accepts new artifact names

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受新增 artifact name，并按照产物类型返回合适响应。

#### Scenario: Read generated JSON artifact

- **WHEN** 客户端请求已存在的 `ball-overlay`、`ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events`、`position-heatmaps`、`position-scatter-plots` 或 `player-render-trajectories`
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

#### Scenario: Ball overlay schema is concrete
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** 文件 MUST 包含 `schema_version`（`"ball_overlay.v1"`）
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `video_id`
- **AND** MUST 包含 `status` 和 `detail`
- **AND** MUST 包含 `source` object（video frame metadata）
- **AND** MUST 包含 `coverage` object（detection rate summary）
- **AND** MUST 包含 `frames` 数组（每个元素含 `frame_index`、`timestamp_seconds` 和 `ball` object）

#### Scenario: Ball overlay is ready for rendering
- **WHEN** 前端获取 `ball_overlay.json`
- **THEN** 前端 MAY 在对应 video timestamp 处渲染 ball bbox 或 center marker
- **AND** MISSING track_status 的帧 MAY 被跳过或显示为"未检测到"
- **AND** 前端 MUST NOT 需要额外解析 `ball_trajectory.json` 来渲染逐帧球位置

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
- **AND** 每个 item MUST 能表达 `title`、`description`、`file_path`、`artifact_url` 和 `source_artifacts`

#### Scenario: Scatter plot manifest describes generated images

- **WHEN** 后续可视化模块生成位置散点图
- **THEN** `position_visualizations/scatter_plots/manifest.json` MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含 `items` 数组
- **AND** 每个 item MUST 能表达 `id`、`kind`、`label`、`file_name`、`url`、`width` 和 `height`
- **AND** 每个 item MUST 能表达 `title`、`description`、`file_path`、`artifact_url` 和 `source_artifacts`

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

### Requirement: Ball engine artifacts declare coordinate units

球轨迹与弹跳点引擎写入已预留球相关 artifact 时，系统 SHALL 在 payload 中明确声明 image 坐标和 court 坐标的单位。

#### Scenario: Raw ball trajectory declares coordinate system
- **WHEN** 新球轨迹引擎写入 `ball_trajectory.json`
- **THEN** payload SHALL 声明 image 坐标单位为 pixels
- **AND** payload SHALL 声明 court 坐标单位为 feet
- **AND** payload SHALL 声明标准球场宽度为 20 ft、长度为 44 ft

#### Scenario: Cleaned ball trajectory declares coordinate system
- **WHEN** 新球轨迹引擎写入 `cleaned_ball_trajectory.json`
- **THEN** payload SHALL 声明 image 坐标单位为 pixels
- **AND** payload SHALL 声明 court 坐标单位为 feet
- **AND** payload SHALL 包含清洗和插值配置摘要

#### Scenario: Bounce events declare coordinate system
- **WHEN** 新球轨迹引擎写入 `bounce_events.json`
- **THEN** payload SHALL 声明 image 坐标单位为 pixels
- **AND** payload SHALL 声明 court 坐标单位为 feet
- **AND** payload SHALL 声明弹跳检测 method

### Requirement: Ball engine artifacts remain optional until pipeline integration

球轨迹与弹跳点引擎 artifact SHALL 保持可选，直到后续 change 明确将引擎接入当前真实分析 pipeline。

#### Scenario: Engine package exists but pipeline is not integrated
- **WHEN** 后端代码包含独立球轨迹与弹跳点引擎
- **THEN** `AnalysisPipelineResult.artifacts` MUST 仍允许球相关 artifact 字段为 null
- **AND** 当前 job 缺少球相关 artifact MUST NOT 被视为 pipeline 失败

#### Scenario: Artifact endpoint requests missing ball engine output
- **WHEN** 客户端请求已知的 `ball-trajectory`、`cleaned-ball-trajectory` 或 `bounce-events` artifact，但当前 job 未生成对应文件
- **THEN** API SHALL 返回 404
- **AND** API MUST NOT 返回 422

### Requirement: Active pipeline writes ball artifacts
系统 SHALL 在球分析 pipeline 阶段启用且输入满足时，将球相关 artifact 写入既有 deterministic paths，并在 `AnalysisPipelineResult.artifacts` 中引用。

#### Scenario: Ball artifacts are generated by a real job
- **WHEN** 真实分析任务启用球检测并成功生成球相关输出
- **THEN** 系统 SHALL 写入 `detections.jsonl`、`ball_trajectory.json` 和 `cleaned_ball_trajectory.json`
- **AND** 如果弹跳检测启用，系统 SHALL 写入 `bounce_events.json`
- **AND** 结果 artifacts SHALL 暴露对应 path、url、status 和 detail

#### Scenario: Ball artifacts are skipped
- **WHEN** 球分析配置关闭或依赖缺失导致 artifact 未生成
- **THEN** `AnalysisPipelineResult` SHALL 保持可序列化
- **AND** 新增 artifact 字段 SHALL 允许为 `null` 或携带 skipped/unavailable 状态

#### Scenario: Existing artifact API reads generated ball artifacts
- **WHEN** 客户端请求已生成的 `detections`、`ball-trajectory`、`cleaned-ball-trajectory` 或 `bounce-events`
- **THEN** API SHALL 返回对应内容和正确 media type
- **AND** JSONL 内容 MUST 保留逐行记录边界或返回等价逐帧记录集合

### Requirement: Artifact status distinguishes generated facts from future semantics
系统 SHALL 在新增 artifact metadata 中区分检测事实、候选事件和未实现的比赛语义。

#### Scenario: Bounce candidates are available
- **WHEN** `bounce_events.json` 包含候选事件
- **THEN** artifact detail SHALL 表达其为弹跳候选或规则检测结果
- **AND** MUST NOT 声明完整落点统计、得分原因或 rally 结果

#### Scenario: Future semantic artifact is unavailable
- **WHEN** 前端或报告请求尚未实现的击球、回合、比分或战术 artifact
- **THEN** 系统 SHALL 返回 unavailable、404 或省略该引用
- **AND** MUST NOT 复用球轨迹 artifact 伪装为语义 artifact

### Requirement: Ball overlay schema is concretely defined
系统 SHALL 将 `ball_overlay.json` 的 schema 从"可按帧渲染的 ball overlay 数据"具体化为包含 source metadata、coverage 摘要和 frames 数组的完整合同，使前端无需猜测 overlay 结构。

#### Scenario: Ball overlay declares source metadata
- **WHEN** `ball_overlay.json` 被写入
- **THEN** 文件 MUST 包含 `source` object，含 `width`（int）、`height`（int）、`fps`（float）、`frame_stride`（int）、`processed_frame_count`（int）
- **AND** `source` 字段 MUST 即使在 `status` 为 `unavailable` 或 `skipped` 时也存在

#### Scenario: Ball overlay declares coverage metadata
- **WHEN** `ball_overlay.json` 被写入
- **THEN** 文件 MUST 包含 `coverage` object
- **AND** `coverage` MUST 包含 `overlay_frame_count`（int）、`missing_frame_count`（int）、`detection_rate`（float）
- **AND** `detection_rate` MUST 等于 `overlay_frame_count / processed_frame_count`（当 `processed_frame_count > 0`）

#### Scenario: Ball overlay frame specifies per-frame ball data
- **WHEN** `ball_overlay.json` 被写入且有球候选
- **THEN** 每个 frame entry MUST 包含 `frame_index`（int）
- **AND** MUST 包含 `timestamp_seconds`（float）
- **AND** MUST 包含 `ball` object
- **AND** `ball` object MUST 包含 `center`（`{"x": float|null, "y": float|null}`）
- **AND** `ball` object MUST 包含 `bbox`（`[x1, y1, x2, y2]` 或 null）
- **AND** `ball` object MUST 包含 `confidence`（float|null）
- **AND** `ball` object MUST 包含 `track_status`（string: `"detected"`、`"missing"`、`"rejected"`）
- **AND** `ball` object MAY 包含 `court`（`{"x": float, "y": float, "unit": "ft"}` 或 null）

#### Scenario: Ball overlay frames are sparse
- **WHEN** `ball_overlay.json` 被写入
- **THEN** `frames` 数组 MUST 只包含球检测实际运行的抽样帧
- **AND** `frames` 数组 MUST NOT 强制包含每个 frame_index 的条目
- **AND** 帧覆盖缺失情况 MUST 由 `coverage` 元数据表达

### Requirement: Ball engine artifact contract is active
系统 SHALL 将球相关 artifact 合同从"保持可选直到 pipeline 集成"更新为"活跃集成状态"，因为 `AnalysisPipeline` 已在真实路径中写入这些 artifact。

#### Scenario: Pipeline writes all five ball artifacts when enabled
- **WHEN** 球检测启用且有视频和标定
- **THEN** pipeline SHALL 写入 `ball_overlay.json`
- **AND** pipeline SHALL 写入 `detections.jsonl`（包含 player + ball 记录）
- **AND** pipeline SHALL 写入 `ball_trajectory.json`
- **AND** pipeline SHALL 写入 `cleaned_ball_trajectory.json`
- **AND** pipeline SHALL 写入 `bounce_events.json`
- **AND** `AnalysisPipelineResult.artifacts` SHALL 包含上述 artifact 的 path、url、status 和 detail

#### Scenario: Ball artifacts are independently skippable
- **WHEN** 球检测未启用、无标定、无视频或依赖缺失
- **THEN** 缺失的 artifact 字段 SHALL 为 null 或携带 skipped/unavailable 状态
- **AND** 已生成的 tracking、pose、serve 等 artifact MUST 不受影响

### Requirement: Deterministic render trajectory artifact path

系统 SHALL 为 `player_render_trajectory.json` 提供确定性的本地存储路径。

#### Scenario: Resolve render trajectory artifact path

- **WHEN** 后端为任务 `job-123` 解析 render trajectory artifact 路径
- **THEN** `player-render-trajectories` MUST 映射到 `outputs/job-123/player_render_trajectory.json`
