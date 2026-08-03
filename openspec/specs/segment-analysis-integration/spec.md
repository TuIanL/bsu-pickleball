# segment-analysis-integration Specification

## Purpose

定义分析批次、任务输入快照、时间裁剪、Pipeline 预热区间和视频 HTTP Range 支持的集成契约。

## Requirements

### Requirement: AnalysisBatch + AnalysisBatchItem

系统 MUST 使用关联表管理批量分析任务，保存创建时的输入快照。

#### Scenario: 创建 Batch

- **WHEN** `POST /api/capture-takes/{id}/analysis-batches` 并提交 `segment_ids`
- **THEN** 创建 AnalysisBatch 记录（status=creating）
- **AND** 为每个 segment 创建 AnalysisBatchItem
- **AND** BatchItem SHALL 保存 `snapshot_start_ms/end_ms`、`segment_version`、`video_id`
- **AND** Segment 的 `latest_analysis_job_id` 可选更新（非权威）

#### Scenario: 防止 ancestor/descendant 同时选中

- **WHEN** 提交的 segment_ids 包含父子关系
- **THEN** 拒绝，返回 400

#### Scenario: 同一 Batch 只能选同类型

- **WHEN** segment_ids 中包含不同 segment_type
- **THEN** 拒绝，返回 400

#### Scenario: 批量上限

- **WHEN** segment_ids 超过配置上限（默认 10）
- **THEN** 拒绝，返回 400 并告知上限值

#### Scenario: 查询 Batch 进度

- **WHEN** `GET /api/analysis-batches/{batch_id}`
- **THEN** 返回各 BatchItem 的 status 和 analysis_job_id

### Requirement: 任务输入快照

系统 MUST 在创建分析任务时保存 Segment 当前时间范围的快照。

#### Scenario: BatchItem 保存快照

- **WHEN** 创建 BatchItem
- **THEN** `snapshot_start_ms` SHALL = segment effective_start_ms
- **AND** `snapshot_end_ms` SHALL = segment effective_end_ms
- **AND** `segment_version` SHALL = segment edit_version

#### Scenario: 快照不随后续编辑改变

- **WHEN** 用户修改 Segment 边界
- **THEN** 已存在 BatchItem 的 snapshot 值 SHALL 不变

### Requirement: 分析任务时间裁剪

系统 MUST 在分析任务 Schema 中支持 clip 参数（JSON 字段，非数据库列）。

#### Scenario: 任务携带 clip 参数

- **WHEN** 通过 AnalysisBatch 创建 Job
- **THEN** Job JSON SHALL 包含 `clipStartMs` 和 `clipEndMs`
- **AND** `captureSegmentId` 和 `segmentVersion`

#### Scenario: 任务签名含 clip

- **WHEN** `analysis_signature()` 计算签名
- **THEN** 输入 SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** 同一视频不同 Rally 的任务 SHALL 产生不同签名

#### Scenario: 区间语义为半开

- **WHEN** 指定 clip 范围
- **THEN** 使用 `[start_ms, end_ms)` 半开区间
- **AND** 相邻片段不会在边界重复处理同一帧

### Requirement: Pipeline 预热区间

系统 MUST 在按片段分析时，为算法提供前序上下文帧。

#### Scenario: 预热区间

- **WHEN** Job 携带 clip 范围
- **THEN** 解码范围 SHALL = `[clip_start - pre_roll_ms, clip_end + post_roll_ms)`
- **AND** 默认 pre_roll_ms=1500, post_roll_ms=500

#### Scenario: 预热帧不纳入指标

- **WHEN** 计算分析指标
- **THEN** SHALL 只统计 clip 范围内的帧

#### Scenario: 预热帧纳入 debug artifact

- **WHEN** 生成 debug artifact
- **THEN** MAY 标记预热帧为 context

### Requirement: 视频 HTTP Range 支持

系统 MUST 确保视频流端点支持 HTTP Range 请求，以支持长视频快速 seek。

#### Scenario: Range 请求

- **WHEN** 播放器 seek 到视频中间位置
- **THEN** 服务端 SHALL 返回 206 Partial Content
- **AND** SHALL 包含 Accept-Ranges: bytes 头
- **AND** SHALL 在 Safari/Chrome 上正常工作
