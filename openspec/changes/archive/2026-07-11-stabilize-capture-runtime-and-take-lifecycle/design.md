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
- 不支持多 Uvicorn Worker 控制录制（CameraLease 解决互斥持久化，但 FFmpeg 控制仍依赖单进程内的 Popen 对象）。

## Decisions

### 1. CaptureStartCoordinator 统一启动编排

**决策**：新增 `CaptureStartCoordinator` 服务，在单个数据库事务中完成 CaptureTake 创建 + CaptureTrack 创建 + CameraLease 获取。调用方无需分别协调 Lease 和 Provisioner。

```python
class CaptureStartCoordinator:
    def prepare_start(
        self,
        *,
        source_session_type: Literal["recording", "sync_recording"],
        source_session_id: str,
        field_session_id: str,
        tracks: list[CaptureTrackSpec],
    ) -> PreparedCapture:
        """在数据库事务中原子完成：创建 CaptureTake + N CaptureTrack + N CameraLease。
           任意一步失败则整体回滚，不启动 FFmpeg。"""
        ...

@dataclass
class CaptureTrackSpec:
    slot: Literal["cam_1", "cam_2"]
    camera_id: str
    analysis_role: Literal["default", "supplementary"]
```

启动流程变为：

```text
Coordinator.prepare_start()           ← 单事务：Take + Tracks + Leases
    ↓
启动 FFmpeg 进程                       ← 成功才标记 recording
    ↓
CaptureTake.status = "recording"
SourceSession.status = "recording"
    ↓
FFmpeg 启动失败？
    ↓
CaptureTake.status = "failed"
release Leases
SourceSession.status = "failed"
```

**原因**：消除 Lease 需要 `capture_take_id` 但 CaptureTake 尚未创建的循环依赖。Coordinator 在事务内先生成 `capture_take_id`，再在同一事务中创建 Lease。

**替代方案**：先创建临时 `capture_take_id` 再传给 Lease。拒绝原因：如果后续 CaptureTake 创建失败，需要回滚 Lease 的 capture_take_id 引用，逻辑复杂且容易残留垃圾数据。

### 2. FieldSession 必选策略

**决策**：正式录制 API（`POST /api/recordings/start` 和 `POST /api/sync-recordings/start`）强制要求 `field_session_id`。旧的独立录制接口保留为 legacy，不进入 Live Coding 工作流（不创建 CaptureTake）。

**原因**：`CaptureTake.field_session_id` 是不可为空的外键。必须消除 FieldSession 可选与"所有 session 都需要 CaptureTake"之间的矛盾。

**替代方案**：无 FieldSession 时自动创建 ad-hoc FieldSession。拒绝原因：增加不可见的数据实体，且语义上独立录制不应被强行关联到虚假的采集任务。

### 3. 状态转换表

**决策**：扩展 `CaptureTakeStatus` 为 6 个状态，定义严格的状态转换图。

```text
CaptureTakeStatus:
  starting
  recording
  completed
  partial
  failed
  canceled

转换规则（第一个合法终态获胜）:
  starting   → recording | failed | canceled
  recording  → completed | partial | failed | canceled
  completed  → 终态（不允许覆盖）
  partial    → 终态（不允许覆盖）
  failed     → 终态（不允许覆盖）
  canceled   → 终态（不允许覆盖）
```

`stopping` 和 `finalizing` 保留为前端/API 过程状态，不持久化到数据库。`deleting` 不由 CaptureTake 状态表达，由 CaptureCleanupService 通过步骤幂等性保证恢复。

**原因**：当前只有 4 种状态（`recording/completed/failed/canceled`），缺少 `starting`（Provisioner 创建后、FFmpeg 启动前）和 `partial`（部分轨道可用）。

### 4. 统一 finalize + 退出原因区分

**决策**：`finalize_capture_take()` 使用 `capture_take_id` 作为主键（不是 `source_session_id`）。Recorder 回调增加退出原因字段。

```python
class RecorderExit:
    returncode: int
    stop_requested: bool       # 用户调用了 stop()
    cancel_requested: bool     # 用户调用了 cancel()

def finalize_capture_take(
    capture_take_id: str,
    terminal_status: Literal["completed", "partial", "failed", "canceled"],
    ended_at: datetime,
    duration_ms: int,
) -> None:
    ...
```

处理规则：

```text
stop_requested = True:
  → stop_session() 显式调用 finalize(completed)
  → on_exit 仅做进程退出确认，不再次 finalize

cancel_requested = True:
  → cancel_session() 显式调用 finalize(canceled)

没有请求但进程自行退出（无论 returncode）:
  → 判定为 unexpected exit
  → finalize(partial)（如果有可用轨道）或 finalize(failed)
  → 之前 returncode=0 也被标成 completed 的 bug 被修复
```

终态冲突处理：

```python
def finalize_capture_take(capture_take_id, terminal_status, ...):
    take = get(capture_take_id)
    if take.status in ("completed", "partial", "failed", "canceled"):
        return  # 已终态，幂等跳过（不覆盖）
    take.status = terminal_status
    # close open segments, etc.
```

**原因**：修复不受请求的 `returncode=0` 被错误标记为 `completed` 的问题；`capture_take_id` 比 `source_session_id` 更精确（因为唯一约束是 `(source_session_type, source_session_id)` 组合而非单字段）；终态不覆盖规则消除竞态。

### 5. Outbox 与媒体停止解耦

**决策**：停止录制时，媒体停止操作立即执行，不再等待 Outbox drain 完成。

```text
用户点击停止:
  1. freeze() — 禁止新事件入 outbox
  2. 立即调用 stop API（停止 FFmpeg）
  3. 同时进行 best-effort flushWithDeadline(timeoutMs=3000)
  4. FFmpeg 停止后进入 finalizing
  5. 未同步事件保留在 localStorage，页面提供「重新同步」入口
```

后端迟到事件处理：

```text
迟到 CodingAction 到达:
  1. 校验 client_action_id 未执行过（幂等）
  2. 校验 0 <= timestamp_ms <= capture_take.duration_ms
  3. 校验 capture_take.ended_at + grace_period > now
  4. 写入 CodingAction 事实日志
  5. 调用 reproject_coding_timeline(capture_take_id):
     a. 按 timestamp_ms + sequence_number 重放所有 CodingAction
     b. 重建 TimelineEvent / CaptureSegment 派生投影
     c. 最后将仍 open 的 segment 裁剪到 duration_ms
```

前端状态拆为正交：

```ts
capturePhase: "recording" | "stopping" | "finalizing" | "completed" | "partial" | "failed"
outboxHealth: "synced" | "pending" | "offline" | "failed"
```

`codingOutbox.ts` 新增方法：
- `freeze()`：停止后禁止新事件入队
- `flushWithDeadline(timeoutMs)`：带 deadline 的 best-effort drain
- `getPendingItems(captureTakeId)`：页面重载后恢复未同步事件
- `retryBlockedItems(captureTakeId)`：手动重试入口

**原因**：现场操作中媒体安全 > 事件同步。不能因为简单放宽状态校验导致 completed 后出现新的 open segment。

**替代方案**：给 Outbox drain 设置较长超时（30s）。拒绝原因：仍然阻塞用户操作，且迟到事件缺少 reproject 仍会造成数据不一致。

### 6. CameraLease 完整闭环

**决策**：新增 `CameraLeaseManager`，使用 SQLite 条件 INSERT 在事务中原子获取 Lease。

**SQLite 原子实现**：

```python
def acquire(self, camera_ids: list[str], capture_take_id: str) -> list[CameraLease]:
    with db.transaction():
        for camera_id in camera_ids:
            # INSERT OR IGNORE: 如果 camera_id 已有 active Lease，跳过
            result = db.execute(
                "INSERT INTO camera_leases (camera_id, capture_take_id, status, ...) "
                "SELECT ?, ?, 'active', ... "
                "WHERE NOT EXISTS (SELECT 1 FROM camera_leases WHERE camera_id=? AND status='active')",
                [camera_id, capture_take_id, camera_id]
            )
            if result.rowcount == 0:
                raise LeaseConflictError(camera_id)
        leases = db.query(CameraLease).filter(...).all()
        return leases  # 返回 list[CameraLease]，不是单个
```

**Heartbeat 调用者**：Recorder 和 SyncRecorder 的主循环中每 10 秒调用 `lease_manager.heartbeat(capture_take_id)`。不另起后台线程。

**ffmpeg_registry 完整维护链**：
- Popen 启动后：INSERT 记录 (pid, pgid, capture_take_id, track_id, command_fingerprint, output_path, started_at)
- 正常退出后：UPDATE set ended_at
- 双摄分片重启：INSERT 新 fragment 的进程记录
- 应用启动恢复 `cleanup_stale_leases()`：
  1. 扫描 status=active 且 heartbeat_at 超过 30 秒的 Lease
  2. 查询关联的 ffmpeg_registry 记录
  3. 校验 command_fingerprint 匹配后再 os.killpg(pgid, SIGTERM)
  4. PID 复用安全：fingerprint 不匹配则仅 release Lease + warning 日志
  5. 关联 CaptureTake 标记为 partial/failed
  6. 释放 Lease

**单 Worker 明确声明**：CameraLease 解决崩溃恢复和互斥持久化，但 FFmpeg 控制仍依赖单进程内的 Popen 对象。本 Change 不支持多 Uvicorn Worker 控制同一录制。

**原因**：消除双向交叉查询的竞态；Lease 操作在 FFmpeg 启动延迟前可忽略。

**替代方案**：使用 Redis 分布式锁。拒绝原因：项目当前无 Redis 依赖。

### 7. 统一 CaptureStopResult

**决策**：新增 `CaptureStopResult` schema，由 `CaptureStopResultBuilder` 统一构建，单摄和双摄停止均返回此结构。

```python
class CaptureTrackStopResult(BaseModel):
    track_id: str
    slot: Literal["cam_1", "cam_2"]
    camera_id: str
    analysis_role: Literal["default", "supplementary"]
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

class CaptureStopResultBuilder:
    @staticmethod
    def from_single_session(recording_session: RecordingSession, capture_take: CaptureTake) -> CaptureStopResult: ...
    
    @staticmethod
    def from_sync_session(sync_session: SyncRecordingSession, capture_take: CaptureTake) -> CaptureStopResult: ...
```

`default_analysis_track_id` 从 CaptureTrack 的 `analysis_role="default"` 解析，不硬编码 cam_1。数据库 `CaptureTrack` 的 unique 约束从 `(capture_take_id, role)` 调整为 `(capture_take_id, slot)`。

单摄使用 `slot="cam_1"`，只有一条 track。

**原因**：消除前端分支，分离物理槽位和分析角色。

### 8. 统一 CleanupService

**决策**：新增 `CaptureCleanupService`，提取现有单摄 `delete_session()` 中的清理逻辑到公共服务，补齐双摄清理。

**范围收紧**：

```text
delete_take(capture_take_id, *, delete_media=True):
  1. 存在 AnalysisJob 引用 → 阻止物理媒体删除，返回 blocked 错误
  2. 数据库事务内：删除 TimelineEvent → CaptureSegment → CaptureTrack → CaptureTake
  3. 删除 source session JSON
  4. 删除物理媒体文件
  5. 释放 CameraLease
  6. CaptureTake 保留 tombstone（设置 deleted_at），不硬删除
```

**策略已决**：
- AnalysisJob 引用 → 阻止物理媒体删除（不 anonymize）
- CaptureTake → 保留 tombstone（`deleted_at`），不硬删除
- 每一步幂等（反复调用不报错），不从中途恢复（每次从头重试）

**原因**：当前单摄 `delete_session()` 已做了 TimelineEvent/CaptureTrack/CaptureCodingAction/CaptureSegment/CaptureTake 的删除，Change 1 是提取+补齐，不是从零新增。

### 9. 依赖注入 + 测试优先

**决策**：SessionService 和 SyncRecordingService 支持 Recorder 工厂注入，不依赖模块级全局对象。

```python
class SessionService:
    def __init__(self, recorder_factory=None, lease_manager=None, coordinator=None):
        self._recorder_factory = recorder_factory or (lambda: Recorder())
        ...

class SyncRecordingService:
    def __init__(self, sync_recorder_factory=None, lease_manager=None, coordinator=None):
        self._sync_recorder_factory = sync_recorder_factory or (lambda: SyncRecorder())
        ...
```

测试使用 `FakeRecorder` 和 `FakeSyncRecorder` 替身，通过工厂注入。

```python
class FakeRecorder:
    def __init__(self, *, simulate_crash: bool = False, exit_code: int = 0,
                 stop_requested: bool = False, cancel_requested: bool = False):
        ...
    
    def start(self, on_exit, *args, **kwargs):
        self._on_exit = on_exit
        self.started = True
    
    def stop(self):
        self.stop_requested = True
        # 模拟 FFmpeg 退出，调用 on_exit(RecorderExit(returncode=0, stop_requested=True))
    
    def cancel(self):
        self.cancel_requested = True
    
    def simulate_unexpected_exit(self, returncode: int = 0):
        # 模拟无请求的异常退出
        self._on_exit(RecorderExit(returncode=returncode, stop_requested=False, cancel_requested=False))
```

**原因**：核心生命周期不依赖 FFmpeg 行为，依赖注入让测试脆弱性降到最低。测试必须在重构前编写（Task 0），而不是事后补。

### 10. 测试顺序

测试不是 Task 7，而是 **Task 0**：

```
0. 依赖注入 + 行为保护测试
1. 数据模型与迁移
2. CaptureStartCoordinator
3. Finalize + 退出原因区分
4. Lease heartbeat + 启动恢复
5. Outbox 解耦 + 迟到事件 reproject
6. CaptureStopResult
7. CleanupService
```

## Risks / Trade-offs

- [Risk] `CaptureStopResult` 返回类型变更对前端是 **BREAKING**。→ Mitigation：前端适配在本 Change 内完成，只改停止完成面板。
- [Risk] `CameraLeaseManager` 引入数据库依赖。→ Mitigation：Lease 操作轻量（单行 INSERT OR IGNORE），在 FFmpeg 启动之前完成。
- [Risk] 旧 `SyncRecordingSession` JSON（v1/v2 schema）在新版 `_load()` 中可能不兼容。→ Mitigation：保留兼容层，不立即迁移历史数据。
- [Risk] FakeRecorder 无法完全模拟真实 FFmpeg 异步退出时序。→ Mitigation：保留 1-2 个合成视频源集成测试，CI 中条件跳过。
- [Risk] 迟到事件宽限期（5 分钟）可能不够。→ Mitigation：可配置 `CAPTURE_TAKE_LATE_EVENT_GRACE_MINUTES`；提供手动重试入口。
- [Risk] `preserve_primary` 故障策略在 Change 3 才引入。→ Mitigation：Change 1 只建基础设施。
- [Risk] 单 Uvicorn Worker 约束。→ Mitigation：在 design 和代码注释中明确声明，不在文档中声称支持多 Worker。

## Migration Plan

1. 注入 recorder_factory / lease_manager / coordinator 到 SessionService 和 SyncRecordingService
2. 编写 Task 0 行为保护测试（FakeRecorder 驱动）
3. 新增 `CaptureTakeStatus` 扩展 + `CameraLease` + `ffmpeg_registry` 模型 + Alembic migration
4. 新增 `CaptureStartCoordinator`，单摄和双摄 start_session 改为调用它
5. 新增 `finalize_capture_take(capture_take_id, ...)` + `RecorderExit`，正常停止/取消/异常退出统一调用
6. 实现 Outbox 解耦：freeze/flushWithDeadline + 后端 `reproject_coding_timeline()`
7. 新增 `CaptureStopResultBuilder` + `CaptureStopResult` schema，更新两个停止端点
8. 新增 `CaptureCleanupService`，提取+补齐清理逻辑
9. 前端适配：完成面板读取 `CaptureStopResult`，移除 Outbox 阻塞
10. 运行全量测试和构建

## Open Questions

- 迟到事件补传宽限期默认值：建议 5 分钟，通过 `CAPTURE_TAKE_LATE_EVENT_GRADE_MINUTES` 配置。
- `camera_leases.heartbeat_at` 清理：应用启动时扫描 + Recorder 主循环中续租，不另起定时任务。
- 旧 `SyncRecordingSession` JSON 升级：推迟到 Change 3，Change 1 只兼容读取。
