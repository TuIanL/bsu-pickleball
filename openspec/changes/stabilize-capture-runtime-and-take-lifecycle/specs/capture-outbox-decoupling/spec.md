## ADDED Requirements

### Requirement: 媒体停止优先于 Outbox 同步

系统 MUST 将媒体录制停止与 Outbox 事件同步分离为两个独立生命周期。用户点击停止录像后，媒体停止操作 MUST 立即执行，不等待 Outbox drain 完成。

#### Scenario: 停止时媒体优先停止

- **WHEN** 用户点击「停止录制」按钮
- **THEN** 系统 MUST 立即请求停止媒体录制（stop API），不等待 Outbox drain
- **AND** 前端 MUST 同时进行 best-effort Outbox drain（带 3 秒 deadline）
- **AND** 编码按钮 MUST 被冻结（禁止新事件入 outbox）

#### Scenario: Outbox 未完成不阻塞进入 finalizing

- **WHEN** 媒体停止完成但 Outbox drain 仍有 pending 事件
- **THEN** capturePhase MUST 进入 `finalizing`，然后 `completed`
- **AND** outboxHealth MUST 显示 `pending`（独立于 capturePhase）
- **AND** 页面 MUST 显示「录像已安全保存，仍有 N 条现场标记待同步」

#### Scenario: Outbox 网络断开时停止正常完成

- **WHEN** 录制过程中网络断开
- **AND** 用户点击停止
- **THEN** 系统 MUST 成功停止 FFmpeg 并进入 completed
- **AND** 未同步事件 MUST 保留在 localStorage
- **AND** 页面 MUST 不卡在停止中状态

### Requirement: 停止后迟到事件补传

系统 MUST 支持在 CaptureTake 完成后一段宽限期内接收迟到 CodingAction，允许事后补传未同步的现场事件。

#### Scenario: 宽限期内补传成功

- **WHEN** CaptureTake 处于 completed 状态且距离 ended_at 不超过宽限期（默认 5 分钟）
- **AND** 客户端提交 CodingAction（timeline 事件）
- **THEN** 系统 MUST 接受并处理该事件
- **AND** 系统 MUST 检查 client_action_id 是否已存在（幂等）

#### Scenario: 宽限期外拒绝补传

- **WHEN** CaptureTake 处于 completed 状态且距离 ended_at 超过宽限期
- **AND** 客户端提交 CodingAction
- **THEN** 系统 MUST 拒绝该事件
- **AND** 返回宽限期已过的错误信息

#### Scenario: 补传事件时间戳校验

- **WHEN** 客户端提交迟到 CodingAction
- **THEN** 系统 MUST 验证 0 <= timestamp_ms <= capture_take.duration_ms
- **AND** 超出范围的事件 MUST 被拒绝

#### Scenario: 录制中正常事件不经历补传路径

- **WHEN** CaptureTake 仍处于 recording 状态
- **AND** 客户端提交 CodingAction
- **THEN** 系统 MUST 按正常实时路径处理（不经过补传宽限检查）

### Requirement: Outbox 事件使用 CaptureTake 时间轴

所有 Outbox 事件的 timestamp 字段 MUST 使用 CaptureTake 时间轴（take_time_ms），不依赖 FFmpeg fragment 局部时间。

#### Scenario: 双摄分片重启后事件时间一致

- **WHEN** 双摄录制过程中发生分片重启（segment_index 递增）
- **AND** 用户在重启前后分别打点
- **THEN** 所有事件的 timestamp_ms MUST 相对 CaptureTake started_at 单调递增
- **AND** 事件的相对时间 MUST 不因分片重启而跳变

#### Scenario: 播放时从 take_time_ms 映射到 track_local_time_ms

- **WHEN** 用户播放具体轨道（如 cam_1.mp4）
- **THEN** 播放器 MUST 通过 CaptureTrackFragment 映射将 take_time_ms 转换为 track_local_time_ms
- **AND** 播放 seek 到某个事件位置时 MUST 使用映射后的局部时间
