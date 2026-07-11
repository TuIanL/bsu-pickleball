## Why

单摄和双摄录制在 CaptureTake 创建时机、停止终态处理、Outbox 阻塞行为、摄像机互斥锁和异常恢复等方面存在多处竞态与不变量缺失，导致录制成功与否依赖线程调度顺序或数据库瞬时可用性，Live Coding 在双摄模式下不可用，停止录像被 Outbox 网络状态阻塞。必须在统一架构前先建立"录制会话—CaptureTake—CaptureTrack—CameraLease"之间不可破坏的生命周期不变量。

## What Changes

### CaptureTake 生命周期硬保证

- 新增 `CaptureTakeProvisioner` 统一服务，单摄和双摄启动录制时必须通过它在数据库事务中前置创建 CaptureTake + CaptureTrack，创建失败则拒绝启动 FFmpeg（**BREAKING**：移除了"CaptureTake 创建失败但录制照常启动"的降级行为）。
- 双摄 `start_session()` 新增 CaptureTake 创建，确保 `SyncRecordingSession.capture_take_id` 被正确填充，双摄 Live Coding 可正常初始化。
- 统一 `finalize_capture_take()` 方法，由正常停止、取消和异常退出共同调用，消除正常停止依赖 `_on_recorder_exit()` 异步回调竞态关闭 CaptureTake 的问题。`_try_close_capture_take()` 保持幂等。

### Outbox 与媒体停止解耦

- 停止录制时媒体停止优先于 Outbox 排空：点击停止后立即请求停止 FFmpeg，同时进行 best-effort Outbox drain，不再因网络断开阻塞录制停止（**BREAKING**：不再要求 Outbox 排空后才停止媒体）。
- 支持停止录制后补传未同步的现场事件，允许 CaptureTake 在 completed 后一段时间内接收迟到 CodingAction。

### CameraLease 统一互斥

- 新增 `CameraLeaseManager`，统一管理摄像机占用，替换当前单摄/双摄各自维护的进程内全局变量交叉查询。
- 双摄申请两台摄像机必须在同一数据库事务中原子完成。启动失败时释放 Lease。
- 记录 FFmpeg 进程信息，支持应用重启后扫描和清理孤儿进程与陈旧 Lease。

### 统一停止结果

- 新增统一 `CaptureStopResult`，单摄和双摄停止均返回相同结构（tracks 数组、analysis_available、warnings 等），单摄只是 tracks.length === 1。
- 停止返回值支持 `completed | partial | failed` 终态。

### 统一删除/清理

- 新增 `CaptureCleanupService`，单摄和双摄删除 session 时通过同一清理服务完成 CaptureTake、CaptureTrack、CaptureSegment、TimelineEvent、Video 资产和物理文件的级联清理，每一步幂等。

### 行为保护测试

- 为 `session_service.py` 和 `sync_recorder_service.py` 的关键生命周期补充 FakeRecorder 驱动的测试：启动、正常停止、取消、异常退出、CaptureTake 竞态场景、Lease 原子获取、启动恢复、重复删除幂等。

### 前端状态（仅基础适配，不做 Controller 重构）

- 双摄停止后读取 `CaptureStopResult`（**BREAKING**：`stopSyncRecording` 返回类型从 `SyncStopResponse` 改为 `CaptureStopResult`）。
- 单摄停止后同样读取 `CaptureStopResult`，移除 `isDualMode` 分支在停止完成面板中的 fork。
- Outbox 阻塞停止的逻辑移除，`capturePhase` 和 `outboxHealth` 拆为正交状态。

## Capabilities

### New Capabilities

- `capture-take-provisioning`: CaptureTake 作为录制会话不可破坏的不变量，前置事务创建、统一终态处理、幂等 finalize
- `camera-lease-management`: 统一的摄像机资源租约管理，原子获取多台摄像机、进程崩溃后 Lease 恢复
- `capture-cleanup`: 统一的录制资源清理服务，支持幂等级联删除
- `capture-outbox-decoupling`: Outbox 事件同步与媒体录制停止的生命周期分离，支持迟到事件补传

### Modified Capabilities

- `recording-session-control`: 启动流程改为 CaptureTake 前置创建（失败则拒绝启动）；停止流程改为显式调用 unified finalize；停止返回 `CaptureStopResult`
- `dual-camera-sync-recording`: 新增 CaptureTake + 2 CaptureTrack 创建；停止返回统一 `CaptureStopResult`
- `capture-workflow`: Outbox 不再作为停止门禁；capturePhase 与 outboxHealth 正交

## Impact

| 影响范围 | 内容 |
|---------|------|
| `backend/app/camera/session_service.py` | 重构 start/stop 流程，集成 CaptureTakeProvisioner、finalize、CameraLease |
| `backend/app/camera/sync_recorder_service.py` | 新增 CaptureTake 创建，重构 stop 流程，集成 CameraLease |
| `backend/app/camera/recorder.py` | 新增 FFmpeg PID 导出，供 CameraLease 进程登记 |
| `backend/app/services/capture_take_service.py` | 新增 unified finalize 方法、补传宽限期逻辑 |
| `backend/app/services/capture_cleanup_service.py` | **新增**，统一清理服务 |
| `backend/app/services/camera_lease_service.py` | **新增**，CameraLease 资源管理器 |
| `backend/app/models/camera_lease.py` | **新增**，CameraLease ORM 模型 |
| `backend/app/api/routes_recording.py` | 停止端点返回 `CaptureStopResult` |
| `backend/app/api/routes_sync_recording.py` | 停止端点返回 `CaptureStopResult` |
| `backend/app/schemas/` | 新增 `CaptureStopResult` schema |
| `backend/tests/` | 新增 FakeRecorder 驱动的生命周期测试 |
| `src/types/report.ts` | 新增 `CaptureStopResult` 类型；`stopSyncRecording` 返回类型变更（**BREAKING**） |
| `src/services/analysisClient.ts` | `stopSyncRecording` 返回类型更新 |
| `src/pages/CaptureConsolePage.tsx` | 停止完成面板统一读取 `CaptureStopResult`；移除 Outbox 阻塞停止逻辑 |
