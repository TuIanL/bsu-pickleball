# match-analysis-pipeline-capabilities Delta Spec

## ADDED Requirements

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

## MODIFIED Requirements

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
