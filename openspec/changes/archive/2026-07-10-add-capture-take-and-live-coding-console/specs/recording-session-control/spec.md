## MODIFIED Requirements

### Requirement: 录制会话生命周期

录制会话 MUST 遵循严格的状态机：`recording → completed / failed / canceled`。终态（`completed`、`failed`、`canceled`）不可再转换。录制会话 MAY 关联一个 Field Session；未关联 Field Session 时 MUST 保持既有直接录制行为。

#### Scenario: 开始录制

- **WHEN** 用户提交 `POST /api/recordings/start`，提供 `camera_id`、`court_name`、`match_format`、`camera_angle`、`fps`、`resolution`、`auto_analyze_after_stop`
- **THEN** 系统验证 `camera_id` 已注册（否则返回 404）
- **AND** 系统验证该摄像头没有正在进行的录制会话（否则返回 409）
- **AND** 启动 FFmpeg 子进程，参数包含：RTSP 输入地址、重连参数、输出路径 `data/recordings/{date}/{camera_id}/{session_id}.mp4`
- **AND** 创建 session metadata 并持久化到 `data/recordings/sessions/{session_id}.json`
- **AND** 返回 `RecordingSession`，`status: "recording"`

#### Scenario: 在 Field Session 中开始录制

- **WHEN** 用户提交 `POST /api/recordings/start` 并提供有效的 `field_session_id`
- **THEN** 系统 SHALL 创建关联该 Field Session 的 RecordingSession
- **AND** RecordingSession metadata SHALL 持久化 `field_session_id`
- **AND** 响应 SHALL 包含 `field_session_id`

#### Scenario: 拒绝不存在的 Field Session

- **WHEN** 用户提交 `POST /api/recordings/start` 并提供不存在的 `field_session_id`
- **THEN** 系统 SHALL 返回 404
- **AND** 系统 SHALL 不启动 FFmpeg 录制进程
- **AND** 系统 SHALL 不创建 RecordingSession metadata

#### Scenario: 停止录制

- **WHEN** 用户请求 `POST /api/recordings/{session_id}/stop`
- **THEN** 系统向 FFmpeg 进程发送 `SIGTERM`（或按 `q` 键优雅退出）
- **AND** 等待进程退出（最多 30 秒），超时则 `SIGKILL`
- **AND** 计算 `duration_sec` = 实际录制时长
- **AND** 调用 `VideoService.register_recording()` 将视频文件注册到视频管理体系中，获得 `video_id`
- **AND** 更新 session status 为 `completed`
- **AND** 如果 `auto_analyze_after_stop=true`，调用 `POST /api/analysis/jobs` 创建分析任务，记录返回的 `job_id` 到 `auto_analysis_job_id`
- **AND** 返回更新后的 `RecordingSession`

#### Scenario: 取消录制

- **WHEN** 用户请求 `POST /api/recordings/{session_id}/cancel`
- **THEN** 系统向 FFmpeg 进程发送 `SIGTERM`
- **AND** 不注册视频文件到 VideoService
- **AND** 删除已写入的部分视频文件
- **AND** 更新 session status 为 `canceled`
- **AND** 返回更新后的 `RecordingSession`

#### Scenario: 查询录制列表

- **WHEN** 用户请求 `GET /api/recordings`
- **THEN** 返回所有录制会话列表，按 `started_at` 降序排列
- **AND** 支持可选查询参数 `?camera_id=xxx` 筛选特定摄像头的录制
- **AND** 支持可选查询参数 `?status=recording` 筛选进行中的录制
- **AND** 支持可选查询参数 `?field_session_id=xxx` 筛选特定 Field Session 下的录制

#### Scenario: 查询单个录制

- **WHEN** 用户请求 `GET /api/recordings/{session_id}`
- **THEN** 返回完整的 `RecordingSession` 详情
- **AND** 如果 session 不存在，返回 404

### Requirement: 录制启动使用用户选择 FPS

系统 SHALL 在单摄和双摄实时录制启动时使用用户选择的 FPS，并将该 FPS 保存到录制 session。

#### Scenario: 单摄录制不使用硬编码 FPS

- **WHEN** 用户在单摄录制界面选择 60fps 并点击开始录制
- **THEN** 前端提交的 `POST /api/recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 请求 MUST NOT 使用硬编码 90fps 覆盖用户选择

#### Scenario: 双摄录制不使用硬编码 FPS

- **WHEN** 用户在双摄录制界面选择 90fps 并点击开始同步录制
- **THEN** 前端提交的同步录制启动请求 MUST 包含 `fps=90`
- **AND** 请求 MUST NOT 使用硬编码 30fps 覆盖用户选择

#### Scenario: 录制 FPS 用于后续分析预填

- **WHEN** 录制 session 完成并注册为可分析视频
- **THEN** 系统 SHALL 在录制 session metadata 中保留启动时选择的 FPS
- **AND** 从该录制创建分析任务时 SHALL 使用该 FPS 作为默认源视频 FPS

## ADDED Requirements

### Requirement: 录制启动时创建 CaptureTake

系统 MUST 在录制启动时自动创建 CaptureTake 记录。

#### Scenario: 单摄录制创建 CaptureTake

- **WHEN** 单摄录制启动成功
- **THEN** 系统 SHALL 创建 CaptureTake 记录
- **AND** `capture_mode` SHALL 设置为 `single`
- **AND** `source_session_type` SHALL 设置为 `recording`
- **AND** `source_session_id` SHALL 设置为 RecordingSession ID
- **AND** `status` SHALL 设置为 `recording`
- **AND** 系统 SHALL 创建一个 CaptureTrack，`role` 为 `primary`，`offset_ms` 为 0

#### Scenario: 录制停止时关闭 CaptureTake（补偿流程）

- **WHEN** 录制停止或失败或取消
- **THEN** 系统 SHALL 先完成底层录制 JSON 更新
- **AND** 系统 SHALL 更新对应 CaptureTake 的 `status`、`ended_at` 和 `duration_ms`
- **AND** 系统 SHALL 关闭所有 open 区间（状态为 `inferred`、`close_reason` 为 `recording_stopped`）
- **AND** 如果 CaptureTake/Segment 更新失败，系统 SHALL 记录 reconciliation_pending
- **AND** 下次查询时 SHALL 执行修复

#### Scenario: 跨存储非原子性

- **WHEN** 录制 JSON 更新成功但 SQLite 更新失败
- **THEN** 系统 SHALL 不声称跨存储原子性
- **AND** 系统 SHALL 依赖补偿流程修复不一致
- **AND** coding-actions 内部（SQLite 层面）SHALL 保持原子性

#### Scenario: CaptureTake ID 返回给前端

- **WHEN** 录制启动成功并创建 CaptureTake
- **THEN** 响应 SHALL 包含 `capture_take_id`
- **AND** 前端 SHALL 使用该 ID 进行后续的事件打点

### Requirement: 录制停止时关闭未结束区间

系统 MUST 在录制停止时自动关闭所有进行中的区间。

#### Scenario: 录制停止关闭 open 区间

- **WHEN** CaptureTake 状态变为 `completed`、`failed` 或 `canceled`
- **THEN** 系统 SHALL 查找所有 `status` 为 `open` 的 CaptureSegment
- **AND** 系统 SHALL 将这些区间的 `status` 设置为 `inferred`
- **AND** 系统 SHALL 设置 `close_reason` 为 `recording_stopped`
- **AND** 系统 SHALL 设置 `end_ms` 为 CaptureTake 的 `ended_at` 对应的时间戳
