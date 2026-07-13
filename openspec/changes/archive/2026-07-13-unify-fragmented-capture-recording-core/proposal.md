## Why

单摄和双摄当前维护两套完全不同的 FFmpeg 生命周期：单摄使用 `Recorder`（stream copy → 1 个 MP4，崩溃全丢），双摄使用 `SyncRecorder`（TS 分片 → 同步重启 → stop 合并 MP4）。Change 1 和 Change 2 已统一后端生命周期不变量和前端录制状态机，但媒体录制核心仍然分裂，导致单摄可靠性远低于双摄、公共 TrackRecorder 无法复用、片段保全和恢复逻辑无法共享。

本 Change 从双摄 `SyncRecorder` 中提炼公共 `TrackRecorder`，将单摄和双摄统一到同一分片录制架构，引入可配置故障策略，建立 `MediaFragment` 持久化和 `CaptureTake` 时间到合并视频时间的映射。

## What Changes

### TrackRecorder 独立化

- 从 `SyncRecorder._record_segment_for_stream()` 提炼独立 `TrackRecorder` 组件：管理一个 CaptureTrack 的当前 FFmpeg 进程，完成 MediaFragment 生命周期。
- `TrackRecorder` 通过 `FragmentStartSpec` → `FragmentResult` 纯接口工作，不依赖 `SyncRecorder` 全局状态。
- 通过 `ProcessFactory`、`ProcessRegistry`、`Clock` 注入实现可单测。

### CaptureRuntimeCoordinator

- 新增 `CaptureRuntimeCoordinator`：负责运行期轨道协调、故障策略分发、停止与重启、terminal status 计算。
- 通过单一控制线程消费 TrackRuntimeEvent，不让多个 TrackRecorder 回调直接并发修改 CaptureTake。

### RecordingPolicy 故障策略

- 新增 `RecordingPolicy` 策略协议：`StrictSyncPolicy`、`PreservePrimaryPolicy`、`IndependentPolicy`。
- 单摄统一解析为 `SingleTrackRestartPolicy`（三策略在单轨下行为等价）。
- 定义 `max_restart_attempts` + 指数退避。

### MediaFragment 持久化 + 双索引

- 新增 `MediaFragment` ORM：`fragment_index`（per-track）+ `rotation_index`（全组同步轮换）+ 状态 + 时间偏移 + 文件元数据。
- 解决 `preserve_primary` 下辅轨单独重启后 fragment_index 不对齐的问题。

### CaptureFinalizer

- 新增 `CaptureFinalizer`：校验片段 → concat manifest → 临时 MP4 → ffprobe → 原子 rename → Video 注册 → `TrackTimelineMap`。
- 幂等：重复执行时复用已存在且校验通过的输出。

### TrackTimelineMap（时间映射）

- 取消全局 `offset_ms`，改为 `TrackTimelineSpan[]`，记录每个 Fragment 的 `take_start_ms` / `take_end_ms` 与 `output_start_ms` / `output_end_ms` 映射关系。
- 解决录制重启后合并视频时间漂移问题。

### ffmpeg_registry 分片级接入

- registry 增加 `fragment_id`、`return_code`、`exit_reason`。
- `ProcessRegistry` 改为注入式公共服务，不再由 `Recorder` 私有方法调用。
- 启动恢复：查询未结束的 registry → 校验 PID/PGID → 清理孤儿 → `MediaFragment` 标记 interrupted。

### Preflight 迁移

- 双摄短录测试改为临时 `TrackRecorder × 2`，不创建正式 CaptureTake。

### 删除旧核心

- 删除或降级 `Recorder`、`SyncRecorder`、`_record_segment_for_stream`、`_merge_segments` 等旧逻辑。

## Capabilities

### New Capabilities

- `track-recorder`: 独立单轨分片录制组件，管理一个 FFmpeg 进程完成一个 MediaFragment 生命周期
- `capture-runtime-coordinator`: 运行期轨道协调、故障策略分发、停止重启编排
- `recording-policy`: 可配置故障策略（StrictSync / PreservePrimary / Independent / SingleTrackRestart）
- `media-fragment-model`: MediaFragment 持久化 ORM + fragment_index/rotation_index 双索引
- `capture-finalizer`: 片段合并、ffprobe 校验、原子替换、Video 注册
- `track-timeline-map`: CaptureTake 时间轴到合并视频时间轴的映射

### Modified Capabilities

- `recording-session-control`: 单摄改为 TrackRecorder × 1 + CaptureFinalizer；stop 合并 TS 片段
- `dual-camera-sync-recording`: SyncRecorder 改为 TrackRecorder × 2 + StrictSyncPolicy
- `camera-lease-management`: ProcessRegistry 改为注入式公共服务 + fragment 级接入

## Impact

| 影响范围 | 内容 |
|---------|------|
| `backend/app/camera/track_recorder.py` | **新增**，独立 TrackRecorder |
| `backend/app/camera/capture_runtime_coordinator.py` | **新增**，运行期协调器 |
| `backend/app/camera/recording_policy.py` | **新增**，四种故障策略 |
| `backend/app/models/media_fragment.py` | **新增**，MediaFragment ORM |
| `backend/app/models/track_timeline_span.py` | **新增**，时间映射 ORM |
| `backend/app/camera/capture_finalizer.py` | **新增**，片段合并与注册 |
| `backend/app/camera/process_registry.py` | **重写**，注入式公共服务 |
| `backend/app/camera/recorder.py` | **删除**（降级为 TrackRecorder 单轨包装） |
| `backend/app/camera/sync_recorder_service.py` | **重构**，SyncRecorder → TrackRecorder × 2 + Policy |
| `backend/app/camera/session_service.py` | **重构**，Recorder → TrackRecorder × 1 + Finalizer |
| `backend/app/api/routes_recording.py` | 停止端点增加 finalization 状态 |
| `backend/app/api/routes_sync_recording.py` | 停止端点增加 fragment_count/restart_count |
| 前端 | 不修改 API 或状态机 |
