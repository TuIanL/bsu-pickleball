# recording-session-control Specification

## Purpose
Define the recording session lifecycle control — starting, stopping, canceling FFmpeg-based camera recordings with state machine enforcement, error handling, video registration, and optional auto-analysis triggering.

## Requirements
### Requirement: 录制会话生命周期

录制会话 MUST 遵循严格的状态机：`recording → completed / failed / canceled`。终态（`completed`、`failed`、`canceled`）不可再转换。

#### Scenario: 开始录制
- **WHEN** 用户提交 `POST /api/recordings/start`，提供 `camera_id`、`court_name`、`match_format`、`camera_angle`、`fps`、`resolution`、`auto_analyze_after_stop`
- **THEN** 系统验证 `camera_id` 已注册（否则返回 404）
- **AND** 系统验证该摄像头没有正在进行的录制会话（否则返回 409）
- **AND** 启动 FFmpeg 子进程，参数包含：RTSP 输入地址、重连参数、输出路径 `data/recordings/{date}/{camera_id}/{session_id}.mp4`
- **AND** 创建 session metadata 并持久化到 `data/recordings/sessions/{session_id}.json`
- **AND** 返回 `RecordingSession`，`status: "recording"`

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

#### Scenario: 查询单个录制
- **WHEN** 用户请求 `GET /api/recordings/{session_id}`
- **THEN** 返回完整的 `RecordingSession` 详情
- **AND** 如果 session 不存在，返回 404

### Requirement: 录制异常处理

#### Scenario: FFmpeg 进程异常退出
- **WHEN** 录制过程中 FFmpeg 子进程非正常退出（流断开超过重连容忍时间等）
- **THEN** 系统捕获进程返回码，更新 session status 为 `failed`
- **AND** 在 `error_message` 中记录退出原因
- **AND** 已写入的部分视频文件保留（可能部分可用）
- **AND** 不触发自动分析

#### Scenario: 防止重复录制
- **WHEN** 某摄像头已有一个 `status=recording` 的 session
- **AND** 用户再次请求 `POST /api/recordings/start` 使用同一个 `camera_id`
- **THEN** 返回 409 错误，提示该摄像头正在录制中

### Requirement: RecordingSession 数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | string | 唯一标识，格式 `rec_{YYYYMMDD}_{HHmmss}` |
| camera_id | string | 关联的摄像头标识 |
| court_name | string | 球场名称 |
| match_format | string | 比赛类型：`doubles` / `singles` |
| camera_angle | string | 拍摄角度：`baseline_high` / `side` / `overhead` 等 |
| fps | int | 录制帧率 |
| resolution | string | 录制分辨率，如 `"1920x1080"` |
| auto_analyze_after_stop | bool | 停止后是否自动提交分析任务 |
| status | string | `recording` / `completed` / `failed` / `canceled` |
| started_at | datetime | 录制开始时间 |
| stopped_at | datetime\|null | 录制停止时间（录制中为 null） |
| duration_sec | float\|null | 实际录制时长（录制中为 null） |
| video_path | string\|null | 视频文件绝对路径（录制中为 null） |
| video_id | string\|null | VideoService 中的视频 ID（录制中为 null） |
| auto_analysis_job_id | string\|null | 自动创建的分析 Job ID（未触发为 null） |
| error_message | string\|null | 失败原因（仅 status=failed 时有值） |

### Requirement: FFmpeg 依赖检查

系统 MUST 在启动时检查 FFmpeg 是否可用。

#### Scenario: FFmpeg 可用
- **WHEN** 系统启动且 `ffmpeg -version` 返回正常
- **THEN** 录制功能正常可用

#### Scenario: FFmpeg 不可用
- **WHEN** 系统启动且 `ffmpeg` 命令不可执行
- **THEN** 录制相关 API 端点返回 503 错误
- **AND** 错误信息明确提示需要安装 FFmpeg
