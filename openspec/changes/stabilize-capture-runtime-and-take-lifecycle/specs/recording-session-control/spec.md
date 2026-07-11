## MODIFIED Requirements

### Requirement: 录制会话生命周期

录制会话 MUST 遵循严格的状态机：`recording → completed / failed / canceled`。终态（`completed`、`failed`、`canceled`）不可再转换。录制会话 MAY 关联一个 Field Session；未关联 Field Session 时 MUST 保持既有直接录制行为。

#### Scenario: 开始录制

- **WHEN** 用户提交 `POST /api/recordings/start`，提供 `camera_id`、`court_name`、`match_format`、`camera_angle`、`fps`、`resolution`、`auto_analyze_after_stop`
- **THEN** 系统验证 `camera_id` 已注册（否则返回 404）
- **AND** 系统调用 `CameraLeaseManager.acquire([camera_id])` 获取租约（否则返回 409）
- **AND** 系统调用 `CaptureTakeProvisioner.provision()` 在数据库事务中创建 CaptureTake + CaptureTrack（创建失败则释放 Lease 并返回 500）
- **AND** 启动 FFmpeg 子进程，参数包含：RTSP 输入地址、重连参数、输出路径 `data/recordings/{date}/{camera_id}/{session_id}.mp4`
- **AND** 创建 session metadata 并持久化到 `data/recordings/sessions/{session_id}.json`
- **AND** 启动 FFmpeg 进程后 MUST 在 `ffmpeg_registry` 中登记进程 PID
- **AND** 返回 `RecordingSession`，`status: "recording"`

#### Scenario: 停止录制

- **WHEN** 用户请求 `POST /api/recordings/{session_id}/stop`
- **THEN** 系统向 FFmpeg 进程发送 `SIGTERM`（或按 `q` 键优雅退出）
- **AND** 等待进程退出（最多 30 秒），超时则 `SIGKILL`
- **AND** 计算 `duration_sec` = 实际录制时长
- **AND** 调用 `VideoService.register_recording()` 将视频文件注册到视频管理体系中，获得 `video_id`
- **AND** 更新 session status 为 `completed`
- **AND** 如果 `auto_analyze_after_stop=true`，调用 `POST /api/analysis/jobs` 创建分析任务，记录返回的 `job_id` 到 `auto_analysis_job_id`
- **AND** MUST 显式调用 `finalize_capture_take(session_id, "completed")` 关闭 CaptureTake 和 open CaptureSegment
- **AND** MUST 调用 `CameraLeaseManager.release(capture_take_id)` 释放租约
- **AND** 返回 `CaptureStopResult`（不再是 `RecordingSession`）

#### Scenario: 取消录制

- **WHEN** 用户请求 `POST /api/recordings/{session_id}/cancel`
- **THEN** 系统向 FFmpeg 进程发送 `SIGTERM`
- **AND** 不注册视频文件到 VideoService
- **AND** 删除已写入的部分视频文件
- **AND** 更新 session status 为 `canceled`
- **AND** MUST 调用 `finalize_capture_take(session_id, "canceled")` 关闭 CaptureTake
- **AND** MUST 调用 `CameraLeaseManager.release(capture_take_id)` 释放租约

### Requirement: 录制启动时创建 CaptureTake

系统 MUST 在录制启动时通过 `CaptureTakeProvisioner` 在数据库事务中前置创建 CaptureTake 记录。创建失败则 MUST NOT 启动 FFmpeg。

#### Scenario: 单摄录制前置创建 CaptureTake

- **WHEN** 单摄录制启动且 CameraLease 已获取
- **THEN** 系统 MUST 调用 `CaptureTakeProvisioner.provision()` 创建 CaptureTake + CaptureTrack
- **AND** CaptureTake 创建 MUST 在 FFmpeg 启动之前完成
- **AND** 创建失败时 MUST 释放 CameraLease 并返回错误
- **AND** 创建成功时 `RecordingSession.capture_take_id` MUST 被正确填充

#### Scenario: 录制停止时统一 finalize

- **WHEN** 录制停止或失败或取消
- **THEN** 系统 MUST 调用 `finalize_capture_take(session_id, terminal_status)` 
- **AND** SHALL 关闭所有 open CaptureSegment
- **AND** 方法的幂等性 MUST 保证重复调用不报错

## ADDED Requirements

### Requirement: 统一 CaptureStopResult 返回

系统 MUST 在停止录制后返回统一的 `CaptureStopResult` 结构，单摄和双摄使用相同 schema。单摄只是 tracks.length === 1。

#### Scenario: 单摄停止返回 CaptureStopResult

- **WHEN** 单摄录制正常停止
- **THEN** 系统 MUST 返回 `CaptureStopResult`
- **AND** `tracks` MUST 包含 1 个 CaptureTrackStopResult（slot="cam_1"）
- **AND** `analysis_available` MUST 根据视频注册结果设置
- **AND** `default_analysis_track_id` MUST 指向唯一的 track

#### Scenario: 双摄停止返回 CaptureStopResult

- **WHEN** 双摄录制正常停止
- **THEN** 系统 MUST 返回 `CaptureStopResult`
- **AND** `tracks` MUST 包含 2 个 CaptureTrackStopResult（slot="cam_1" 和 slot="cam_2"）
- **AND** `default_analysis_track_id` MUST 指向 cam_1 对应的 track

#### Scenario: 部分轨道失败的 partial 状态

- **WHEN** 双摄录制停止时仅一路成功
- **THEN** 成功的 track.status MUST 为 `"completed"`
- **AND** 失败的 track.status MUST 为 `"failed"`
- **AND** `analysis_available` MUST 为 true（只要有一路可用视频）
- **AND** `warnings` MUST 包含失败轨道的信息
