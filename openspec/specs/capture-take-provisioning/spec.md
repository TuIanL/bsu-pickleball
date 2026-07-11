# capture-take-provisioning Specification

## Requirements

### Requirement: CaptureStartCoordinator 统一启动编排

系统 MUST 提供 `CaptureStartCoordinator` 服务，在单个数据库事务中原子完成 CaptureTake 创建 + CaptureTrack 创建 + CameraLease 获取。任一子步骤失败则整体回滚，不得启动 FFmpeg。

#### Scenario: single 事务中创建 Take + Tracks + Leases

- **WHEN** 单摄录制启动被请求
- **THEN** Coordinator MUST 在单个数据库事务中创建 1 个 CaptureTake(status=starting) + 1 个 CaptureTrack + 1 个 CameraLease
- **AND** 任意一步失败 MUST 整体回滚
- **AND** 事务成功后 MUST 返回 PreparedCapture 供调用方启动 FFmpeg

#### Scenario: 双摄原子获取两路 Lease

- **WHEN** 双摄录制启动被请求
- **THEN** Coordinator MUST 在同一事务中创建 1 CaptureTake + 2 CaptureTrack + 2 CameraLease
- **AND** 任一 camera_id 存在 active Lease 冲突 MUST 触发整体回滚
- **AND** 事务中使用了 INSERT OR IGNORE + WHERE NOT EXISTS 实现原子检查

#### Scenario: FFmpeg 启动失败补偿

- **WHEN** Coordinator prepare_start 成功但 FFmpeg 启动失败
- **THEN** CaptureTake.status MUST 更新为 failed
- **AND** SourceSession.status MUST 更新为 failed
- **AND** 所有 CameraLease MUST 被 release
- **AND** 不得残留 active Lease

### Requirement: 状态转换严格定义

系统 MUST 扩展 CaptureTakeStatus 包含 starting 和 partial，并强制执行终态不可覆盖规则。

#### Scenario: 合法状态转换

- **WHEN** CaptureTake 处于 starting 状态
- **THEN** 允许转换为 recording | failed | canceled
- **WHEN** CaptureTake 处于 recording 状态
- **THEN** 允许转换为 completed | partial | failed | canceled

#### Scenario: 终态不可覆盖

- **WHEN** CaptureTake 已处于 completed/partial/failed/canceled
- **AND** 再次调用 finalize
- **THEN** 操作 MUST 幂等返回（不改变状态，不报错）
- **AND** 不得用另一个终态值覆盖已有终态

### Requirement: CaptureTakeProvisioner 前置创建入口

系统 MUST 要求正式录制 API（单摄和双摄）传入 `field_session_id` 且不可为空。CaptureTake.field_session_id 为 NOT NULL 外键。

#### Scenario: 正式录制 API 强制 field_session_id

- **WHEN** 客户端调用 POST /api/recordings/start 或 POST /api/sync-recordings/start
- **THEN** request body 中 field_session_id MUST 非空
- **AND** 为空时 MUST 返回 400 错误

#### Scenario: 旧版独立录制不创建 CaptureTake

- **WHEN** 向后兼容的独立录制被触发（如果有）
- **THEN** 该录制 MUST NOT 进入 Live Coding 工作流
- **AND** 不得强制创建 CaptureTake

### Requirement: unified finalize 使用 capture_take_id

系统 MUST 提供 `finalize_capture_take(capture_take_id, terminal_status, ended_at, duration_ms)` 方法，使用 capture_take_id 作为主键（非 source_session_id）。

#### Scenario: 正常停止 finalize

- **WHEN** 用户点击停止且 FFmpeg 正常退出
- **THEN** stop_session MUST 显式调用 `finalize_capture_take(capture_take_id, "completed")`
- **AND** CaptureTake 状态从 recording 更新为 completed

#### Scenario: 意外退出不标为 completed

- **WHEN** FFmpeg 进程在无用户请求下退出（returncode 任意值）
- **AND** RecorderExit.stop_requested=False 且 cancel_requested=False
- **THEN** 系统 MUST 调用 `finalize_capture_take(capture_take_id, "failed" 或 "partial")`
- **AND** MUST NOT 标为 completed
