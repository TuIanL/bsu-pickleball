# media-fragment-model Specification

## Purpose

定义媒体 Fragment 的持久化双索引、状态流转、时间偏移和跨重启时间线映射规则，确保分片生命周期和产物关联能够被实现与测试验证。

## Requirements

### Requirement: MediaFragment 持久化 + 双索引

系统 MUST 新增 `MediaFragment` ORM，记录每个 TS 分片的生命期元数据。使用 `fragment_index`（per-track）和 `rotation_index`（全组轮换）双索引。

#### Scenario: 创建 Fragment 时分配双索引

- **WHEN** TrackRecorder.start_fragment() 被调用
- **THEN** fragment_index MUST 为该 Track 内的递增序号
- **AND** rotation_index MUST 为 Coordinator 分配的当前轮次号
- **AND** UNIQUE(capture_track_id, fragment_index)

#### Scenario: Fragment 状态流转

- **WHEN** Fragment 被启动 → status MUST 为 starting
- **WHEN** FFmpeg 启动成功 → status MUST 更新为 recording
- **WHEN** FFmpeg 正常退出 → status MUST 更新为 completed
- **WHEN** FFmpeg 异常退出 → status MUST 更新为 failed
- **WHEN** 应用崩溃 → status MUST 更新为 interrupted
- **WHEN** 用户取消 → status MUST 更新为 discarded

#### Scenario: Fragment 记录时间偏移

- **WHEN** Fragment 启动
- **THEN** take_start_offset_ms MUST 为当前 take 已运行时间
- **WHEN** Fragment 结束
- **THEN** take_end_offset_ms MUST 为结束时 take 已运行时间
- **AND** media_duration_ms MUST 为实际媒体时长

### Requirement: TrackTimelineSpan 时间映射

系统 MUST 在 Finalizer 合并后生成 `TrackTimelineSpan[]`，记录每个 Fragment 的 CaptureTake 时间与输出 MP4 时间映射。

#### Scenario: 无重启时映射连续

- **WHEN** 录制无重启且 Fragment 1 覆盖 0ms-120000ms
- **THEN** take_start_ms=0, output_start_ms=0
- **AND** take_end_ms=120000, output_end_ms=120000
- **AND** gap_before_ms=0

#### Scenario: 重启后映射含 gap

- **WHEN** Fragment 1 覆盖 0ms-120000ms，3 秒中断，Fragment 2 覆盖 123000ms-240000ms
- **THEN** Fragment 2.take_start_ms=123000, output_start_ms=120000
- **AND** gap_before_ms=3000
- **AND** 最终 MP4 时长为 237000ms（非 240000ms）
