## ADDED Requirements

### Requirement: CaptureFinalizer 合并片段并注册视频

系统 MUST 提供 `CaptureFinalizer`，由显式的双摄任务合并操作在 stop 后将 Track 的有效 TS 片段合并为 MP4，并注册 Video。Finalizer MUST 幂等，且不得被双摄停止请求自动调用。

#### Scenario: 正常合并流程

- **WHEN** Finalizer.finalize_track(capture_track_id) 被显式调用
- **THEN** MUST 按 take_start_offset_ms 排序有效 Fragment（completed + interrupted 但可读）
- **AND** MUST 跳过 failed/空文件/discarded 片段
- **AND** MUST 生成 ffmpeg concat manifest
- **AND** MUST 执行 concat 到临时 MP4
- **AND** MUST ffprobe 校验（returncode=0 + 文件 > 0 + 可读）
- **AND** MUST os.replace → 最终 MP4
- **AND** MUST 注册 Video
- **AND** MUST 更新 CaptureTrack.video_id
- **AND** MUST 生成 TrackTimelineMap

#### Scenario: 合并失败不产生伪 completed

- **WHEN** ffmpeg concat returncode != 0 或 ffprobe 失败
- **THEN** MUST NOT os.replace 到最终路径
- **AND** CaptureTake.status MUST NOT 更新为 completed
- **AND** analysis_available MUST 为 false
- **AND** MUST 返回并持久化错误原因

#### Scenario: 幂等重试

- **WHEN** 对已完成的 Track 再次调用 finalize_track
- **AND** 输出文件存在 + manifest hash 一致 + ffprobe 成功
- **THEN** MUST 直接复用已有输出（不重新合并）

#### Scenario: 任务级两路合并

- **WHEN** 用户触发一个双摄任务的合并操作
- **THEN** 系统 MUST 为两路 Track 依次调用 Finalizer
- **AND** 任一路正在处理时 MUST 拒绝同一任务的重复合并请求
- **AND** 只有两路都完成后才允许任务进入可播放、可分析状态

#### Scenario: cancel 不合并

- **WHEN** 录制被 cancel
- **THEN** MUST NOT 调用 Finalizer
- **AND** Fragment 标记 discarded

### Requirement: TrackTimelineMap 持久化

系统 MUST 在 Finalizer 完成后持久化 TrackTimelineMap，供播放器和分析任务查询。

#### Scenario: 通过 API 查询时间映射

- **WHEN** 客户端请求 Track 的时间映射
- **THEN** 系统 MUST 返回 TrackTimelineSpan[]
- **AND** 客户端 MUST 可通过映射完成 take_time_ms → track_time_ms 转换
