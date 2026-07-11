# recording-session-control Specification

## Purpose
Define the recording session lifecycle control — starting, stopping, canceling FFmpeg-based camera recordings with state machine enforcement, error handling, video registration, optional Field Session association, and optional auto-analysis triggering.

## Requirements
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

系统 SHALL 通过 `CameraLeaseManager` 统一管理摄像机占用。Lease 在 Coordinator 事务中与 CaptureTake 一同创建，通过数据库保证互斥。

#### Scenario: 单摄录制占用双摄摄像头

- **WHEN** 摄像机已被双摄 Lease 占用（status=active）
- **AND** 单摄尝试获取 Lease
- **THEN** Coordinator 事务中的 INSERT OR IGNORE 发现冲突
- **AND** 返回 409 错误

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
系统 SHALL 在单摄和双摄实时录制启动时使用用户选择的 FPS，并将该 FPS 保存到录制 session。录制入口 MUST 默认选择 60fps，且实时录制请求的 FPS MUST NOT 超过 60fps。

#### Scenario: 单摄录制默认使用 60fps
- **WHEN** 用户进入单摄录制界面且尚未手动修改视频帧率
- **THEN** 前端提交的 `POST /api/recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 录制 session metadata SHALL 保存 `fps=60`

#### Scenario: 单摄录制不使用硬编码高 FPS
- **WHEN** 用户在单摄录制界面选择 60fps 并点击开始录制
- **THEN** 前端提交的 `POST /api/recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 请求 MUST NOT 使用硬编码 90fps 覆盖用户选择

#### Scenario: 双摄录制默认使用 60fps
- **WHEN** 用户进入双摄同步录制界面且尚未手动修改视频帧率
- **THEN** 前端提交的 `POST /api/sync-recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 双摄录制 session metadata SHALL 保存 `fps=60`

#### Scenario: 双摄录制不使用硬编码高 FPS
- **WHEN** 用户在双摄录制界面选择 60fps 并点击开始同步录制
- **THEN** 前端提交的同步录制启动请求 MUST 包含 `fps=60`
- **AND** 请求 MUST NOT 使用硬编码 90fps 或 30fps 覆盖用户选择

#### Scenario: 录制入口不提供超过 60fps 的选项
- **WHEN** 用户打开单摄或双摄实时录制的 FPS 选择控件
- **THEN** 控件 MUST 提供 60fps 选项
- **AND** 控件 MUST NOT 提供 90fps 或 120fps 录制选项

#### Scenario: 后端拒绝超过 60fps 的录制请求
- **WHEN** 客户端提交 `POST /api/recordings/start` 或 `POST /api/sync-recordings/start` 且 `fps > 60`
- **THEN** 系统 MUST 拒绝该请求
- **AND** 系统 MUST NOT 启动任何 FFmpeg 录制进程

#### Scenario: 录制 FPS 用于后续分析预填
- **WHEN** 录制 session 完成并注册为可分析视频
- **THEN** 系统 SHALL 在录制 session metadata 中保留启动时选择的 FPS
- **AND** 从该录制创建分析任务时 SHALL 使用该 FPS 作为默认源视频 FPS

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
