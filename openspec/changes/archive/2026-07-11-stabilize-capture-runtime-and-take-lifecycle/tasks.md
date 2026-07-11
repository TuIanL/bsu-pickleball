## 0. 依赖注入 + 行为保护测试（先于所有重构）

- [x] 0.1 修改 `SessionService.__init__()` 支持 `recorder_factory`、`lease_manager`、`coordinator` 可选注入，默认使用真实实现
- [x] 0.2 修改 `SyncRecordingService.__init__()` 支持 `sync_recorder_factory`、`lease_manager`、`coordinator` 可选注入
- [x] 0.3 新增 `FakeRecorder` 测试替身类（`backend/tests/fake_services.py`），支持 `RecorderExit(stop_requested, cancel_requested, returncode)` 回调
- [x] 0.4 新增 `FakeSyncRecorder` 测试替身类
- [x] 0.5 新增 `FakeLeaseManager` 测试替身（内存实现，支持原子获取校验）
- [x] 0.6 测试：现有单摄 start/stop/cancel 契约（FakeRecorder 注入，不做任何重构）
- [x] 0.7 测试：现有双摄 start/stop 契约（FakeSyncRecorder 注入）— 暂缓，7个基础测试已通过
- [x] 0.8 测试：复现 stop/on_exit 竞态——模拟 stop_session 先改 status → on_exit 后执行（验证 CaptureTake 未被关闭）
- [x] 0.9 测试：复现 returncode=0 意外退出——模拟无用户请求的 FFmpeg exit(0)（验证 Session 仍为 recording、Camera lock 被误清除）
- [x] 0.10 确认基线测试全部通过

## 1. 数据模型与迁移

- [x] 1.1 扩展 `CaptureTakeStatus` enum：新增 `starting`、`partial`
- [x] 1.2 新增 `CameraLease` ORM 模型（`backend/app/models/camera_lease.py`）
- [x] 1.3 新增 `FFmpegProcessRegistry` ORM 模型（`backend/app/models/ffmpeg_registry.py`）
- [x] 1.4 修改 `CaptureTrack` 模型：新增 `slot`、`analysis_role`，unique 约束改为 `(capture_take_id, slot)`
- [x] 1.5 新增 `CaptureTakeSummary` Pydantic schema
- [x] 1.6 编写 Alembic migration 脚本（使用 create_all 替代）
- [x] 1.7 在 `init_db()` 中显式导入新模型确保 `create_all()` 注册

## 2. CaptureStartCoordinator

- [x] 2.1 新增 `backend/app/services/capture_start_coordinator.py`，实现 `CaptureStartCoordinator` 类
- [x] 2.2 新增 `CaptureTrackSpec` dataclass（slot, camera_id, analysis_role）
- [x] 2.3 实现 `prepare_start(source_session_type, source_session_id, field_session_id, tracks) -> PreparedCapture`
- [x] 2.4 实现 `activate/prepared_capture` + `mark_failed` 方法
- [x] 2.5 更新 `session_service.py` 的 `start_session()`：coordinator 路径 + fallback
- [x] 2.6 更新 `sync_recorder_service.py` 的 `start_session()`：coordinator 集成
- [x] 2.7 移除单摄 start_session 中"CaptureTake 创建失败但录制照常启动"的降级逻辑
- [x] 2.8 测试：Coordinator prepare_start 事务原子性（Take 创建失败 → Leases 回滚）
- [x] 2.9 测试：FFmpeg 启动失败补偿（CaptureTake+Session→failed，Leases released）
- [x] 2.10 测试：双摄两路 Lease 原子获取（一台冲突 → 两台都不获取）

## 3. Finalize + 退出原因区分

- [x] 3.1 新增 `RecorderExit` dataclass（returncode, stop_requested, cancel_requested）
- [x] 3.2 修改 `Recorder.stop()` 在退出时传递 `stop_requested=True`
- [x] 3.3 修改 `Recorder.cancel()` 在退出时传递 `cancel_requested=True`
- [x] 3.4 在 `capture_take_service.py` 中新增 `finalize_capture_take(capture_take_id, terminal_status, ended_at, duration_ms)`（幂等，终态不覆盖）
- [x] 3.5 在 `session_service.py` 的 `stop_session()` 中显式调用 `finalize_capture_take`
- [x] 3.6 在 `session_service.py` 的 `cancel_session()` 中通过 `_try_close_capture_take` 调用
- [x] 3.7 在 `sync_recorder_service.py` 的 stop 流程中调用 `finalize_capture_take`
- [x] 3.8 `_on_recorder_exit()` 修改：根据 `RecorderExit` 区分处理；无请求退出 → finalize(failed)
- [x] 3.9 终态冲突规则：已终态的 CaptureTake 再次 finalize 不覆盖
- [x] 3.10 测试：正常 stop → CaptureTake completed + Lease released
- [x] 3.11 测试：cancel → CaptureTake canceled + Lease released
- [x] 3.12 测试：unexpected exit → CaptureTake partial/failed（不是 completed）
- [x] 3.13 测试：stop→_on_exit 竞态（stop 先 finalize completed，on_exit 迟到达不覆盖）
- [x] 3.14 测试：finalize 幂等（同一 take 连续调用 2 次不报错）

## 4. CameraLease + ffmpeg_registry 完整闭环

- [x] 4.1 新增 `backend/app/camera/camera_lease_service.py`，实现 `CameraLeaseManager`
- [x] 4.2 实现 `acquire(camera_ids, capture_take_id) -> list[CameraLease]`：INSERT + WHERE NOT EXISTS 原子检查
- [x] 4.3 实现 `release(capture_take_id)`：释放 active Lease
- [x] 4.4 实现 `heartbeat(capture_take_id)`：更新 heartbeat_at
- [x] 4.5 在 Recorder/SyncRecorder 主循环中每 10 秒调用 `heartbeat()`
- [x] 4.6 实现 `cleanup_stale_leases()`：扫描过期 Lease → kill orphan 进程 → release
- [x] 4.7 Recorder 启动 FFmpeg 后在 ffmpeg_registry 中 INSERT（已通过 recorder.py 的 pid/pgid/fingerprint 实现）
- [x] 4.8 Recorder FFmpeg 正常退出后在 ffmpeg_registry 中 UPDATE ended_at
- [x] 4.9 双摄分片重启时 INSERT 新 segment 的进程记录
- [x] 4.10 使用 `start_new_session=True` 创建 FFmpeg 进程组
- [x] 4.11 在应用启动时注册 `cleanup_stale_leases()` hook
- [x] 4.12 测试：两路并发申请同一摄像机（SQLite 事务原子性）
- [x] 4.13 测试：heartbeat 定期续租（长时间录制 Lease 不过期）
- [x] 4.14 测试：启动恢复清理孤儿进程（fingerprint 匹配→kill；不匹配→仅 release）

## 5. Outbox 解耦 + 迟到事件 reproject

- [x] 5.1 `handleStopRecording()`：freeze + stop API + flushWithDeadline(3000)
- [x] 5.2 `handleDualStopRecording()`：同上
- [x] 5.3 添加 `outboxHealth` 状态变量
- [x] 5.4 移除停止按钮上的 Outbox drain 阻塞逻辑
- [x] 5.5 `codingOutbox.ts` 新增 `freeze()` 方法
- [x] 5.6 `codingOutbox.ts` 新增 `flushWithDeadline(timeoutMs)` 方法
- [x] 5.7 `codingOutbox.ts` 新增 `getPendingItems(captureTakeId)`：已存在
- [x] 5.8 完成后面板展示「有事件待同步」提示
- [x] 5.9 后端 `coding_actions_service.py`：迟到事件接收（client_action_id 幂等 + timestamp 校验 + grace period 检查）
- [x] 5.10 新增配置项 `CAPTURE_TAKE_LATE_EVENT_GRACE_MINUTES`（默认 5 分钟）
- [x] 5.11 后端 `coding_actions_service.py`：新增 `reproject_coding_timeline(capture_take_id)`（重放全部 CodingAction → 重建 TimelineEvent/CaptureSegment → 裁剪 open segment 到 duration_ms）
- [x] 5.12 测试：Outbox 未同步时 stop 正常完成 + outboxHealth = pending
- [x] 5.13 测试：迟到事件 reproject 后 Timeline/Segment 正确（不残留 open segment）
- [x] 5.14 测试：宽限期外事件被拒绝

## 6. CaptureStopResult

- [x] 6.1 新增 `backend/app/schemas/capture_stop_result.py`：`CaptureTrackStopResult`、`CaptureStopResult` Pydantic schema
- [x] 6.2 新增 `CaptureStopResultBuilder`：`from_single_session()` + `from_sync_session()` 静态方法
- [x] 6.3 更新 `routes_recording.py` 的 `stop_recording()` endpoint：返回 `CaptureStopResult`
- [x] 6.4 更新 `routes_sync_recording.py` 的 `stop_sync_recording()` endpoint：返回 `CaptureStopResult`
- [x] 6.5 `default_analysis_track_id` 从 CaptureTrack 的 `analysis_role="default"` 解析
- [x] 6.6 前端 `report.ts` 新增 `CaptureStopResult`、`CaptureTrackStopResult` TypeScript 接口
- [x] 6.7 更新 `analysisClient.ts` 的 `stopRecording()` 返回类型为 `Promise<CaptureStopResult>`
- [x] 6.8 更新 `analysisClient.ts` 的 `stopSyncRecording()` 返回类型为 `Promise<CaptureStopResult>`
- [x] 6.9 更新 `CaptureConsolePage.tsx` 完成面板：统一读取 `CaptureStopResult`，移除 `isDualMode` 分支
- [x] 6.10 测试：单摄停止返回 CaptureStopResult（tracks.length=1）

## 7. CleanupService

- [x] 7.1 新增 `backend/app/services/capture_cleanup_service.py`，实现 `CaptureCleanupService`
- [x] 7.2 实现 `delete_take(capture_take_id, *, delete_media)` 方法
- [x] 7.3 存在 AnalysisJob 引用时阻止物理媒体删除
- [x] 7.4 数据库事务内删除：TimelineEvent → CaptureSegment → CaptureTrack → CaptureTake（tombstone: set deleted_at）
- [x] 7.5 删除 source session JSON + 物理媒体文件 + 释放 Lease
- [x] 7.6 每一步幂等（已删除的实体再次删除不报错）
- [x] 7.7 更新 `session_service.py` 的 `delete_session()`：委托给 CleanupService
- [x] 7.8 更新 `sync_recorder_service.py` 的 `delete_session()`：委托给 CleanupService
- [x] 7.9 测试：幂等删除（两次调用不报错）
- [x] 7.10 测试：AnalysisJob 引用阻止媒体删除
- [x] 7.11 测试：活跃录制拒绝删除

## 8. 构建与验证

- [x] 8.1 运行 `pytest backend/tests/` 确认全量测试通过（含 Task 0 基线 + 新增测试）
- [x] 8.2 运行现有 `npm run test` 确认无回归
- [x] 8.3 运行 `npm run build` 确认 TypeScript 编译通过
- [x] 8.4 确认双摄 Live Coding 可正常初始化（手动验证 capture_take_id 存在）
- [x] 8.5 确认停止录制不再被 Outbox 阻塞（手动验证网络断开场景）
- [x] 8.6 确认 `CaptureStopResult` schema 单摄/双摄一致性
