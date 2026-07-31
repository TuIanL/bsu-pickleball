## MODIFIED Requirements

### Requirement: 双摄 CaptureTrack 时间偏移

系统 MUST 为双摄 CaptureTrack 保存基于真实时间轴校正的相对偏移和同步质量，而不是仅使用进程启动时间或假设值。

#### Scenario: 双摄 CaptureTrack 使用 PTS 映射

- **WHEN** 创建或完成双摄 CaptureTake 的时间轴校正
- **THEN** 系统 SHALL 为每个摄像头保存相对于参考机位的 `offset_ms`
- **AND** SHALL 保存可选的 `drift_ppm` 或等价速率参数
- **AND** `offset_source` SHALL 为 `measured` 或 `corrected`
- **AND** `sync_quality` SHALL 为 `good`、`degraded` 或 `unknown`

#### Scenario: 无法测量可靠的跨路时间偏移

- **WHEN** 源 PTS 缺失、不单调、跨路不可比较或拟合残差超过阈值
- **THEN** 系统 SHALL 将 `sync_quality` 标记为 `degraded` 或 `unknown`
- **AND** SHALL 保留诊断原因
- **AND** SHALL NOT 将 `offset_source` 标记为 `measured`

#### Scenario: 事件映射到 CaptureTrack

- **WHEN** 需要定位事件在某个摄像头视频中的位置
- **THEN** 系统 SHALL 保持事件 `timestamp_ms` 相对 CaptureTake 起点不变
- **AND** SHALL 使用 CaptureTrack 的 offset/drift 映射得到摄像头本地时间和帧号
- **AND** SHALL 将映射误差暴露给训练导出或诊断清单
