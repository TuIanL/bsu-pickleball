## 1. CameraLease 基础设施

- [ ] 1.1 新增 `backend/app/models/camera_lease.py`，定义 `CameraLease` ORM 模型（camera_id PK, capture_take_id, source_session_id, owner_instance_id, status, acquired_at, heartbeat_at, expires_at）
- [ ] 1.2 新增 `backend/app/camera/camera_lease_service.py`，实现 `CameraLeaseManager` 类
- [ ] 1.3 实现 `acquire(camera_ids: list[str], capture_take_id: str) -> CameraLease`：在同一事务中原子获取，任一冲突则全部不获取
- [ ] 1.4 实现 `release(capture_take_id: str) -> None`：释放该 take 下所有 active Lease
- [ ] 1.5 实现 `heartbeat(capture_take_id: str) -> None`：更新 heartbeat_at
- [ ] 1.6 实现 `find_active_lease(camera_id: str) -> CameraLease | None`：查询单台摄像机占用状态
- [ ] 1.7 实现 `is_camera_available(camera_id: str) -> bool`：便捷查询方法
- [ ] 1.8 新增 `backend/app/camera/camera_lease_service.py` 中 `cleanup_stale_leases()`：启动时扫描过期 Lease，检查 FFmpeg 进程存活状态，清理孤儿 Lease
- [ ] 1.9 新增 `ffmpeg_registry` 表模型（pid, pgid, capture_take_id, track_id, command_fingerprint, output_path, started_at）

## 2. CaptureTakeProvisioner 统一创建

- [ ] 2.1 新增 `backend/app/services/capture_take_provisioner.py`，实现 `CaptureTakeProvisioner` 类
- [ ] 2.2 实现 `provision(field_session_id, capture_mode, source_session_type, source_session_id, tracks)` 方法
- [ ] 2.3 在数据库事务中原子创建 CaptureTake + N CaptureTrack
- [ ] 2.4 更新 `session_service.py` 的 `start_session()`：先获取 Lease → 再调用 Provisioner → 最后启动 FFmpeg（失败时释放 Lease）
- [ ] 2.5 更新 `sync_recorder_service.py` 的 `start_session()`：先获取两路 Lease → 再调用 Provisioner → 最后启动 SyncRecorder（失败时释放 Lease）
- [ ] 2.6 移除单摄 `start_session()` 中"CaptureTake 创建失败但录制照常启动"的降级逻辑（创建失败即拒绝启动）
- [ ] 2.7 双摄 `SyncRecordingSession.capture_take_id` 在启动后被正确填充

## 3. unified finalize 消除竞态

- [ ] 3.1 在 `backend/app/services/capture_take_service.py` 中新增 `finalize_capture_take(source_session_id, terminal_status, ended_at, duration_ms)` 方法
- [ ] 3.2 实现幂等逻辑：已 finalize 的 CaptureTake 再次调用不报错、不重复关闭
- [ ] 3.3 实现 CaptureSegment 关闭：找到所有 `end_ms` 为 null 的 open segment，设置 end_ms
- [ ] 3.4 将现有 `_try_close_capture_take()` 方法内部改为调用 unified `finalize_capture_take()`
- [ ] 3.5 在 `session_service.py` 的 `stop_session()` 中显式调用 `finalize_capture_take(session_id, "completed")`
- [ ] 3.6 在 `session_service.py` 的 `cancel_session()` 中调用 `finalize_capture_take(session_id, "canceled")`
- [ ] 3.7 在 `sync_recorder_service.py` 的 stop 流程中调用 `finalize_capture_take(session_id, "completed")`
- [ ] 3.8 在 `sync_recorder_service.py` 的 cancel 流程中调用 `finalize_capture_take(session_id, "canceled")`
- [ ] 3.9 `_on_recorder_exit()` 保留 finalize 调用（异常退出路径），但与显式调用互不干扰

## 4. Outbox 与媒体停止解耦

- [ ] 4.1 更新 `CaptureConsolePage.tsx` 的 `handleStopRecording()`：先调用 stop API，再进行 best-effort Outbox drain
- [ ] 4.2 更新 `CaptureConsolePage.tsx` 的 `handleDualStopRecording()`：同上
- [ ] 4.3 添加 `outboxHealth` 状态变量（"synced" | "pending" | "offline" | "failed"）
- [ ] 4.4 移除停止按钮上的 Outbox drain 等待逻辑（不再 drainConfirm 弹窗阻塞停止）
- [ ] 4.5 Outbox drain 改为 3 秒 deadline 的 best-effort，超时后未同步事件保留在 localStorage
- [ ] 4.6 完成后面板展示「有 N 条现场标记待同步」（当 outboxHealth 为 pending 时）
- [ ] 4.7 后端 `coding_actions_service.py` 新增迟到事件处理：检查 client_action_id 幂等 + 时间戳范围校验 + 宽限期检查
- [ ] 4.8 新增配置项 `CAPTURE_TAKE_LATE_EVENT_GRACE_MINUTES`（默认 5 分钟）

## 5. 统一 CaptureCleanupService

- [ ] 5.1 新增 `backend/app/services/capture_cleanup_service.py`，实现 `CaptureCleanupService` 类
- [ ] 5.2 实现 `delete_take(capture_take_id, *, delete_media)` 方法，按级联顺序清理
- [ ] 5.3 每一步实现幂等（已删除的实体再次删除不报错）
- [ ] 5.4 中途失败后下次调用从失败步骤继续（通过 take status 标记）
- [ ] 5.5 被 AnalysisJob 引用的视频阻止物理删除
- [ ] 5.6 活跃录制拒绝删除
- [ ] 5.7 更新 `session_service.py` 的 `delete_session()`：委托给 `CaptureCleanupService`
- [ ] 5.8 更新 `sync_recorder_service.py` 的 `delete_session()`：委托给 `CaptureCleanupService`

## 6. 统一 CaptureStopResult

- [ ] 6.1 新增 `backend/app/schemas/capture_stop_result.py`，定义 `CaptureTrackStopResult` 和 `CaptureStopResult` Pydantic schema
- [ ] 6.2 更新 `routes_recording.py` 的 `stop_recording()` endpoint：返回 `CaptureStopResult`
- [ ] 6.3 更新 `routes_sync_recording.py` 的 `stop_sync_recording()` endpoint：返回 `CaptureStopResult`
- [ ] 6.4 前端 `report.ts` 新增 `CaptureStopResult`、`CaptureTrackStopResult` TypeScript 接口
- [ ] 6.5 更新 `analysisClient.ts` 的 `stopRecording()` 返回类型为 `Promise<CaptureStopResult>`
- [ ] 6.6 更新 `analysisClient.ts` 的 `stopSyncRecording()` 返回类型为 `Promise<CaptureStopResult>`
- [ ] 6.7 更新 `CaptureConsolePage.tsx` 完成面板：统一读取 `CaptureStopResult`，移除 `isDualMode` 分支

## 7. 行为保护测试

- [ ] 7.1 新增 `FakeRecorder` 测试替身类（`backend/tests/fake_recorder.py`）
- [ ] 7.2 实现可控的 `start`/`stop`/`cancel` + 模拟异步 `on_exit` 回调
- [ ] 7.3 实现 `simulate_crash` 模式（模拟 FFmpeg 异常退出）
- [ ] 7.4 新增 `backend/tests/test_recording_lifecycle.py`：测试单摄 start → normal stop（CaptureTake completed + Lease released）
- [ ] 7.5 测试单摄 start → cancel（CaptureTake canceled + Lease released）
- [ ] 7.6 测试单摄 start → FFmpeg crash（CaptureTake failed + Lease released）
- [ ] 7.7 测试双摄 start → normal stop（2 CaptureTracks + Lease released）
- [ ] 7.8 测试 CaptureTakeProvisioner 失败时不启动 FFmpeg + Lease 释放
- [ ] 7.9 测试 stop_session 竞态场景：模拟 stop_session 先改 status → `_on_recorder_exit()` 后执行（CaptureTake 仍被 finalize）
- [ ] 7.10 测试 unified finalize 幂等性：对同一 session 连续调用 2 次 finalize_capture_take
- [ ] 7.11 测试 CameraLease 原子获取：两台中一台被占用时两台都不获取
- [ ] 7.12 测试 CameraLease 进程崩溃恢复：创建 stale Lease → 调用 cleanup → Lease 被 release
- [ ] 7.13 测试 CaptureCleanupService 幂等删除
- [ ] 7.14 测试 CaptureCleanupService 拒绝删除活跃录制
- [ ] 7.15 测试 Outbox 未同步时 stop 正常完成 + outboxHealth = pending
- [ ] 7.16 新增前端测试：单摄/双摄停止后读取 CaptureStopResult 结构一致

## 8. 构建与验证

- [ ] 8.1 运行 `pytest backend/tests/` 确认全量测试通过（含新增测试）
- [ ] 8.2 运行现有 `npm run test` 确认无回归
- [ ] 8.3 运行 `npm run build` 确认 TypeScript 编译通过
- [ ] 8.4 确认双摄 Live Coding 可正常初始化（手动验证 capture_take_id 存在）
- [ ] 8.5 确认停止录制不再被 Outbox 阻塞（手动验证网络断开场景）
- [ ] 8.6 确认 `CaptureStopResult` schema 单摄/双摄一致性
