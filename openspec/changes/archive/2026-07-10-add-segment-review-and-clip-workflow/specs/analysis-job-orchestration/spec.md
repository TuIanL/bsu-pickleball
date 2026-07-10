## ADDED Requirements

### Requirement: 分析任务 Schema 增加 clip 字段

系统 MUST 在 AnalysisJob 的 JSON Schema 中支持视频时间裁剪参数（**非数据库列**，AnalysisJob 为 JSON 持久化）。

#### Scenario: Job Schema 包含 clip 字段

- **WHEN** 创建含裁剪参数的分析任务
- **THEN** `AnalysisJobCreate` SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** `AnalysisJobSummary` SHALL 包含对应字段

#### Scenario: 任务签名包含 clip 信息

- **WHEN** `analysis_signature()` 计算
- **THEN** 输入 payload SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** 同一视频不同 Rally SHALL 产生不同签名

#### Scenario: Worker 传递 clip 到 Pipeline

- **WHEN** AnalysisWorker 执行含 clip 参数的任务
- **THEN** run_kwargs SHALL 包含 `clip_start_ms`、`clip_end_ms`
- **AND** Pipeline SHALL 使用预热区间解码

#### Scenario: Pipeline 裁剪结果记录

- **WHEN** Pipeline 按 clip 范围执行
- **THEN** 结果 SHALL 记录 `requested_clip.start_ms/end_ms` 和 `decoded_range.start_ms/end_ms`
- **AND** decoded_range = `[clip_start - pre_roll, clip_end + post_roll)`

### Requirement: 分析预热区间配置

系统 MUST 支持配置算法预热缓冲区。

#### Scenario: 默认预热值

- **WHEN** 未显式指定预热值
- **THEN** pre_roll_ms SHALL 默认为 1500
- **AND** post_roll_ms SHALL 默认为 500

#### Scenario: 预热裁剪到视频边界

- **WHEN** clip_start - pre_roll < 0
- **THEN** decode_start SHALL = 0
- **AND** decode_end SHALL = min(video_duration, clip_end + post_roll)
