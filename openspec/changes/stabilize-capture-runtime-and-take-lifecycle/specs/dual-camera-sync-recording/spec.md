## MODIFIED Requirements

### Requirement: 双摄同步录制会话

系统 SHALL 提供双摄同步录制会话，用一次开始和一次停止操作同时管理两个已注册摄像头。两个摄像头均为平等机位，slot key 为 `cam_1` 和 `cam_2`，默认机位角度均为 `baseline_high`。

#### Scenario: 开始双摄同步录制

- **WHEN** 用户为 `cam_1` 和 `cam_2` 两个机位槽位选择了不同的已注册摄像头并点击开始同步录制
- **THEN** 系统 MUST 调用 `CameraLeaseManager.acquire([cam_1_id, cam_2_id])` 在同一事务中原子获取两路租约（否则返回 409）
- **AND** 系统 MUST 调用 `CaptureTakeProvisioner.provision(capture_mode="dual", tracks=[{slot:"cam_1"}, {slot:"cam_2"}])` 创建 CaptureTake + 2 CaptureTrack
- **AND** 系统为两路摄像头同时启动 FFmpeg 录制进程
- **AND** 系统 MUST 在 `ffmpeg_registry` 中为每路 FFmpeg 登记进程 PID
- **AND** SyncRecordingSession.capture_take_id MUST 被正确填充

#### Scenario: 用户停止录制

- **WHEN** 用户停止正在进行的双摄同步录制会话
- **THEN** 系统终止两路 FFmpeg 进程
- **AND** 系统等待录制线程退出
- **AND** 系统将会话状态更新为 completed
- **AND** 系统记录停止时间、总时长和已保存分段
- **AND** 系统 MUST 调用 `finalize_capture_take(session_id, "completed")` 关闭 CaptureTake 和 open CaptureSegment
- **AND** 系统 MUST 调用 `CameraLeaseManager.release(capture_take_id)` 释放两路租约

### Requirement: 默认分析视频登记

系统 SHALL 在双摄录制完成后使 `cam_1` 视频能够进入现有单视频分析流程（作为默认分析视频），并保留 `cam_2` 素材引用。`default_analysis_track_id` 由 CaptureTake 显式记录，不硬编码 cam_1。

#### Scenario: 双摄录制完成后登记默认分析视频

- **WHEN** 双摄同步录制会话完成且 `cam_1` 存在可用视频产物
- **THEN** 系统将 `cam_1` 的合并视频登记为 `default_analysis_video_id`
- **AND** 系统通过 `default_analysis_track_id` 解析分析入口（不硬编码 cam_1）
- **AND** 系统保留 `cam_2` 的分段文件路径作为关联素材

#### Scenario: 用户可指定非 cam_1 为分析入口（未来）

- **WHEN** 未来版本中用户选择 cam_2 作为分析视频
- **THEN** `default_analysis_track_id` 应指向 cam_2 的 track
- **AND** 分析流程从 `default_analysis_track_id` 解析 video_id，不修改已有逻辑

### Requirement: 双摄录制创建 CaptureTake

系统 MUST 在双摄录制启动时通过 `CaptureTakeProvisioner` 前置创建 CaptureTake 记录。创建失败 MUST NOT 启动 FFmpeg。

#### Scenario: 双摄录制前置创建 CaptureTake

- **WHEN** 双摄同步录制启动且两路 Lease 已获取
- **THEN** 系统 MUST 调用 `CaptureTakeProvisioner.provision()` 创建 CaptureTake + 2 CaptureTrack
- **AND** 创建必须在 FFmpeg 启动之前完成
- **AND** 创建失败时 MUST 释放两路 CameraLease 并返回错误
- **AND** SyncRecordingSession.capture_take_id MUST 被正确填充
- **AND** 前端 Live Coding MUST 可正常初始化

## ADDED Requirements

### Requirement: 双摄停止返回统一 CaptureStopResult

系统 MUST 在双摄停止后返回 `CaptureStopResult`，与单摄使用相同 schema。两路轨道信息通过 tracks 数组表达。

#### Scenario: 双摄停止返回 CaptureStopResult

- **WHEN** 用户停止双摄同步录制
- **THEN** 系统 MUST 返回 `CaptureStopResult`（不再是 `SyncStopResponse`）
- **AND** `tracks` MUST 包含两个元素（cam_1 和 cam_2）
- **AND** 每个 track 包含 fragment_count 和 restart_count
- **AND** `default_analysis_track_id` MUST 指向 cam_1 对应的 track

#### Scenario: 双摄部分成功返回 partial

- **WHEN** 双摄录制停止时 cam_2 的视频合并失败
- **THEN** cam_1 的 track.status MUST 为 `"completed"`
- **AND** cam_2 的 track.status MUST 为 `"failed"`
- **AND** `analysis_available` MUST 为 true（cam_1 可用）
- **AND** `warnings` MUST 包含 cam_2 的失败信息
