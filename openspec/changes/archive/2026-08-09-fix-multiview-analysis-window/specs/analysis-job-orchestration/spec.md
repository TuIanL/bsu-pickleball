## MODIFIED Requirements

### Requirement: 分析任务支持时间裁剪与预热区间

系统 MUST 在 AnalysisJob JSON Schema 中支持 clip 参数（非数据库列），并在所有实际执行和派生可视化阶段使用统一的窗口语义。Pipeline 执行时使用预热区间，但正式指标、融合统计和用户可见叠加视频 MUST 只对应请求窗口。

#### Scenario: Job Schema 包含 clip 字段

- **WHEN** 创建含裁剪参数的分析任务
- **THEN** `AnalysisJobCreate` SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** `AnalysisJobSummary` SHALL 包含对应字段

#### Scenario: 任务签名包含 clip 信息

- **WHEN** `analysis_signature()` 计算
- **THEN** 输入 payload SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** 同一视频不同 Rally SHALL 产生不同签名

#### Scenario: Pipeline 预热区间

- **WHEN** 任务携带 clip 范围
- **THEN** 解码范围 SHALL = `[clip_start - pre_roll_ms, clip_end + post_roll_ms)`
- **AND** 默认 `pre_roll_ms=1500`、`post_roll_ms=500`
- **AND** 半开区间 `[start, end)`，相邻片段不会在边界重复处理
- **AND** 预热帧不纳入正式分析指标

#### Scenario: Pipeline 裁剪结果记录

- **WHEN** Pipeline 按 clip 范围执行
- **THEN** 结果 SHALL 记录 `requested_clip.start_ms/end_ms` 和 `decoded_range.start_ms/end_ms`
- **AND** SHALL 记录实际 `processed_frame_count` 与 `source_frame_count`

#### Scenario: 派生叠加视频遵守窗口

- **WHEN** 任务启用分析叠加视频且携带 clip 范围
- **THEN** 叠加视频 writer SHALL 只读取并写出请求窗口对应的帧
- **AND** 结果 SHALL 记录 `output_time_origin_ms`，使输出 artifact 能映射回源视频时间轴

#### Scenario: 无 clip 保持全场行为

- **WHEN** 任务未携带完整的 `clipStartMs/clipEndMs`
- **THEN** Pipeline、叠加视频和统计 SHALL 按完整源视频执行
- **AND** 结果 SHALL 将窗口字段标记为未启用或省略

