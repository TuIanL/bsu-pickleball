# match-analysis-pipeline-capabilities Specification

## Purpose
TBD - created by archiving change activate-match-analysis-pipeline-capabilities. Update Purpose after archive.
## Requirements
### Requirement: 可配置激活比赛分析能力
系统 SHALL 通过配置和依赖检查激活新增比赛分析能力，而不是把历史 MVP 边界作为永久禁用规则。系统 SHALL 额外支持 `PICKLEBALL_BALL_ANALYSIS_STRICT` 配置（默认 `false`）控制球分析失败是否升级为 pipeline 失败。

#### Scenario: 默认环境保持现有流程
- **WHEN** 后端在没有新增球分析启用配置的环境中运行真实分析任务
- **THEN** 系统 SHALL 保持现有 player、pose、tracking、serve 和 movement 输出兼容
- **AND** 系统 MUST NOT 要求球模型文件或 CUDA 环境存在

#### Scenario: 配置启用新增能力
- **WHEN** 管理员启用球检测、弹跳检测或可视化输出配置且依赖满足
- **THEN** pipeline SHALL 执行对应分析阶段并在结果中暴露阶段状态、artifact 引用和诊断摘要
- **AND** ball-trajectory 和 bounce-detection 阶段 SHALL 作为两个独立用户可见阶段出现

#### Scenario: 配置启用但依赖缺失
- **WHEN** 新增能力被启用但模型路径、adapter、输入 artifact 或运行时依赖不可用
- **THEN** pipeline SHALL 将对应阶段标记为 `skipped`、`unavailable` 或 `failed`
- **AND** 基础 player、pose、tracking、serve 和 movement 结果 MUST 继续可用

#### Scenario: Strict mode 升级球分析失败
- **WHEN** `PICKLEBALL_BALL_ANALYSIS_STRICT=true` 且球分析链路异常
- **THEN** pipeline SHALL 将整个任务标记为 `failed`
- **AND** 失败信息 SHALL 指向具体失败的球分析阶段

### Requirement: 事实 artifact 优先于语义结论
系统 SHALL 优先输出可复盘的检测、轨迹、弹跳候选和可视化 artifact，并把完整比赛语义留给后续能力。

#### Scenario: 事实 artifact 可用
- **WHEN** 真实分析任务生成球检测、球轨迹、清洗轨迹或弹跳候选 artifact
- **THEN** 系统 SHALL 允许前端和报告展示这些 artifact 支撑的事实、候选点和状态
- **AND** 展示内容 MUST 引用真实任务 artifact 而不是模拟数据

#### Scenario: 需要完整比赛语义
- **WHEN** UI、报告或 API 需要击球类型、完整回合边界、比分、犯规、落点统计或战术结论
- **THEN** 系统 SHALL 在专门能力实现前标记为 unavailable 或省略
- **AND** 系统 MUST NOT 从球轨迹或弹跳候选直接伪造这些结论

### Requirement: 能力状态可复盘
系统 SHALL 为新增分析能力提供可复盘的状态、原因和 counters，使用户和开发者能区分配置关闭、依赖缺失、无检测、部分可用和已完成。

#### Scenario: 阶段被配置关闭
- **WHEN** 新增分析阶段因配置未启用而不运行
- **THEN** pipeline 阶段记录或结果摘要 SHALL 表达 `skipped` 状态和配置原因

#### Scenario: 阶段运行但没有候选
- **WHEN** 新增分析阶段成功运行但没有达到阈值的候选或事件
- **THEN** 对应 artifact 或阶段记录 SHALL 表达 `no_candidates` 或等价状态
- **AND** SHALL 提供输入覆盖、阈值或候选数量摘要

#### Scenario: 阶段部分可用
- **WHEN** 新增分析阶段只能使用部分输入生成结果
- **THEN** 对应状态 SHALL 表达 `partial`
- **AND** SHALL 说明缺失输入和仍然使用的信号

### Requirement: Pipeline stages converge to ball-trajectory and bounce-detection
系统 SHALL 向用户暴露两个球分析阶段 —— `ball-trajectory`（球检测、候选筛选、轨迹采样、raw trajectory、ball_overlay、detections.jsonl）和 `bounce-detection`（轨迹清洗、插值、弹跳检测、cleaned_ball_trajectory、bounce_events）—— 而不暴露内部的 `ball-detection` 或 `trajectory-cleaning` 阶段。

#### Scenario: Ball analysis produces two visible stages
- **WHEN** 球检测启用且 pipeline 成功生成球 artifact
- **THEN** pipeline stages MUST 包含 `ball-trajectory`（status 为 `done`）
- **AND** pipeline stages MUST 包含 `bounce-detection`（status 为 `done`、`no_candidates` 或 `skipped`）
- **AND** pipeline stages MUST NOT 包含 `ball-detection` 或 `trajectory-cleaning` 作为独立阶段

#### Scenario: Ball detection details are preserved in counters
- **WHEN** pipeline 生成 `ball-trajectory` 阶段
- **THEN** `ball-trajectory` 阶段的 counters MUST 包含 `model_enabled`、`processed_frame_count`、`ball_detection_count`、`raw_sample_count`、`detection_rate`
- **AND** 这些 counters MUST 可 JSON 序列化

#### Scenario: Ball analysis is disabled
- **WHEN** 球检测配置关闭
- **THEN** `ball-trajectory` stage status MUST 为 `skipped`
- **AND** `bounce-detection` stage status MUST 为 `skipped`
- **AND** detail MUST 说明跳过原因（配置关闭或缺少标定）

### Requirement: Ball analysis strict mode controls failure escalation
系统 SHALL 提供配置项 `PICKLEBALL_BALL_ANALYSIS_STRICT`（默认 `false`），控制球分析链路异常是否导致整个 pipeline failed。

#### Scenario: Default mode keeps ball failures non-fatal
- **WHEN** `PICKLEBALL_BALL_ANALYSIS_STRICT=false`（默认）且球检测中途异常
- **THEN** `ball-trajectory` stage status MUST 为 `failed` 或 `unavailable`
- **AND** `bounce-detection` stage status MUST 为 `skipped`
- **AND** pipeline result status MUST 仍为 `completed`
- **AND** player tracking、pose、serve 和 movement 结果 MUST 继续可用

#### Scenario: Strict mode escalates ball failures to pipeline failure
- **WHEN** `PICKLEBALL_BALL_ANALYSIS_STRICT=true` 且球检测或弹跳检测异常
- **THEN** pipeline result status MUST 为 `failed`
- **AND** failed stage MUST 指向 `ball-trajectory` 或 `bounce-detection`
- **AND** error message MUST 可定位具体失败原因

#### Scenario: Strict mode does not affect video-read or player-tracking failures
- **WHEN** `PICKLEBALL_BALL_ANALYSIS_STRICT=true` 但视频读取或 player tracking 主流程失败
- **THEN** pipeline MUST 仍然 failed（因为视频/tracking 失败在任何模式下都致命）
- **AND** ball_analysis_strict MUST NOT 改变视频/tracking 的失败行为

#### Scenario: No-candidates is never treated as failure
- **WHEN** 弹跳检测运行但未发现弹跳候选（`no_candidates`）
- **THEN** `bounce-detection` stage status MUST 为 `done`
- **AND** counters 或 detail MUST 表达 `no_candidates`
- **AND** pipeline MUST NOT failed（无论 strict mode 值）

### Requirement: Pipeline progress for ball analysis stages
系统 SHALL 在 ball 分析阶段开始时通过 `progress_callback` 发送 `active` 状态，在阶段完成时发送 `done`、`skipped` 或 `failed` 状态。

#### Scenario: Ball trajectory stage sends progress
- **WHEN** ball 分析开始写入 artifact 和创建阶段
- **THEN** pipeline SHALL 通过 `progress_callback` 通知 `ball-trajectory` 阶段状态变化
- **AND** 在 artifact 写入完成后 SHALL 发送 `done` 或 `skipped` 状态

#### Scenario: Bounce detection stage sends progress
- **WHEN** 弹跳检测后处理完成
- **THEN** pipeline SHALL 通过 `progress_callback` 通知 `bounce-detection` 阶段状态变化
- **AND** 发送 `done`、`skipped` 或 `failed` 状态

#### Scenario: Progress events are stage-level only
- **WHEN** ball 分析运行在长视频上
- **THEN** pipeline MUST NOT 逐帧发送 progress 回调
- **AND** 只在阶段边界（开始/完成）发送 progress 事件

### Requirement: Stage counters provide diagnostic detail
系统 SHALL 为 `ball-trajectory` 和 `bounce-detection` 阶段提供完整的 counters，使前端和调试者无需读取 artifact 文件即可了解阶段执行情况。

#### Scenario: Ball trajectory stage counters
- **WHEN** `ball-trajectory` 阶段完成
- **THEN** `stage.counters` MUST 包含 `processed_frame_count`（int）
- **AND** MUST 包含 `ball_detection_count`（int，有候选点的帧数）
- **AND** MUST 包含 `raw_sample_count`（int，总 sample 数）
- **AND** MUST 包含 `missing_frame_count`（int，无候选或未接受的帧数）
- **AND** MUST 包含 `detection_rate`（float，`ball_detection_count / processed_frame_count`）
- **AND** MUST 包含 `frame_stride`（int）
- **AND** MUST 包含 `court_unit`（string，`"ft"`）
- **AND** MUST 包含 `model_enabled`（bool）

#### Scenario: Bounce detection stage counters
- **WHEN** `bounce-detection` 阶段完成
- **THEN** `stage.counters` MUST 包含 `input_sample_count`（int，输入的 raw sample 数）
- **AND** MUST 包含 `cleaned_sample_count`（int，清洗后的轨迹点数）
- **AND** MUST 包含 `interpolated_sample_count`（int，插值填充的点数）
- **AND** MUST 包含 `bounce_event_count`（int，检测到的弹跳候选数）
- **AND** MUST 包含 `detection_mode`（string，`"rule_based"` 或等价标识）
- **AND** MUST 包含 `status`（string，`available`、`no_candidates` 等）

#### Scenario: Counters are consistent with artifact content
- **WHEN** `ball-trajectory` counters 报告 `ball_detection_count = 318`
- **THEN** `ball_trajectory.json` 中 `samples` 的 `accepted=true` 记录数 MUST 一致
- **AND** `ball_overlay.json` 中 `coverage.overlay_frame_count` MUST 一致

### Requirement: 指标状态区分"不适用"和"未识别到"
系统 SHALL 为每个指标提供 `status` 字段，明确区分"该指标不适用"（如单打中的双打间距）和"该指标应计算但未识别到足够数据"（如双打中同侧球员不足）。

#### Scenario: 单打中 doubles_spacing 为 not_applicable
- **WHEN** `match_context.enable_doubles_spacing=False`（单打）
- **THEN** `metric_statuses["doubles_spacing"]` SHALL 为 `{"status": "not_applicable", "reason": "singles_match"}`
- **AND** `doubles_spacing: List[DoublesSpacingSummary]` SHALL 为空数组（保持类型兼容）
- **AND** 系统 SHALL NOT 调用 `doubles_spacing()` 函数

#### Scenario: 双打中 doubles_spacing 为 insufficient_players
- **WHEN** `match_context.enable_doubles_spacing=True` 但 `observed_player_count < expected_player_count`（如同侧只识别出 1 人）
- **THEN** `metric_statuses["doubles_spacing"]` SHALL 为 `{"status": "insufficient_players", "expected_player_count": 4, "observed_player_count": 3}`
- **AND** `doubles_spacing: List[DoublesSpacingSummary]` SHALL 为空数组

#### Scenario: 正常双打
- **WHEN** `match_context.enable_doubles_spacing=True` 且识别到 4 名球员
- **THEN** `metric_statuses["doubles_spacing"]` SHALL 为 `{"status": "available"}`
- **AND** `doubles_spacing: List[DoublesSpacingSummary]` SHALL 包含正常计算的间距数据

### Requirement: 报告隐藏单打不适用模块
系统 SHALL 在分析结果持久化后，使前端能通过 `match_context` 和指标 `status` 字段判断是否显示双打专属模块。

#### Scenario: 单打报告隐藏双打间距
- **WHEN** 前端渲染单打分析报告且 `doubles_spacing.status === "not_applicable"`
- **THEN** 前端 SHALL 隐藏"搭档间距"和"双打协同"等双打专属模块
- **AND** SHALL 不渲染空白的组件占位

#### Scenario: 双打报告正常显示
- **WHEN** 前端渲染双打分析报告且 `doubles_spacing.status === "available"`
- **THEN** 前端 SHALL 正常显示双打间距和配合指标

### Requirement: 任务签名包含 matchFormat
系统 SHALL 确保 matchFormat 参与分析任务签名计算，使同一视频以不同赛制提交时产生不同的任务签名和不同的分析结果。

#### Scenario: 同视频不同赛制产生不同签名
- **WHEN** 同一 `video_id` 以 `matchFormat="singles"` 创建任务
- **AND** 再以 `matchFormat="doubles"` 创建任务
- **THEN** 两个任务 SHALL 具有不同的输入签名
- **AND** SHALL 分别执行两次独立的分析

#### Scenario: 同视频同赛制复用结果
- **WHEN** 同一 `video_id` 以 `matchFormat="singles"` 提交两次
- **THEN** 第二次提交 SHALL 引用或返回原有分析结果（符合现有去重逻辑）

### Requirement: Task-level inference toggles drive pipeline execution
The system SHALL honor per-job inference toggles when executing an analysis pipeline, overriding the global configuration for that job while preserving the global defaults for jobs that do not specify toggles.

#### Scenario: Job enables model inference
- **WHEN** an analysis job carries `enableModelInference=true`
- **THEN** the pipeline SHALL run YOLO human detection with the configured detector model for that job even if the global setting is disabled

#### Scenario: Job disables model inference
- **WHEN** an analysis job carries `enableModelInference=false`
- **THEN** the pipeline SHALL use the empty detector behavior (no human boxes, detection stage skipped) and SHALL NOT run model inference

#### Scenario: Job enables pose inference
- **WHEN** an analysis job carries `enablePoseInference=true` and the RTMPose config/checkpoint are resolvable
- **THEN** the pipeline SHALL run RTMPose pose estimation for that job even if the global setting is disabled

#### Scenario: Job disables pose inference
- **WHEN** an analysis job carries `enablePoseInference=false`
- **THEN** the pipeline SHALL skip pose estimation and report the pose overlay as unavailable

#### Scenario: Toggle omitted falls back to global config
- **WHEN** an analysis job does not specify `enableModelInference` or `enablePoseInference`
- **THEN** the pipeline SHALL use the backend global configuration for those switches

#### Scenario: Toggles participate in job deduplication
- **WHEN** two job submissions share the same input but differ in `enableModelInference` or `enablePoseInference`
- **THEN** the configuration signature SHALL differ so the jobs are not deduplicated into one

### Requirement: Projection diagnostics expose per-sample details
The match-analysis pipeline SHALL emit a `projection_diagnostics.json` artifact that records, for every tracked player sample, the footpoint method used, raw and smoothed court coordinates, projection confidence, and the reason the sample was accepted or filtered.

#### Scenario: Sample accepted
- **WHEN** a player sample projects to a court position within `0 ≤ court_x ≤ 20` and `0 ≤ court_y ≤ 44`
- **THEN** the diagnostics entry SHALL record `projection_status="accepted"` together with the chosen footpoint method, raw court coordinates, smoothed court coordinates, and confidence

#### Scenario: Sample filtered out of range
- **WHEN** a player sample projects to a court position outside the allowed player bounds (`-4 ≤ court_x ≤ 24` and `-8 ≤ court_y ≤ 52`)
- **THEN** the diagnostics entry SHALL record `projection_status="filtered_out_of_range"` together with `filter_reason` describing the offending axis
- **AND** the sample SHALL NOT be written to the main player trajectory artifact with a `[0, 0]` fallback

#### Scenario: Player stands outside the court bounds (serve position)
- **WHEN** a player sample projects to a court position outside the standard court (`0..20` x `0..44`) but within the allowed player bounds (`-4..24` x `-8..52`)
- **THEN** the sample SHALL be recorded with `projection_status="out_of_bounds_allowed"`
- **AND** the sample SHALL be written to the main player trajectory artifact so the minimap can render the player outside the court lines (e.g. while serving from behind the baseline)
- **AND** the diagnostics entry SHALL note the `in_bounds=false` condition without treating it as an error

#### Scenario: Ball samples keep strict bounds
- **WHEN** a ball sample projects to a court position outside the standard court bounds
- **THEN** the ball trajectory SHALL keep its existing strict validation and SHALL NOT be relaxed by the player out-of-bounds allowance

#### Scenario: Footpoint falls back to bbox with explicit metadata
- **WHEN** the configured method is `hybrid` but pose keypoints are unavailable for a sample
- **THEN** the footpoint SHALL fall back to the bbox bottom-center
- **AND** the diagnostics entry SHALL record `footpoint_method="bbox_bottom_center"` together with `pose_unavailable=true` in metadata
- **AND** when the bbox bottom is near the frame edge, the entry SHALL also record `near_frame_bottom=true`

### Requirement: Calibration enforces baseline Y monotonicity
The manual court calibration page SHALL validate that the two near-baseline corner points have larger image Y than the two far-baseline corner points, and SHALL warn the user when the baseline order appears reversed.

#### Scenario: Calibration baselines are in expected order
- **WHEN** the user finishes selecting four court corners
- **THEN** the calibration page SHALL compute the average image Y of the two far-baseline corners and the two near-baseline corners
- **AND** if `near_baseline_avg_y - far_baseline_avg_y` is greater than a reasonable threshold, the page SHALL accept the calibration without further prompt

#### Scenario: Calibration baselines appear reversed
- **WHEN** the user finishes selecting four court corners
- **AND** the near-baseline average image Y is less than the far-baseline average image Y (or the difference is below the threshold)
- **THEN** the calibration page SHALL surface a confirmation prompt such as "近端与远端底线可能颠倒，请确认画面顶/底对应的场地底线"
- **AND** the user MAY proceed with the calibration after confirming

#### Scenario: Calibration Y values are missing or non-finite
- **WHEN** one or more of the four corner image Y values are not finite
- **THEN** the calibration page SHALL treat the order check as inconclusive and proceed without prompting

