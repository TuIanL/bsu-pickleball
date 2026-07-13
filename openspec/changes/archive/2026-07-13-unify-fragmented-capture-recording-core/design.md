## Context

Change 1 建立了 CaptureTake/CameraLease/finalize 不变量，Change 2 统一了前端录制状态机。但媒体录制核心仍分叉：单摄 `Recorder`（直接 MP4，崩溃全丢）vs 双摄 `SyncRecorder`（TS 分片 + 同步重启 + stop 合并）。本 Change 从双摄提炼公共 `TrackRecorder`，统一分片架构。

## Goals / Non-Goals

**Goals:**

- 从 `SyncRecorder._record_segment_for_stream()` 提炼独立可单测的 `TrackRecorder`。
- 新增 `CaptureRuntimeCoordinator` 编排轨道运行、故障策略分发、stop/restart。
- 实现四种 RecordingPolicy：StrictSync / PreservePrimary / Independent / SingleTrackRestart。
- `MediaFragment` ORM + `TrackFinalization` ORM + `TrackTimelineSpan` ORM。
- `CaptureFinalizer`：同步片段合并 → ffprobe → 原子 rename → Video 注册。
- `CaptureCompletionService`：组合 RuntimeOutcome + FinalizationResult → 唯一终态决策。
- `PrepareCapture` 返回真实 `CaptureTrack.id`（不是 spec）。
- Finalizer 回写旧 Source Session 兼容字段。
- `ProcessRegistry` 注入式公共服务。
- 单摄迁移：TrackRecorder × 1 + SingleTrackRestartPolicy + 同步 Finalizer。
- 双摄迁移：TrackRecorder × 2 + StrictSyncPolicy（行为不变）。
- Preflight 通过 `InMemoryFragmentRepository` 复用 TrackRecorder。
- `scheduled_rotation`（定时切片）可选，默认 5 分钟计划轮换，限故障损失范围。

**Non-Goals:**

- 不做异步 Finalizer（保持同步停止→合并→返回）。
- 不修改前端 API 调用或状态机。
- 不删除 `CaptureTrack.offset_ms`（保留初始同步偏移，TrackTimelineSpan 是 per-track 内部分段映射）。
- 不实现硬件级帧同步、多 Worker 跨进程控制、云端上传、后台转码。

## Decisions

### 1. 同步 Finalizer

**决策**：本 Change 保持同步 Finalizer。用户停止后，后端停止 FFmpeg → 合并 → 校验 → 注册 → 返回最终结果。前端 Change 2 已有 `finalizing` 阶段（HTTP 响应等待期间展示），不需要后端新增中间状态。

增加 `finalizer_timeout_seconds`（默认 60s），超时按实际可用轨道返回 `partial + warnings`。

**原因**：异步 Finalizer 需要 CaptureTakeStatus.finalizing + job 持久化 + 轮询接口 + 前端恢复逻辑，应留给后续 Change。

### 2. 保留 CaptureTrack.offset_ms

**决策**：保留 `CaptureTrack.offset_ms` / `offset_source` / `sync_quality`（轨道间初始同步偏移）。新增 `TrackTimelineSpan[]`（同一轨道内一次重启产生的空档映射）。

```text
CaptureTake timestamp
→ 减去 CaptureTrack.offset_ms（轨道间同步偏差）
→ 定位对应 TrackTimelineSpan
→ 减去 gap_before_ms + output_start_ms 偏移
→ 得到 merged MP4 timestamp
```

**原因**：它们不是同一个概念，offset_ms 是轨道间偏差，TrackTimelineSpan 是轨道内分段空档。

### 3. PreparedCapture 返回真实 Track ID

**决策**：`CaptureStartCoordinator.prepare_start()` 返回 `PreparedTrack`（包含真实 `capture_track_id`），不是原始 `CaptureTrackSpec`。

```python
@dataclass(frozen=True)
class PreparedTrack:
    capture_track_id: str
    slot: str
    camera_id: str
    analysis_role: str
```

服务层直接使用 `prepared_track.capture_track_id`，不重新推算或事后查询。

### 4. 固化的启动顺序

**决策**：

```text
1. 生成 source session ID
2. CaptureStartCoordinator.prepare_start() → 获得真实 Take ID + Track ID + Leases
3. 为每个 Track 创建 starting MediaFragment
4. 启动 TrackRecorder
5. 全部必要轨道成功 → activate → recording
6. 部分失败 → 停止已启动轨道 → CaptureTake mark_failed → release Leases → Session failed
```

**原因**：消除「先 FFmpeg → 后 CaptureTake」的历史顺序问题。

### 5. CaptureCompletionService 唯一定终态

**决策**：Coordinator 返回 `CaptureRuntimeOutcome`（运行期结果），Finalizer 返回 `TrackFinalizationResult`（每轨媒体结果）。唯一由 `CaptureCompletionService` 组合两者决定最终终态，且只调用一次 `finalize_capture_take()`。

```text
主分析轨 finalization 失败 → failed
主轨成功、任意辅轨失败 → partial
所有要求轨道成功 → completed
用户 cancel → canceled
```

**原因**：消除 Coordinator 和 Finalizer 两个终态决策者的冲突。

### 6. TrackRecorder 单一完成所有者

**决策**：监控线程是唯一完成者。外部调用 `request_stop(reason)` 仅发送信号，monitor 负责 wait → 更新 registry → 更新 Fragment → 设置 FragmentResult → enqueue 一次事件。

```python
handle = recorder.start_fragment(spec)
handle.request_stop(reason)
result = handle.wait(timeout)
```

内部使用 Lock + completed_event + callback_emitted 防重入。

Coordinator 停止多轨时先 broadcast request_stop，再统一等待所有 handle。

### 7. Finalizer 回写 Source Session

**决策**：Finalizer 只返回 `TrackFinalizationResult`，由各 SessionService 回写兼容字段。

单摄：`RecordingSession.video_path` / `video_id` / `auto_analysis_job_id`
双摄：`SyncRecordingSession.registered_video_ids` / `default_analysis_video_id` / `associated_video_paths`
同时更新：`CaptureTrack.video_id`

### 8. TrackFinalization 持久化

**决策**：新增 `TrackFinalization` ORM 保存幂等信息。

```python
class TrackFinalization:
    id / capture_track_id / manifest_hash
    status: "running" | "completed" | "failed"
    output_path / video_id
    started_at / completed_at / error_message
```

UNIQUE(capture_track_id, manifest_hash)。Finalizer 重试时复用。

### 9. 定时切片（scheduled rotation）

**决策**：引入 `max_fragment_duration_seconds`（默认 300 = 5 分钟），正常录制中定期计划轮换。

```text
scheduled_rotation
→ 当前所有需要同步的轨道优雅结束
→ rotation_index + 1
→ 启动下一组 Fragment
```

不消耗 restart budget。如果暂不实现，Non-Goals 中声明「本 Change 仅在故障时切片」。

### 10. 数据库迁移

**决策**：已有表 `ffmpeg_registry` 新增 `fragment_id`/`return_code`/`exit_reason` 使用幂等 `ALTER TABLE`，延续项目现有模式。

### 11. CleanupService 扩展

**决策**：纳入 MediaFragment → TrackTimelineSpan → TrackFinalization → CaptureTrack 的级联删除，以及 TS 片段文件、concat manifest、临时/最终 MP4 的清理。cancel 标记 `discarded` 后交给 CleanupService 统一处理。

## Risks / Trade-offs

- [Risk] 同步 Finalizer 可能增加 stop API 响应延迟（数秒合并+校验）。→ Mitigation：`finalizer_timeout_seconds=60` 兜底，超时按 partial 返回。
- [Risk] 定时切片产生大量 TS 文件。→ Mitigation：5 分钟间隔均衡，cleanup 清除旧片段。
- [Risk] 旧 Recorder/SyncRecorder 删除影响其他调用方。→ Mitigation：先降级为 TrackRecorder 适配器，确认无其他引用后再删除。

## Migration Plan

按修正后的 13 步顺序（见 tasks.md）。
