# orphan-capture-take-recovery Specification

## Purpose

定义服务启动和录制 session 自愈时对孤儿 CaptureTake、单路 session 与双路 session 的恢复边界。

## Requirements

### Requirement: 启动时修复孤儿 CaptureTake

系统 MUST 在启动恢复流程（`recover_orphan_recordings`）中，将 DB 中所有仍处于 `starting` 或 `recording` 状态且无对应活跃录制进程的 `CaptureTake` 终态化为 `failed`。

#### Scenario: 服务器崩溃重启后孤儿 CaptureTake 被修复

- **WHEN** 服务器启动并执行 `recover_orphan_recordings()`
- **AND** 存在 `CaptureTake` 记录其 `status` 为 `recording`
- **AND** 对应的 FFmpeg 进程已被上一步清理
- **THEN** 系统 MUST 将该 `CaptureTake.status` 更新为 `failed`
- **AND** 系统 MUST 设置 `ended_at` 为当前时间
- **AND** 系统 MUST 计算并记录 `duration_ms`
- **AND** `has_active_capture_take()` SHALL 返回 False

#### Scenario: 已终态的 CaptureTake 不被孤儿修复覆盖

- **WHEN** `CaptureTake.status` 已为 `completed`、`partial`、`failed` 或 `canceled`
- **THEN** 孤儿修复逻辑 MUST 跳过该记录
- **AND** 其状态和结束时间 MUST NOT 被修改

#### Scenario: 启动时不存在孤儿 CaptureTake

- **WHEN** 启动恢复时 DB 中无 `starting`/`recording` 状态的 `CaptureTake`
- **THEN** 孤儿修复步骤 MUST 正常完成（no-op）
- **AND** MUST NOT 产生错误日志

### Requirement: 单路录制 session 列表自愈

单路 `session_service.list_sessions()` 在扫描磁盘 JSON 时 MUST 检测 session JSON 状态为 `recording` 但服务端内存中无对应活跃会话的情况，并 MUST 将 session 和关联 `CaptureTake` 同步修复为 `failed`。

#### Scenario: session JSON 为 recording 但无活跃进程

- **WHEN** `list_sessions()` 从磁盘加载 session JSON 且其 `status` 为 `"recording"`
- **AND** `session_service.find_active_session(camera_id)` 返回 None（该摄像头无活跃录制）
- **THEN** 系统 MUST 将 session JSON `status` 更新为 `"failed"`
- **AND** 系统 MUST 设置 `stopped_at` 和 `error_message`
- **AND** 系统 MUST 持久化修复后的 session JSON
- **AND** 系统 MUST 调用 `finalize_capture_take(capture_take_id, "failed")` 终态化关联 CaptureTake
- **AND** 修复后的 session 因其 `status` 为 `"failed"`，当调用方 `status == "recording"` 过滤时，MUST NOT 出现在结果中

#### Scenario: 单路 session JSON 正常活跃无需自愈

- **WHEN** session JSON `status` 为 `"recording"`
- **AND** `find_active_session(camera_id)` 返回非 None（存在活跃录制进程）
- **THEN** 系统 MUST NOT 修改 session JSON
- **AND** 系统 MUST NOT 调用 `finalize_capture_take`

### Requirement: 双路录制自愈同步修复 CaptureTake

双路 `sync_recorder_service.list_sessions()` 在自愈修复 session JSON 时 MUST 同步终态化关联的 `CaptureTake`。

#### Scenario: 双路 session JSON 自愈时同步清理 CaptureTake

- **WHEN** `list_sessions()` 检测到 session JSON `status` 为 `"recording"` 且 `is_recording()` 返回 False
- **AND** 系统将 session JSON 更新为 `"failed"`
- **THEN** 系统 MUST 调用 `finalize_capture_take(capture_take_id, "failed")` 终态化关联 CaptureTake
- **AND** `has_active_capture_take()` SHALL 在修复后返回 False

#### Scenario: 双路自愈时 session 无 capture_take_id

- **WHEN** 自愈触发的 session 无 `capture_take_id` 字段
- **THEN** 系统 MUST 正常完成 session JSON 修复
- **AND** MUST NOT 因 capture_take_id 缺失而抛出异常
