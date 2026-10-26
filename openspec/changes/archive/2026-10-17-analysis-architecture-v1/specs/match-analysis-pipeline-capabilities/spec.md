## MODIFIED Requirements

### Requirement: 可配置激活比赛分析能力
系统 SHALL 通过配置和依赖检查激活新增比赛分析能力，而不是把历史 MVP 边界作为永久禁用规则。系统 SHALL 额外支持 `PICKLEBALL_BALL_ANALYSIS_STRICT` 配置（默认 `false`）控制球分析失败是否升级为 pipeline 失败。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

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

### Requirement: 能力状态可复盘
系统 SHALL 为新增分析能力提供可复盘的状态、原因和 counters，使用户和开发者能区分配置关闭、依赖缺失、无检测、部分可用和已完成。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

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

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

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

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

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

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

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

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

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

### Requirement: 任务签名包含 matchFormat
系统 SHALL 确保 matchFormat 参与分析任务签名计算，使同一视频以不同赛制提交时产生不同的任务签名和不同的分析结果。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: 同视频不同赛制产生不同签名
- **WHEN** 同一 `video_id` 以 `matchFormat="singles"` 创建任务
- **AND** 再以 `matchFormat="doubles"` 创建任务
- **THEN** 两个任务 SHALL 具有不同的输入签名
- **AND** SHALL 分别执行两次独立的分析

#### Scenario: 同视频同赛制复用结果
- **WHEN** 同一 `video_id` 以 `matchFormat="singles"` 提交两次
- **THEN** 第二次提交 SHALL 引用或返回原有分析结果（符合现有去重逻辑）

### Requirement: Task-level inference toggles drive pipeline execution
系统 SHALL 在执行 Pipeline 时遵守任务级推理开关，覆盖该任务的全局配置；未指定时保留全局默认。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: Job enables model inference
- **WHEN** 任务携带 enableModelInference=true
- **THEN** Pipeline SHALL 使用该任务配置的 detector 运行 YOLO 人检测，即使全局禁用

#### Scenario: Job disables model inference
- **WHEN** 任务携带 enableModelInference=false
- **THEN** Pipeline SHALL 使用空 detector 行为（无人框、检测阶段 skipped），且 SHALL NOT 运行模型推理

#### Scenario: Job enables pose inference
- **WHEN** 任务携带 enablePoseInference=true 且 RTMPose config/checkpoint 可解析
- **THEN** Pipeline SHALL 为该任务运行 RTMPose，即使全局禁用

#### Scenario: Job disables pose inference
- **WHEN** 任务携带 enablePoseInference=false
- **THEN** Pipeline SHALL 跳过姿态，并报告姿态叠加 unavailable

#### Scenario: Toggle omitted falls back to global config
- **WHEN** 任务未指定 enableModelInference 或 enablePoseInference
- **THEN** Pipeline SHALL 对这些开关使用后端全局配置

#### Scenario: Toggles participate in job deduplication
- **WHEN** 两次任务提交输入相同，但 enableModelInference 或 enablePoseInference 不同
- **THEN** 配置签名 SHALL 不同，两任务不能被合并去重

## ADDED Requirements

### Requirement: 模块能力由冻结计划独立激活
modular_v1 SHALL 按最小依赖计划激活能力，不继承 legacy 的固定球阶段、全量 matchFormat 签名或 PICKLEBALL_BALL_ANALYSIS_STRICT 成功策略。模块 SHALL 按消费字段冻结上下文，并按 analysis-result-publication 定义节点状态、质量和失败策略；事实优先于解释的要求继续适用。

#### Scenario: 原始球节点独立
- **WHEN** modular_v1 只请求 ball.detect
- **THEN** 系统 SHALL 只输出声明的原始观测和 nodeRuns
- **AND** SHALL 不强制提供 ball-trajectory/bounce-detection 阶段或其他产品输出

#### Scenario: 无关赛制变化
- **WHEN** 纯图像节点不消费 matchFormat 而赛制变化
- **THEN** 它的计算身份 SHALL 保持不变
- **AND** 消费赛制的未来语义节点 SHALL 使用新的上下文身份

#### Scenario: 推理参数冻结
- **WHEN** 模块请求选择可执行实现
- **THEN** 实现的有效推理配置 SHALL 在入队前冻结并参与身份
- **AND** legacy 开关 SHALL 不被当成默默关闭必需模块并返回空成功的理由
