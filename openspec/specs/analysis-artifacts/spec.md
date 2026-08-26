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

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中描述会话目录内新增分析产物的 path、url、status 和 detail 字段，且所有新增字段 MUST 可选以保持旧结果兼容。可选 artifact 即使没有文件，也 SHALL 保留可解释的状态。

#### Scenario: Capture analysis result references session artifacts

- **WHEN** 录制会话的分析任务生成 artifact 文件
- **THEN** `AnalysisPipelineResult.artifacts` MUST 包含该 artifact 的逻辑引用和实际文件状态
- **AND** artifact API SHALL 通过 job_id 和 SQLite 索引解析到对应 capture 会话目录

#### Scenario: Missing capture artifact remains compatible

- **WHEN** 录制会话没有生成某个可选 artifact
- **THEN** 对应 artifact 字段 MUST 允许为 `null`
- **AND** API MUST 返回 404 而不是暴露绝对路径或返回 422
- **AND** 结果 SHALL 继续返回该 artifact 的 `status` 和 `detail`（若调用方支持）

#### Scenario: Optional artifact status is explicit

- **WHEN** pipeline 处理一个可选 artifact
- **THEN** `status` SHALL 为 `available`、`skipped`、`unavailable` 或 `failed` 之一
- **AND** `detail` SHALL 说明跳过原因、能力不可用原因或执行错误
- **AND** `available` SHALL 仅用于文件已成功写入并可通过 artifact API 读取的情况

#### Scenario: Artifact state survives missing file

- **WHEN** artifact status 为 `skipped`、`unavailable` 或 `failed` 且没有对应文件
- **THEN** `path` 和 `url` MAY 为 `null`
- **AND** `status` 与 `detail` MUST NOT 被清空或根据 `path` 重新推导为 `null`

### Requirement: Artifact API accepts new artifact names

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受新增 artifact name，并按照产物类型返回合适响应。

#### Scenario: Read generated JSON artifact

- **WHEN** 客户端请求已存在的 `ball-overlay`、`ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events`、`position-heatmaps`、`position-scatter-plots` 或 `player-render-trajectories`
- **THEN** API MUST 返回 200
- **AND** 响应 MUST 是 JSON

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

### Requirement: fused player overlay 产物字段

分析产物 contract SHALL 新增 `fused_player_overlay_json_path` / `fused_player_overlay_url` / `fused_player_overlay_status` / `fused_player_overlay_detail` 四字段，作为 joint 模式正式球员叠加层的产物契约（对应 `multiview-fused-player-overlay.v1` artifact）。

#### Scenario: joint 模式填充字段

- **WHEN** joint_tracking_v2 任务完成 compose 且 fused overlay 生成成功
- **THEN** `fused_player_overlay_json_path` SHALL 指向 Parent 命名空间的 overlay JSON 文件
- **AND** `fused_player_overlay_url` SHALL 为浏览器可访问的 artifact URL（非本地绝对路径）
- **AND** `fused_player_overlay_status` SHALL 为 `available`

#### Scenario: 生成失败显式状态

- **WHEN** fused overlay 生成失败
- **THEN** `fused_player_overlay_status` SHALL 为 `unavailable`
- **AND** `fused_player_overlay_detail` SHALL 说明失败原因

#### Scenario: 非 joint 模式不填充

- **WHEN** 任务执行模式为单摄或 late_fusion_v1
- **THEN** `fused_player_overlay_*` 字段 SHALL 保持未设置（null）
- **AND** 既有 `tracking_overlay_*` 字段行为 SHALL 不变

### Requirement: performance_insights 产物字段与再生成语义

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中新增 `performance_insights_json_path` / `performance_insights_url` / `performance_insights_status` / `performance_insights_detail` 四个可选字段，作为 `performance-insights.v1` artifact 的产物契约；该产物由 post-pipeline 的 Insight Engine 服务写入确定性路径（capture 任务位于 `analysis/<job_id>/` 下，普通任务位于 `outputs/<job_id>/`），并支持仅凭已落盘输入产物独立再生成。

#### Scenario: 真实任务填充产物字段

- **WHEN** 真实分析任务完成且 insights 生成成功
- **THEN** `performance_insights_json_path` SHALL 指向该任务的 `performance_insights.json` 文件
- **AND** `performance_insights_url` SHALL 为浏览器可访问的 artifact URL
- **AND** `performance_insights_status` SHALL 为 `available`

#### Scenario: 洞察生成失败显式状态

- **WHEN** insights 生成失败或被跳过
- **THEN** `performance_insights_status` SHALL 为 `skipped`、`unavailable` 或 `failed` 之一，`performance_insights_detail` SHALL 说明原因
- **AND** 该状态 MUST NOT 使视觉 pipeline 结果本身判定为失败

#### Scenario: artifact API 读取洞察产物

- **WHEN** 客户端请求已生成的 `performance-insights` artifact
- **THEN** API SHALL 返回 200 与 JSON 内容
- **WHEN** 客户端请求已知但当前任务未生成的 `performance-insights`
- **THEN** API SHALL 返回 404，MUST NOT 返回 422

#### Scenario: 再生成覆盖旧版本

- **WHEN** Insight Engine 以新 `rule_profile_version` 对同一 job 再生成
- **THEN** 系统 SHALL 原子覆盖同一确定性路径下的 `performance_insights.json`
- **AND** 再生成过程 MUST NOT 触发视觉分析阶段重跑或改写视觉 artifacts

### Requirement: 球立体证据产物契约
系统 SHALL 为 `multiview_ball_stereo_evidence` 提供稳定的 artifact url / path / status 契约，供前端按需获取。

#### Scenario: 固定存储与访问路径
- **WHEN** 系统写入球立体证据
- **THEN** 文件 SHALL 存入固定路径 `multiview_ball_stereo_evidence.json`
- **AND** 该 slug 可通过既有 artifact 访问机制按需请求，无需后端主动加载重产物

#### Scenario: 状态机一致
- **WHEN** 前端请求球立体证据
- **THEN** 该 artifact SHALL 沿用与现有产物一致的 `available / unavailable / skipped / failed` 状态语义
- **AND** 缺失或不可用时不得返回 422 破坏分析展示

### Requirement: Parent 结果正式引用双摄球产物
joint 任务的 Parent `AnalysisResult.artifacts` SHALL 正式引用 `reconstructed_ball_trajectory.v3` 与 `multiview_ball_stereo_evidence.v1`。每个产物 SHALL 同时提供内部 path、公开 URL、status 和 detail；前端 MUST 只从 Parent 引用读取公开入口，不得依赖子任务私有路径。

#### Scenario: 双摄球产物可用
- **WHEN** joint 任务完成球分析并生成两个 JSON 产物
- **THEN** Parent artifacts SHALL 包含两个产物的 `*_json_path`、`*_url`、`*_status` 与 `*_detail`
- **AND** URL SHALL 能通过现有 artifact API 获取

#### Scenario: 双摄球产物不可用
- **WHEN** 球分析失败、超时或质量不足
- **THEN** Parent artifacts SHALL 仍提供对应 status/detail
- **AND** 缺失 path/url 不得被解释为分析尚未执行

### Requirement: 双摄球产物状态与 schema 版本一致
双摄球 evidence SHALL 使用 `multiview_ball_stereo_evidence.v1`，用户轨迹 SHALL 使用 `reconstructed_ball_trajectory.v3`。artifact 状态 SHALL 与产物 `overall_status`、`schema_version` 和质量信息保持一致，MUST NOT 发布一个版本字段与内容不匹配的产物。

#### Scenario: v3 轨迹发布
- **WHEN** Parent 引用 reconstructed ball trajectory
- **THEN** JSON SHALL 声明 v3 schema
- **AND** SHALL 包含整体状态、validity 分级、落点信息与可用的三维质量指标

#### Scenario: evidence 发布
- **WHEN** Parent 引用 stereo evidence
- **THEN** JSON SHALL 声明 v1 schema
- **AND** 每条证据 SHALL 可追溯到 canonical tick、双摄帧和候选输入

### Requirement: 球相关 artifact API 保持安全边界
artifact API SHALL 允许读取上述两个公开 artifact 名称，并继续拒绝任意文件路径。API 的公开返回 SHALL 只暴露任务作用域内的文件内容或受控下载响应。

#### Scenario: 读取 Parent 球路产物
- **WHEN** 客户端使用合法 task id 与 `reconstructed-ball-trajectory` 或 `multiview-ball-stereo-evidence` 请求 artifact
- **THEN** API SHALL 返回对应 JSON
- **AND** 返回内容 SHALL 来自该 task 的已发布路径

#### Scenario: 越权读取
- **WHEN** 请求携带其他 task 的路径、绝对路径或路径穿越片段
- **THEN** API SHALL 拒绝请求
- **AND** SHALL 不泄露宿主文件系统信息

### Requirement: Canonical Rally/Shot artifact paths and references

系统 SHALL 为 `shot-rally-events` 和 `metric-snapshot` 提供确定性的 artifact path、url、status 和 detail 引用。关联 CaptureTake 的任务 SHALL 将文件写入对应会话目录的 `analysis/<job_id>/` 下；旧任务或上传任务 SHALL 使用兼容的 `outputs/<job_id>/` 目录。`AnalysisPipelineResult.artifacts` 中的新增字段 SHALL 可选，以保持旧结果兼容。

#### Scenario: CaptureTake 任务生成事件产物

- **WHEN** 关联 CaptureTake 的 job `job-123` 生成 canonical 事件和指标快照
- **THEN** 两个文件 SHALL 位于该 take 的 `analysis/job-123/` 目录
- **AND** Pipeline result SHALL 暴露两个 artifact 的公开 url、状态和详情

#### Scenario: 旧任务保持兼容

- **WHEN** 没有 `capture_take_id` 的旧 job 生成或读取新 artifact
- **THEN** 系统 SHALL 使用 `outputs/job-123/` 下的兼容路径
- **AND** 缺少新 artifact SHALL NOT 破坏旧 tracking、pose、trajectory 或 report 请求

### Requirement: Canonical event artifact API

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受 `shot-rally-events` 和 `metric-snapshot`，并返回对应 JSON。已知但未生成的 artifact SHALL 返回 404；路径穿越、绝对路径和跨 job artifact 请求 SHALL 被拒绝。

#### Scenario: 读取可用事件产物

- **WHEN** 客户端请求已生成的 `shot-rally-events`
- **THEN** API SHALL 返回 200
- **AND** Content SHALL 是 `shot-rally-events.v1` JSON

#### Scenario: 读取未生成产物

- **WHEN** 客户端请求当前 job 尚未生成的 `metric-snapshot`
- **THEN** API SHALL 返回 404
- **AND** MUST NOT 返回 422 或模拟数据

### Requirement: Canonical event schema metadata

事件和指标 artifact SHALL 在文件和 Pipeline result 中保持 schema version、status、detail 和实际可用性一致。`available` 只允许用于文件已成功写入且 API 可读的情况；`skipped`、`unavailable` 或 `failed` 必须携带原因。

#### Scenario: 生成状态一致

- **WHEN** 事件组合阶段因缺少球员归属输入而降级
- **THEN** 文件 status、Pipeline result status 和 detail SHALL 表达同一个降级原因
- **AND** 不得仅因 path 存在就把 artifact 标记为 available

#### Scenario: 空事件结果

- **WHEN** 组合阶段成功完成但没有可确认的 Shot
- **THEN** `shot_rally_events.json` MAY 为 available 且包含空数组
- **AND** detail SHALL 说明没有确认事件，而不是省略该状态

### Requirement: Normalized metric artifact paths and references

系统 SHALL 为 `normalized-metrics` 提供确定性的 artifact path、url、status 和 detail 引用。关联 CaptureTake 的任务 SHALL 将文件写入对应会话目录的 `analysis/<job_id>/normalized_metrics.json`；旧任务或上传任务 SHALL 使用兼容的 `outputs/<job_id>/normalized_metrics.json`。`AnalysisPipelineResult.artifacts` 中的新增字段 SHALL 可选，以保持旧结果兼容。

#### Scenario: CaptureTake 任务生成 normalized artifact

- **WHEN** 关联 CaptureTake 的 job `job-123` 生成 normalized metric snapshot
- **THEN** 文件 SHALL 位于该 take 的 `analysis/job-123/normalized_metrics.json`
- **AND** Pipeline result SHALL 暴露公开 url、status、detail 和可选 path

#### Scenario: 旧任务保持兼容

- **WHEN** 没有 `capture_take_id` 的旧 job 读取或生成 normalized artifact
- **THEN** 系统 SHALL 使用 `outputs/job-123/normalized_metrics.json`
- **AND** 缺少该可选 artifact SHALL NOT 破坏旧 tracking、trajectory、report 或 insights 请求

### Requirement: Normalized metric artifact API

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 中接受 `normalized-metrics`，并返回 `normalized-metric-snapshot.v1` JSON。已知但未生成的 artifact SHALL 返回 404；绝对路径、路径穿越和跨 job artifact 请求 SHALL 被拒绝。

#### Scenario: 读取可用 normalized artifact

- **WHEN** 客户端请求已生成的 `normalized-metrics`
- **THEN** API SHALL 返回 200
- **AND** response SHALL 是 `normalized-metric-snapshot.v1` JSON

#### Scenario: 读取未生成 normalized artifact

- **WHEN** 当前 job 没有生成 normalized artifact
- **THEN** API SHALL 返回 404
- **AND** MUST NOT 返回 422、默认分数或模拟数据

### Requirement: Normalized artifact state consistency

normalized artifact 文件、Pipeline result 和 API 可用性 SHALL 保持 schema version、status、detail 和实际文件状态一致。`available` 只允许用于文件成功写入且 API 可读的情况；`skipped`、`unavailable` 或 `failed` SHALL 携带原因。

#### Scenario: 参考 profile 缺失

- **WHEN** 输入 metric snapshot 可读但没有适用的 scoring reference profile
- **THEN** normalized artifact MAY 写入并标记为 `available`（包含 unsupported entries），或按实现选择 `unavailable`
- **AND** detail SHALL 明确说明 profile 缺失
- **AND** SHALL NOT 生成默认 utility 或 overall score

#### Scenario: 空 normalized 结果

- **WHEN** job 已完成但没有任何指标满足规范化条件
- **THEN** artifact MAY 为 `available` 且 `metrics` 为空或全为降级条目
- **AND** `score_coverage` 和 detail SHALL 说明没有 eligible metric

### Requirement: Semantic boundary evaluation artifact is versioned and optional

系统 SHALL 支持可选的 `ball_semantic_boundary_eval.v1` artifact，用于记录语义边界 replay、证据摘要、adjudication 结果和评估指标；该 artifact 不得替代或破坏既有球轨迹、球 overlay 和球员分析 artifact。

#### Scenario: Evaluation artifact has a deterministic path and status

- **WHEN** 启用语义边界评估的 CaptureTake 分析任务完成回放
- **THEN** artifact SHALL 写入对应 session 的 `analysis/<job_id>/ball_semantic_boundary_eval.json`
- **AND** result SHALL 暴露 schema version、path/url、status 和 detail

#### Scenario: Legacy output path remains compatible

- **WHEN** 任务没有 CaptureTake 上下文而使用旧 `outputs/<job_id>/` 路径
- **THEN** 系统 SHALL 将 artifact 写入兼容 outputs 目录
- **AND** 既有 artifact path resolver 和历史球轨迹读取行为 SHALL 保持不变

#### Scenario: Missing or disabled evaluation is explicit

- **WHEN** 语义边界评估关闭、没有参考标签或评估依赖不可用
- **THEN** artifact status SHALL 为 `skipped`、`unavailable` 或 `partial`
- **AND** 主球检测、球跟踪、球路和球员分析 SHALL 不因此失败

### Requirement: Semantic boundary evaluation payload supports replay and metrics

`ball_semantic_boundary_eval.v1` SHALL 包含 job/take identity、policy version、rollout snapshot、source metadata、按 canonical timestamp 排序的 tick records、evidence summary、pending/confirmed phase、boundary action、formal candidate before/after、segment id、fallback/error 和 metrics。

#### Scenario: Tick records can be replayed

- **WHEN** 客户端或离线工具读取 evaluation artifact
- **THEN** 每个 tick record SHALL 能恢复 phase、authority、evidence ids、adjudication state 和 action result
- **AND** 同一输入按相同 policy version 重放 SHALL 得到确定性结果

#### Scenario: Metrics distinguish recommendation and execution

- **WHEN** fixture 或人工参考边界存在
- **THEN** metrics SHALL 分别记录 Shadow recommendation、Enforced execution 和 reference comparison
- **AND** 至少包含 boundary precision、recall、confirmation latency、false suppression 和 cross-segment contamination

#### Scenario: Artifact API accepts the known artifact name

- **WHEN** 客户端请求当前任务已有的 `ball-semantic-boundary-eval`
- **THEN** API SHALL 返回 200 JSON
- **AND** 当 artifact 未生成时 SHALL 返回 404，而不是 422

