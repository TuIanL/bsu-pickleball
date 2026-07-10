# recording-session-control Specification

## Purpose
Define the recording session lifecycle control — starting, stopping, canceling FFmpeg-based camera recordings with state machine enforcement, error handling, video registration, optional Field Session association, and optional auto-analysis triggering.

## Requirements
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

### Requirement: 录制异常处理

系统 MUST 在 FFmpeg 录制异常时更新会话状态并避免触发自动分析。

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

### Requirement: FFmpeg 依赖检查

系统 MUST 在启动时检查 FFmpeg 是否可用。

#### Scenario: FFmpeg 可用
- **WHEN** 系统启动且 `ffmpeg -version` 返回正常
- **THEN** 录制功能正常可用

#### Scenario: FFmpeg 不可用
- **WHEN** 系统启动且 `ffmpeg` 命令不可执行
- **THEN** 录制相关 API 端点返回 503 错误
- **AND** 错误信息明确提示需要安装 FFmpeg

### Requirement: 双摄同步录制控制入口

系统 SHALL 在录制控制层支持双摄同步录制入口，并保持单摄录制入口不变。

#### Scenario: 单摄采集任务继续使用单摄录制
- **WHEN** Field Session 的 `camera_setup` 为 `single` 或 `debug_single`
- **THEN** 系统继续调用现有单摄录制 API 开始和停止录制
- **AND** 系统返回现有 Recording Session 响应结构

#### Scenario: 双摄采集任务使用同步录制
- **WHEN** Field Session 的 `camera_setup` 为 `dual` 且用户点击开始同步录制
- **THEN** 系统调用双摄同步录制 API (`POST /api/sync-recordings/start`)
- **AND** 系统将返回的双摄同步录制会话作为当前活跃录制
- **AND** 系统使用双摄会话 ID 停止该录制

### Requirement: 录制占用保护

系统 SHALL 防止同一摄像头同时参与单摄录制和双摄同步录制。

#### Scenario: 单摄录制占用双摄摄像头
- **WHEN** 用户尝试开始双摄同步录制且任一摄像头正在单摄录制
- **THEN** 系统拒绝开始双摄同步录制
- **AND** 系统返回状态冲突错误（409）

#### Scenario: 双摄录制占用单摄摄像头
- **WHEN** 用户尝试开始单摄录制且该摄像头正在双摄同步录制中
- **THEN** 系统拒绝开始单摄录制
- **AND** 系统返回状态冲突错误（409）

### Requirement: 双摄录制停止与终态

系统 SHALL 支持停止、查询和恢复展示双摄同步录制的终态。

#### Scenario: 停止双摄同步录制
- **WHEN** 用户停止当前双摄同步录制
- **THEN** 系统调用 `POST /api/sync-recordings/{id}/stop`
- **AND** 系统终止两路 FFmpeg 进程并等待线程退出
- **AND** 系统将前端状态切换到 stopped
- **AND** 系统展示双摄录制完成信息（含 analysis_available 判断）

#### Scenario: 双摄录制异常终止
- **WHEN** 双摄同步录制服务将会话标记为 failed
- **THEN** 前端查询状态时展示失败状态和错误信息
- **AND** 系统释放两个摄像头的录制占用

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
