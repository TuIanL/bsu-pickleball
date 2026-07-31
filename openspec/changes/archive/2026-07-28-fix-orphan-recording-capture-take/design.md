## Context

当前系统存在两套「活跃录制」检测机制，它们在服务端异常重启后脱节：

```
来源 A（DB 层）                    来源 B（Session JSON 层）
capture_take_service               session_service
  .get_active_capture_take()         .list_sessions()
  .has_active_capture_take()
     ↓                                ↓
  CaptureTake 表                   磁盘 *.json 文件
  status IN ('starting',           status == 'recording'
    'recording')
     ↓                                ↓
  侧边栏红点、409 拦截              控制台 hydrate() 入口
```

`recover_orphan_recordings()`（`capture_recovery.py`）启动时清理了 FFmpeg 进程、MediaFragment、CameraLease，但未更新 CaptureTake 状态。双路 `list_sessions` 的自愈逻辑（`sync_recorder_service.py:1884-1890`）修复了 session JSON 但未同步 CaptureTake，反而让 session 和控制台进一步脱节。单路 `list_sessions` 完全没有自愈逻辑。

## Goals / Non-Goals

**Goals:**
1. 服务端启动时，`recover_orphan_recordings()` 完成后，所有孤儿 `CaptureTake`（`starting`/`recording` 且无对应活跃进程）必须终态化为 `failed`
2. 双路 `list_sessions` 自愈修复 session JSON 时，必须同步终态化关联 `CaptureTake`
3. 单路 `list_sessions` 新增自愈逻辑：session JSON 为 `recording` 但内存中无活跃 session → 标记 `failed` + 终态化 `CaptureTake`
4. 前端侧边栏 `ActiveRecordingBlock` 提供兜底的「强制终止」入口，在孤儿场景下用户可主动解除 409 阻塞

**Non-Goals:**
- 不改变 `has_active_capture_take()` 的 3 小时超时逻辑
- 不修改录制启动/停止的正常流程
- 不对历史已终态的 CaptureTake 做回溯修正
- 不引入新的数据库表或前端路由

## Decisions

### 1. 孤儿判定策略：启动后「全量 orphan」

**决策：** 在 `recover_orphan_recordings()` 执行完成（FFmpeg 已杀、Fragment 已标记、Lease 已释放）后，DB 中所有仍处于 `starting`/`recording` 的 `CaptureTake` 一律视为孤儿，全部终态化为 `failed`。

**理由：** 服务器启动时内存中 `SESSIONS` 和 `_ACTIVE_SYNC_SESSION_ID` 均为空，不存在任何合法活跃会话。任何 `CaptureTake` 如果仍然是 `starting`/`recording`，只能是上次崩溃残留。

**替代方案及舍弃理由：**
- 逐条检查对应 session JSON + FFmpeg 进程：过于复杂，且进程已在上一步杀掉了，无法比对。
- 仅修复关联到刚被杀进程的 CaptureTake：`FFmpegProcessRegistry` 到 `CaptureTake` 之间没有直接外键，关联依赖中间表。

### 2. 自愈入口位置：在 `list_sessions`（非独立定时任务）

**决策：** 单双路 session 的自愈逻辑放在 `list_sessions()` 方法内，在扫描磁盘 JSON 时顺带做修复，不引入额外的后台定时任务。

**理由：**
- `list_sessions` 是前端 hydrate 和列表页的主要数据入口，修复在此处最自然地阻断不一致数据流向前端
- 无需管理额外的调度器生命周期
- 双路已有此模式（`sync_recorder_service.py:1884`），单路对齐即可

**替代方案及舍弃理由：**
- 独立后台定时任务扫描：需要额外线程管理、需要处理任务重复执行问题，过度设计。

### 3. 前端「强制终止」策略：兜底调用 cancel API

**决策：** `ActiveRecordingBlock` 点击跳转到控制台后，若控制台 hydrate 结果为 `NO_ACTIVE_SESSION`（session 已自愈为 failed 但 CaptureTake 未清理），侧边栏通过 `useActiveCaptureTake` 暴露 `forceCancel` 回调。用户可在侧边栏直接点「终止录制」，调用 `cancelRecording` / `cancelSyncRecording` 清理 session + CaptureTake。

**理由：**
- 不改变现有导航行为
- 给用户一个明确的出口来解除 409 阻塞
- `cancelRecording` / `cancelSyncRecording` 会调用 `_finalize_capture_take_on_stop`，确保 CaptureTake 被清理

**替代方案及舍弃理由：**
- 自动跳转到控制台才展示终止按钮：控制台 hydrate 可能是瞬态的，用户可能看不到按钮就离开了。
- 后端开放 `POST /api/capture-takes/active/force-finalize` 独立 API：增加了 API 表面积，且单双路分别需要不同清理逻辑，不如复用已有 cancel 链路。

### 4. CaptureTake 清理幂等性

**决策：** 使用已有 `finalize_capture_take()` 方法（`capture_take_service.py:256`），其内部 267 行已有终态不可覆盖的幂等保护：`if take.status in _TERMINAL_STATUSES: return take`。

**理由：** 复用现有幂等逻辑，无需新增防御代码。孤儿修复只对 `starting`/`recording`（非终态）生效，已终态的不受影响。

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| 启动时孤儿修复与并发 start 请求竞态（极少见） | orphan 修复在 startup 事件中同步执行（单线程），start 请求之后才可能进来 |
| `list_sessions` 自愈在 cold path 触发 DB 写入，增加请求延迟 | 仅在首次扫描到此 session JSON 时触发一次（修复后 session JSON status 变为 failed，下次不触发）。单次 DB flush 延迟 < 50ms |
| 前端「强制终止」按钮误触导致正在录制中的会话被终止 | 按钮仅在检测到孤儿（`activeTake` 存在但 hydrate 失败）时显示，正常录制不会触发 |
| 单路 `list_sessions` 自愈引入与双路相同的「修复一半」问题 | 同步调用 `finalize_capture_take`，在同一个方法内完成 session JSON + CaptureTake 的双写 |
