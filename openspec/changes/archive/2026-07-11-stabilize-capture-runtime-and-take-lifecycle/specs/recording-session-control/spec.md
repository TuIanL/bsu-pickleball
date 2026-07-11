## MODIFIED Requirements

### Requirement: 录制会话生命周期

录制会话 MUST 遵循严格的状态机。`field_session_id` 为必填参数。启动流程通过 `CaptureStartCoordinator` 在单事务中创建 Take + Tracks + Leases。

#### Scenario: 开始录制

- **WHEN** 用户提交 `POST /api/recordings/start`，提供 `camera_id`、`field_session_id`（必填）、`court_name`、`match_format`、`camera_angle`、`fps`、`resolution`、`auto_analyze_after_stop`
- **THEN** 系统调用 `CaptureStartCoordinator.prepare_start()` 在事务中创建 CaptureTake(status=starting) + CaptureTrack + CameraLease
- **AND** 事务成功后启动 FFmpeg 子进程
- **AND** FFmpeg 启动成功后 CaptureTake 和 RecordingSession 转为 recording
- **AND** FFmpeg 启动失败则 CaptureTake→failed + Session→failed + Leases released
- **AND** 在 ffmpeg_registry 中登记进程 PID/PGID
- **AND** 返回 `RecordingSession`，`status: "recording"`

#### Scenario: 停止录制

- **WHEN** 用户请求 `POST /api/recordings/{session_id}/stop`
- **THEN** 系统停止 FFmpeg
- **AND** Session.status 更新为 `completed`
- **AND** 显式调用 `finalize_capture_take(capture_take_id, "completed")`
- **AND** 通过 `CaptureStopResultBuilder.from_single_session()` 构建返回结果
- **AND** 返回 `CaptureStopResult`（不再是 `RecordingSession`）

### Requirement: 录制启动时创建 CaptureTake

系统 MUST 在录制启动时通过 `CaptureStartCoordinator` 在 FFmpeg 启动前创建 CaptureTake。

#### Scenario: 单摄前置创建 CaptureTake

- **WHEN** 单摄录制启动
- **THEN** CaptureTake 创建 MUST 在 FFmpeg 启动前完成
- **AND** 创建失败 MUST 不启动 FFmpeg 且释放 Lease
- **AND** RecordingSession.capture_take_id MUST 被填充

#### Scenario: 录制停止时统一 finalize

- **WHEN** 录制停止/失败/取消
- **THEN** 系统 MUST 调用 `finalize_capture_take(capture_take_id, terminal_status)`
- **AND** 已终态的 CaptureTake MUST 不在重复调用时被覆盖

### Requirement: 录制占用保护

系统 SHALL 通过 `CameraLeaseManager` 统一管理摄像机占用。Lease 在 Coordinator 事务中与 CaptureTake 一同创建，通过数据库保证互斥。

#### Scenario: 单摄录制占用双摄摄像头

- **WHEN** 摄像机已被双摄 Lease 占用（status=active）
- **AND** 单摄尝试获取 Lease
- **THEN** Coordinator 事务中的 INSERT OR IGNORE 发现冲突
- **AND** 返回 409 错误

## ADDED Requirements

### Requirement: 统一 CaptureStopResult 返回

系统 MUST 通过 `CaptureStopResultBuilder` 统一构建停止返回值。单摄和双摄使用相同 schema。

#### Scenario: 单摄停止返回 CaptureStopResult

- **WHEN** 单摄录制正常停止
- **THEN** CaptureStopResultBuilder.from_single_session() MUST 构建 CaptureStopResult
- **AND** tracks MUST 包含 1 个元素（slot="cam_1", analysis_role="default"）
- **AND** default_analysis_track_id MUST 指向 analysis_role="default" 的 track

#### Scenario: 双摄停止返回 CaptureStopResult

- **WHEN** 双摄录制正常停止
- **THEN** CaptureStopResultBuilder.from_sync_session() MUST 构建 CaptureStopResult
- **AND** tracks MUST 包含 2 个元素（slot="cam_1" 和 slot="cam_2"）
- **AND** default_analysis_track_id MUST 从 analysis_role="default" 解析
