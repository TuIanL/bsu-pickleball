## ADDED Requirements

### Requirement: CameraLeaseManager 统一摄像机互斥

系统 MUST 提供 `CameraLeaseManager` 服务，通过 SQLite 条件 INSERT 在事务中原子获取 Lease。Lease 返回 list[CameraLease]（非单个）。

#### Scenario: 单摄获取 Lease

- **WHEN** 单摄录制启动进入 Coordinator 事务
- **THEN** 系统 MUST 使用 `INSERT OR IGNORE ... WHERE NOT EXISTS (SELECT 1 FROM camera_leases WHERE camera_id=? AND status='active')` 原子检查
- **AND** rowcount=0 时 MUST 抛出 LeaseConflictError
- **AND** acquire() 返回 list[CameraLease]（单摄返回 1 个）

#### Scenario: 双摄原子获取两路 Lease

- **WHEN** 双摄录制启动进入 Coordinator 事务
- **THEN** 系统 MUST 在同一个数据库事务中对 cam_1 和 cam_2 执行条件 INSERT
- **AND** 任一台冲突 MUST 触发事务回滚（两台都不获取）
- **AND** acquire() 返回 list[CameraLease]（双摄返回 2 个）

### Requirement: Heartbeat + ffmpeg_registry 完整维护链

系统 MUST 在 Recorder/SyncRecorder 主循环中每 10 秒调用 heartbeat()，并在 FFmpeg 启动/停止/分片重启时维护 ffmpeg_registry。

#### Scenario: Recorder 主循环中续租

- **WHEN** 录制处于 recording 状态
- **THEN** Recorder 主循环 MUST 每 10 秒调用 `lease_manager.heartbeat(capture_take_id)`
- **AND** heartbeat_at MUST 被更新为当前时间

#### Scenario: FFmpeg 启动时登记进程

- **WHEN** FFmpeg 子进程被 Popen 启动
- **THEN** 系统 MUST 使用 `start_new_session=True` 创建进程组
- **AND** 系统 MUST 在 ffmpeg_registry 中 INSERT (pid, pgid, command_fingerprint, output_path, started_at)

#### Scenario: FFmpeg 正常退出时更新 ended_at

- **WHEN** FFmpeg 进程正常退出
- **THEN** 系统 MUST 在 ffmpeg_registry 中 UPDATE ended_at

#### Scenario: 双摄分片重启时登记新进程

- **WHEN** 双摄同步录制发生分片重启
- **THEN** 系统 MUST 在 ffmpeg_registry 中 INSERT 新 segment 的进程记录（新 pid/pgid）

### Requirement: 启动时清理孤儿进程与陈旧 Lease

系统 MUST 在应用启动时扫描 status=active 且 heartbeat_at 超过 30 秒的 Lease，检查关联 FFmpeg 进程并清理。

#### Scenario: 孤儿进程 fingerprint 匹配后 kill

- **WHEN** cleanup_stale_leases() 发现一个过期 Lease
- **AND** 关联的 ffmpeg_registry 记录的 command_fingerprint 与存活的 PID 匹配
- **THEN** 系统 MUST 调用 os.killpg(pgid, SIGTERM) 终止进程组
- **AND** 关联 CaptureTake MUST 标记为 partial/failed
- **AND** Lease MUST 被 release

#### Scenario: PID 复用安全（fingerprint 不匹配）

- **WHEN** 过期 Lease 关联的 PID 存活但 command_fingerprint 不匹配
- **THEN** 系统 MUST NOT 终止该进程
- **AND** Lease MUST 被 release + 记录 warning 日志

### Requirement: 单 Worker 显式声明

CameraLease 解决崩溃恢复和互斥持久化，但 FFmpeg Popen 控制仍依赖单进程。本 Change MUST NOT 声称支持多 Uvicorn Worker 控制录制。

#### Scenario: 录制服务初始化位置

- **WHEN** API 应用启动
- **THEN** SessionService 和 SyncRecordingService MUST 在单个 Worker 中初始化
- **AND** 多个 Worker MUST NOT 各自持有独立的 Recorder/SyncRecorder 实例
