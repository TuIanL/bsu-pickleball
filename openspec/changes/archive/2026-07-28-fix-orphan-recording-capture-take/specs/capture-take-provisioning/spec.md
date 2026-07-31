## ADDED Requirements

### Requirement: 启动时孤儿 CaptureTake 终态化

系统 MUST 在每次服务启动时，将 DB 中所有处于非终态（`starting` 或 `recording`）且无对应活跃录制进程的 `CaptureTake` 自动终态化为 `failed`。

#### Scenario: 崩溃重启后孤儿记录被修复

- **WHEN** 服务被中断后重新启动
- **AND** DB 中存在 `status` 为 `recording` 的 `CaptureTake` 记录
- **AND** 内存中 `SESSIONS` 和 `_ACTIVE_SYNC_SESSION_ID` 均为 None
- **THEN** 启动恢复流程 MUST 调用 `finalize_capture_take(take_id, "failed")`
- **AND** `has_active_capture_take()` SHALL 在修复后返回 False
- **AND** 修复 SHALL 发生在 `recover_orphan_recordings()` 中，位于 FFmpeg 进程清理之后

#### Scenario: 正常关闭后无孤儿残留

- **WHEN** 服务正常关闭（录制均已停止）
- **AND** 所有 `CaptureTake` 均已为终态
- **THEN** 启动恢复流程 MUST 正常完成（no-op）
- **AND** MUST NOT 产生错误日志或修改任何已终态的记录
