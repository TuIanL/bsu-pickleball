## ADDED Requirements

### Requirement: CameraLeaseManager 统一摄像机互斥

系统 MUST 提供 `CameraLeaseManager` 服务，统一管理摄像机录制占用，替换当前单摄/双摄进程内全局变量的交叉查询。Lease 以数据库行为权威真源。

#### Scenario: 单摄获取 Lease

- **WHEN** 单摄录制启动
- **THEN** 系统 MUST 调用 `acquire([camera_id], capture_take_id)` 获取 Lease
- **AND** 如果该 camera_id 已有 active Lease，MUST 返回冲突错误
- **AND** Lease.status MUST 为 `active`

#### Scenario: 双摄原子获取两路 Lease

- **WHEN** 双摄录制启动
- **THEN** 系统 MUST 在同一个数据库事务中调用 `acquire([cam_1_id, cam_2_id], capture_take_id)`
- **AND** 如果任一 camera_id 已有 active Lease，MUST 不获取任何 Lease（全有或全无）
- **AND** 两路 Lease 必须同时成功或同时失败

#### Scenario: 正常停止后释放 Lease

- **WHEN** 录制正常停止
- **THEN** 系统 MUST 调用 `release(capture_take_id)` 释放所有关联 Lease
- **AND** Lease.status MUST 更新为 `released`

#### Scenario: 取消录制后释放 Lease

- **WHEN** 录制被取消
- **THEN** 系统 MUST 调用 `release(capture_take_id)`
- **AND** 摄像机可被其他录制使用

#### Scenario: 启动失败时释放 Lease

- **WHEN** CaptureTakeProvisioner 或 FFmpeg 启动失败
- **THEN** 系统 MUST 释放已获取的 Lease
- **AND** MUST NOT 残留 active Lease

#### Scenario: 防止同一摄像机被重复占用

- **WHEN** 摄像机 A 已有 active Lease
- **AND** 另一个录制请求尝试获取摄像机 A 的 Lease
- **THEN** 系统 MUST 返回 409 冲突错误
- **AND** 错误信息 MUST 包含占用该摄像机的 capture_take_id

### Requirement: FFmpeg 进程登记与启动恢复

系统 MUST 在 FFmpeg 进程启动时将进程信息写入 `ffmpeg_registry`，并在应用启动时扫描和清理孤儿进程与陈旧 Lease。

#### Scenario: FFmpeg 启动时登记进程信息

- **WHEN** FFmpeg 子进程被启动
- **THEN** 系统 MUST 写入 `ffmpeg_registry` 记录，包含 pid、pgid、command_fingerprint、output_path、started_at
- **AND** 记录 MUST 关联 capture_take_id

#### Scenario: 应用启动时扫描陈旧 Lease

- **WHEN** 应用进程启动
- **THEN** 系统 MUST 扫描所有 status=active 的 CameraLease
- **AND** 对于超过心跳时限（默认 30 秒未更新 heartbeat_at）的 Lease，MUST 检查关联的 FFmpeg 进程是否仍存活
- **AND** 如果 FFmpeg 进程已不存在，MUST release Lease 并将关联录制标记为 failed/partial
- **AND** 如果 FFmpeg 进程仍存活，MUST 更新 heartbeat_at（接管孤儿会话）

#### Scenario: 进程 PID 复用安全校验

- **WHEN** 启动恢复检查 FFmpeg 进程
- **AND** 系统发现一个 PID 存活但与记录的 command_fingerprint 不匹配
- **THEN** 系统 MUST NOT 终止该进程
- **AND** 系统 MUST 将 Lease 标记为 orphaned 并 release
- **AND** 系统 MUST 记录 warning 日志

#### Scenario: 录制服务只运行在单进程

- **WHEN** API 应用启动
- **THEN** 系统 MUST 确保录制服务（SessionService/SyncRecordingService）在单个专用 worker 进程中初始化
- **AND** 多个 API Worker MUST NOT 各自初始化全局 Recorder

### Requirement: CameraLease 数据模型

系统 MUST 使用 `camera_leases` 数据库表存储摄像机租约，以 `camera_id` 为唯一键。

#### Scenario: Lease 表结构

- **WHEN** 系统创建 CameraLease 记录
- **THEN** 记录 MUST 包含 camera_id (unique)、capture_take_id、source_session_id、owner_instance_id、status ("active"|"released")、acquired_at、heartbeat_at、expires_at
- **AND** camera_id 上 MUST 有 UNIQUE 约束（一个摄像机同时只能有一个 active Lease）

#### Scenario: Heartbeat 定期更新

- **WHEN** 录制处于 recording 状态
- **THEN** 系统 SHALL 定期更新对应 Lease 的 heartbeat_at（建议间隔 10 秒）
- **AND** 更新 MUST 在后台异步执行，不阻塞录制主流程
