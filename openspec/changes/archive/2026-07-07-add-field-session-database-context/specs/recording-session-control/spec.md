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

### Requirement: RecordingSession 数据模型

系统 MUST 在 `RecordingSession` 中保存录制生命周期字段，并 MAY 保存其所属 Field Session。

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | string | 唯一标识，格式 `rec_{YYYYMMDD}_{HHmmss}` |
| camera_id | string | 关联的摄像头标识 |
| field_session_id | string\|null | 关联的 Field Session id；直接录制时为空 |
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

#### Scenario: 直接录制模型兼容
- **WHEN** 用户不提供 `field_session_id` 开始录制
- **THEN** RecordingSession SHALL 正常创建
- **AND** `field_session_id` SHALL 为空

#### Scenario: Field Session 录制模型关联
- **WHEN** 用户提供有效 `field_session_id` 开始录制
- **THEN** RecordingSession SHALL 保存该 `field_session_id`

## ADDED Requirements

### Requirement: 继承 Field Session 录制上下文

系统 MUST 在 Field Session 内开始录制时继承任务上下文。

#### Scenario: 继承球场名称和比赛形式
- **WHEN** 用户使用 `field_session_id` 开始录制且未提供 `court_name` 和 `match_format`
- **THEN** RecordingSession SHALL 使用 Field Session 的 `court_name`
- **AND** RecordingSession SHALL 使用 Field Session 的 `match_format`

#### Scenario: 请求字段覆盖继承值
- **WHEN** 用户使用 `field_session_id` 开始录制并显式提供 `court_name` 或 `match_format`
- **THEN** RecordingSession SHALL 使用请求中的显式值
- **AND** Field Session 的原始上下文 SHALL 保持不变

#### Scenario: 自动分析元数据使用录制上下文
- **WHEN** Field Session 内的录制停止并触发自动分析
- **THEN** 自动创建的分析任务 SHALL 使用 RecordingSession 上最终确定的 `court_name` 和 `match_format`
- **AND** 系统 SHALL 能通过 RecordingSession 追溯到 Field Session
