## ADDED Requirements

### Requirement: CaptureTakeProvisioner 统一创建入口

系统 MUST 提供 `CaptureTakeProvisioner` 服务作为单摄和双摄录制启动前的统一 CaptureTake 创建入口。创建失败时 MUST 拒绝启动 FFmpeg 录制进程。

#### Scenario: 单摄录制前创建 CaptureTake

- **WHEN** 单摄录制启动被请求且 CameraLease 已获取
- **THEN** 系统 MUST 调用 `CaptureTakeProvisioner.provision(capture_mode="single", source_session_type="recording", source_session_id, tracks=[{slot: "cam_1", ...}])`
- **AND** 必须在数据库事务中原子创建 1 个 CaptureTake + 1 个 CaptureTrack
- **AND** 创建成功后 MUST 将 CaptureTake 标记为 `recording`
- **AND** 创建失败时 MUST 拒绝启动 FFmpeg

#### Scenario: 双摄录制前创建 CaptureTake

- **WHEN** 双摄录制启动被请求且两路 CameraLease 均已获取
- **THEN** 系统 MUST 调用 `CaptureTakeProvisioner.provision(capture_mode="dual", source_session_type="sync_recording", source_session_id, tracks=[{slot: "cam_1", ...}, {slot: "cam_2", ...}])`
- **AND** 必须在数据库事务中原子创建 1 个 CaptureTake + 2 个 CaptureTrack
- **AND** 双摄 SyncRecordingSession.capture_take_id MUST 被正确填充
- **AND** 前端 Live Coding 初始化 MUST 可正常读取 capture_take_id

#### Scenario: Provision 失败时释放 Lease

- **WHEN** CaptureTakeProvisioner 创建失败（如数据库不可用）
- **THEN** 系统 MUST 释放已获取的 CameraLease
- **AND** 系统 MUST NOT 启动任何 FFmpeg 进程
- **AND** 系统 MUST 返回错误给调用方

### Requirement: unified finalize 统一终态处理

系统 MUST 提供 `finalize_capture_take(source_session_id, terminal_status, ended_at, duration_ms)` 方法，由正常停止、取消和异常退出共同调用。方法 MUST 幂等：已 finalize 的 CaptureTake 再次调用不报错。

#### Scenario: 正常停止 finalize

- **WHEN** 录制正常停止（单摄 stop_session 或双摄 stop_session）
- **THEN** 系统 MUST 显式调用 `finalize_capture_take(session_id, "completed", ended_at, duration_ms)`
- **AND** CaptureTake.status MUST 更新为 `completed`
- **AND** 所有 open CaptureSegment MUST 被关闭（end_ms 被设置）
- **AND** RecordingSession.status 已为 `completed` 时，finalize MUST 依然成功执行

#### Scenario: 取消录制 finalize

- **WHEN** 录制被取消（单摄 cancel_session 或双摄 cancel_session）
- **THEN** 系统 MUST 调用 `finalize_capture_take(session_id, "canceled", ended_at, duration_ms)`
- **AND** CaptureTake.status MUST 更新为 `canceled`

#### Scenario: 异常退出 finalize

- **WHEN** FFmpeg 异常退出触发 `_on_recorder_exit()`
- **THEN** 系统 MUST 调用 `finalize_capture_take(session_id, "failed", ended_at, duration_ms)`
- **AND** CaptureTake.status MUST 更新为 `failed`

#### Scenario: 重复 finalize 幂等

- **WHEN** `finalize_capture_take()` 被对同一个 session 多次调用（如 stop_session 显式调用后 `_on_recorder_exit()` 再次调用）
- **THEN** 第二次调用 MUST NOT 报错
- **AND** CaptureTake 终态 MUST NOT 被改变
- **AND** 已关闭的 CaptureSegment MUST NOT 被重复修改

#### Scenario: stop_session 竞态窗口消除

- **WHEN** stop_session 先将 Session 改为 `completed`，然后 `_on_recorder_exit()` 看到 `status != "recording"` 后 return
- **THEN** stop_session 中的显式 finalize 调用 MUST 确保 CaptureTake 被正确关闭
- **AND** 无论线程调度顺序如何，CaptureTake MUST 被 finalize

### Requirement: CaptureTake 不存在时的录制保护

系统 MUST 在检测到活跃录制缺少 CaptureTake 时将现场打点和 Live Coding 功能标记为不可用，但 MUST NOT 中断媒体录制。

#### Scenario: 启动恢复时发现孤儿 Session

- **WHEN** 应用重启后发现一个 Completed 状态的 RecordingSession 但 CaptureTake 不存在
- **THEN** 系统 SHALL 通过补偿流程创建 CaptureTake（status 为 completed，duration 从 session metadata 推断）
- **AND** 系统 SHALL 记录 warning 日志
