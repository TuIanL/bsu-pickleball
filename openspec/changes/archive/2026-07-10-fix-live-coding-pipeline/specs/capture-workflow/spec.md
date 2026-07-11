## MODIFIED Requirements

### Requirement: 录制中事件标记

#### Scenario: 录制中展示时间线

- WHEN 录制状态为 recording
- THEN 系统在事件标记下方展示时间线
- AND 时间线实时展示已标记的事件，包含时间戳和事件标签
- AND 新事件实时追加到时间线末尾
- AND 时间线 SHALL 与视频预览底部对齐，位于预览画面正下方
- AND 时间线 SHALL 使用三轨道色条（盘、局、分）展示 CaptureSegment
- AND 色条 SHALL 在录制中随 elapsedMs 实时增长
- AND 时间线不 SHALL 使用倒三角事件标记
