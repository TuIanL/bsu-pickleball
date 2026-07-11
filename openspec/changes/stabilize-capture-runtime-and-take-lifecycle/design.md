## Context

当前录制架构存在两条独立路径：`SessionService`（单摄，`session_service.py`）和 `SyncRecordingService`（双摄，`sync_recorder_service.py`）。两者在 CaptureTake 创建、停止终态处理、摄像机互斥锁和异常恢复方面存在多处竞态与不变量缺失。

关键问题：
- 单摄 `stop_session()` 依赖 `Recorder._monitor()` 异步回调中的 `_on_recorder_exit()` 来关闭 CaptureTake，存在竞态窗口：如果 `stop_session()` 先将 session 改为 `completed`，`_on_recorder_exit()` 看到 status 不再为 `"recording"` 后跳过 `_try_close_capture_take()`，导致 CaptureTake 永远停在 recording。
- 双摄完全不创建 CaptureTake，Live Coding 不可用。
- 互斥锁使用进程内全局变量（`_ACTIVE_CAMERA`、`_ACTIVE_SYNC_CAMERAS`），进程崩溃后遗留锁。
- Outbox drain 阻塞媒体停止，网络断开时录制无法停止。

本 Change 是第一阶段的稳定化，不涉及前端 Controller 重构（Change 2）或单摄分片化（Change 3）。

## Goals / Non-Goals

**Goals:**

- 建立录制会话与 CaptureTake 的硬不变量：任何进入 recording 状态的 session，必须有且仅有一个 CaptureTake，其 source_session_id 指向该 session。
- 统一 finalize 入口，消除竞态。
- Outbox 与媒体停止解耦，停止操作不再被网络状态阻塞。
- 统一 CameraLease 互斥管理，支持进程崩溃后 Lease 恢复。
- 统一停止返回值 CaptureStopResult。
- 统一删除/清理服务。
- FakeRecorder 驱动的关键路径测试覆盖。

**Non-Goals:**

- 不将单摄迁移到分片录制核心（Change 3）。
- 不引入可配置双摄故障策略（Change 3）。
- 不做前端 `useCaptureController` 重构（Change 2）。
- 不做双摄按 fragment 的时间映射（Change 3）。
- 不修改分析 Pipeline 输入接口。
- 不重构 `CaptureConsolePage` 的组件拆分。

## Decisions

### 1. CaptureTakeProvisioner 作为统一入口

**决策**：新增 `CaptureTakeProvisioner` 服务，单摄和双摄启动录制前必须调用。在数据库事务中创建 CaptureTake + N 个 CaptureTrack，创建成功才允许启动 FFmpeg。

```python
class CaptureTakeProvisioner:
    def provision(
        self,
        *,
        field_session_id: str,
        capture_mode: Literal["single", "dual"],
        source_session_type: Literal["recording", "sync_recording"],
        source_session_id: str,
        tracks: list[CaptureTrackSpec],
    ) -> CaptureTake:
        ...
```

**原因**：避免单摄的"FFmpeg 先启动，CaptureTake 后创建，创建失败仅 warning"的降级逻辑，也避免双摄的两处重复创建。CaptureTake 缺失不能再被视为可接受降级。

**替代方案**：在每个 session service 内部各自创建 CaptureTake（类似当前单摄的实现）。拒绝原因：导致数据库逻辑重复，且无法保证"FFmpeg 启动前 CaptureTake 已存在"的不变式。

### 2. 统一 finalize_capture_take

**决策**：新增 `finalize_capture_take(source_session_id, terminal_status, ended_at, duration_ms)` 方法，由 `stop_session()`、`cancel_session()`、`_on_recorder_exit()` 三个调用点共同调用。方法内部幂等：已 finalize 的 CaptureTake 再次调用不报错。

同时保留 `_on_recorder_exit()` 中的调用路径（异常退出场景），但在 `stop_session()` 中添加显式调用（正常停止场景），消除竞态窗口。

```text
stop_session():
  1. Recorder.stop()
  2. session.status = "completed"
  3. persist
  4. clear_active
  5. finalize_capture_take(session, "completed")  ← 新增显式调用
  6. return

_on_recorder_exit():
  1. 读取 session
  2. 如果 status != "recording" → return
  3. 如果 returncode != 0 → session.status = "failed"
  4. persist
  5. clear_active
  6. finalize_capture_take(session, "failed")     ← 保留
```

`_try_close_capture_take()` 重命名为 `finalize_capture_take()` 并保持幂等。

**原因**：消除竞态，无论线程调度顺序如何，CaptureTake 都会被正确关闭。

**替代方案**：在 `Recorder.stop()` 中 join 监控线程，保证回调先于 stop_session 完成。拒绝原因：监控线程可能因 FFmpeg 僵死而长时间阻塞，join 会阻塞 API 响应。

### 3. Outbox 与媒体停止解耦

**决策**：停止录制时，媒体停止操作立即执行，不再等待 Outbox drain 完成。

```text
用户点击停止:
  1. 冻结编码按钮（禁止新事件入 outbox）
  2. 调用 stop API（停止 FFmpeg）
  3. 同时进行 best-effort Outbox drain（带 deadline，默认 3 秒）
  4. FFmpeg 停止后进入 finalizing
  5. 未同步事件保留在 localStorage，允许事后手动补传
```

后端 `executeCodingAction` 支持迟到事件：
- `client_action_id` 未执行过（幂等）
- `0 <= timestamp_ms <= capture_take.duration_ms`
- CaptureTake 在 completed 后的宽限期内（默认 5 分钟）

前端状态拆为正交：

```ts
capturePhase: "recording" | "stopping" | "finalizing" | "completed" | "partial" | "failed"
outboxHealth: "synced" | "pending" | "offline" | "failed"
```

**原因**：现场操作中，媒体安全 > 事件同步。网络断开时用户点停止，摄像机继续录制不可接受。

**替代方案**：给 Outbox drain 设置较长超时（30s）作为兜底。拒绝原因：仍然会让用户在"停止"按钮上等待，且无法根本解决"outbox 故障不应影响媒体安全"的原则问题。

### 4. CameraLease 统一互斥

**决策**：新增 `CameraLeaseManager` 和 `camera_leases` 数据库表，替代进程内全局变量的交叉查询。

```text
camera_leases
──────────────────────────
camera_id           UNIQUE
capture_take_id
source_session_id
owner_instance_id
status              "active" | "released"
acquired_at
heartbeat_at
expires_at
```

原子获取规则：

```python
# 单摄
lease = lease_manager.acquire([cam_id], capture_take_id)

# 双摄
lease = lease_manager.acquire([cam_1_id, cam_2_id], capture_take_id)
# 两台摄像机在同一个事务中原子获取，要么全成功，要么全失败
```

同时记录 FFmpeg 进程信息：

```text
ffmpeg_registry
──────────────────────────
capture_take_id
track_id
pid
pgid
command_fingerprint
output_path
started_at
```

**原因**：消除双向交叉查询的竞态，支持多 worker/进程重启场景。数据库事务保证原子性。

**替代方案**：使用 Redis 分布式锁。拒绝原因：项目当前无 Redis 依赖，增加运维复杂度。

### 5. 统一 CaptureStopResult

**决策**：新增 `CaptureStopResult` schema，单摄和双摄停止均返回此结构：

```python
class CaptureTrackStopResult(BaseModel):
    track_id: str
    slot: str  # "cam_1" | "cam_2"
    camera_id: str
    status: Literal["completed", "partial", "failed"]
    video_id: str | None
    duration_ms: int | None
    fragment_count: int
    restart_count: int

class CaptureStopResult(BaseModel):
    capture_take: CaptureTakeSummary
    tracks: list[CaptureTrackStopResult]
    analysis_available: bool
    default_analysis_track_id: str | None
    default_analysis_video_id: str | None
    analysis_blocked_reason: str | None
    warnings: list[str]
```

单摄只是 `tracks.length === 1`。

**原因**：消除前端 `isDualMode ? dualStopResponse : completedRecording` 的分支。

**替代方案**：继续使用 `RecordingSession` 和 `SyncStopResponse` 两个类型，在前端做 adapter。拒绝原因：增加前端维护负担，且两个类型的字段语义不完全对齐。

### 6. 统一 CleanupService

**决策**：新增 `CaptureCleanupService`，单摄和双摄删除时调用同一服务。

```text
delete_take(capture_take_id, *, delete_media=True):
  1. 检查是否仍处于 recording/starting（拒绝删除活跃会话）
  2. CaptureTake 标记 deleting
  3. 处理 AnalysisJob 引用（anonymize 或阻止删除）
  4. 删除或归档 TimelineEvent
  5. 删除 CaptureSegment
  6. 删除 CaptureTrack / Fragment 元数据
  7. 删除 Video 资产登记
  8. 删除物理媒体文件
  9. 删除 source session JSON
  10. 释放 CameraLease
  11. CaptureTake 硬删除或保留 tombstone
```

每一步幂等，中途失败后下次调用从上次位置继续。

**原因**：当前删除逻辑分散在 `session_service.delete_session()` 和 `sync_recorder_service.delete_session()` 中，前者只做基本清理，后者只删除文件，级联行为不一致。

### 7. 测试策略：FakeRecorder 替换 FFmpeg

**决策**：后端关键路径测试使用 `FakeRecorder` 替换真实 FFmpeg 进程。

```python
class FakeRecorder:
    """可控的 Recorder 替身，不启动真实 FFmpeg"""
    
    def __init__(self, *, simulate_crash: bool = False, exit_delay: float = 0):
        self._simulate_crash = simulate_crash
        self._exit_delay = exit_delay
        self.pid = 99999
        self.started = False
        self.stopped = False
    
    def start(self, *args, **kwargs):
        self.started = True
        # 模拟监控线程行为（延迟执行 on_exit）
    
    def stop(self):
        self.stopped = True
        # 模拟 FFmpeg 正常退出

    def cancel(self):
        self.stopped = True
        # 模拟 FFmpeg 被杀
```

**原因**：核心业务逻辑（状态转换、租赁获取/释放、finalize）不依赖真实 FFmpeg 行为，FakeRecorder 可以提供可控的测试时序。

**替代方案**：使用真实 FFmpeg 录制合成视频源。拒绝原因：CI 环境可能缺少 FFmpeg，且"录制 5 秒视频再停止"的测试耗时过长。

## Risks / Trade-offs

- [Risk] `CaptureStopResult` 返回类型变更对前端是 **BREAKING**。→ Mitigation：前端适配在本 Change 内完成，前端只改停止完成面板的逻辑，不动整个页面的结构。
- [Risk] `CameraLeaseManager` 引入数据库依赖，增加了录制启动的延迟。→ Mitigation：Lease 操作轻量（单行 UPSERT），相比 FFmpeg 启动延迟可忽略。
- [Risk] 旧 `SyncRecordingSession` JSON 文件（v1/v2 schema）在新版 `_load()` 中可能不兼容。→ Mitigation：保留兼容层，通过 `schema_version` 字段集中反序列化，不立即迁移历史数据。
- [Risk] FakeRecorder 无法完全模拟真实 FFmpeg 的异步退出时序。→ Mitigation：保留 1-2 个使用合成视频源的集成测试，CI 环境中条件跳过。
- [Risk] 迟到 CodingAction 补传的宽限期策略（5 分钟）可能在极端场景不够。→ Mitigation：宽限期可配置，后续可根据实际使用数据调整。
- [Risk] `preserve_primary` 故障策略不在本 Change 范围内，双摄在 Change 1 后仍使用"任一路失败杀全部"逻辑。→ Mitigation：已在 Change 3 规划中，本 Change 只保证 infrastructure 就绪。

## Migration Plan

1. 运行现有 `npm run test` 和 `pytest`，记录基线。
2. 新增 `CameraLease` 模型 + `CameraLeaseManager` 服务。
3. 新增 `CaptureTakeProvisioner`，单摄和双摄 start_session 改为调用它。
4. 新增 `finalize_capture_take()`，正常停止/取消/异常退出统一调用。
5. 实现 Outbox 解耦：后端补传宽限、前端移除 drain-before-stop 门禁。
6. 新增 `CaptureCleanupService`，替换两处 session delete 逻辑。
7. 新增 `CaptureStopResult` schema，更新两个停止端点。
8. 前端适配：完成面板读取 `CaptureStopResult`，移除 Outbox 阻塞。
9. 补充 FakeRecorder 驱动的生命周期测试。
10. 运行全量测试和构建。

## Open Questions

- 迟到事件补传的宽限期（默认 5 分钟）是否需要可配置？建议在 `settings.py` 中增加 `CAPTURE_TAKE_LATE_EVENT_GRACE_MINUTES` 配置项。
- `camera_leases` 表的 `heartbeat_at` 是否需要后台定时任务清理？建议应用启动时扫描，不另起定时任务。
- 旧 `SyncRecordingSession` JSON 是否在 Change 1 中就升级到 v3 schema？建议推迟到 Change 3，Change 1 只确保兼容读取。
