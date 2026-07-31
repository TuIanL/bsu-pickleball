## Why

服务端异常重启（崩溃、断电、停机）后，`recover_orphan_recordings()` 只清理了 FFmpeg 进程、MediaFragment 和 CameraLease，但未将关联的 `CaptureTake` 从 `recording`/`starting` 更新为 `failed`。导致：① `has_active_capture_take()` 持续返回 True，新录制请求被 409 拒绝（最长阻塞 3 小时）；② 侧边栏显示「录制中」但控制台无法停止（session 与 CaptureTake 状态脱节）；③ 双路录制的自愈逻辑仅修复了 session JSON，CaptureTake 仍然僵死，进一步加剧状态不一致。

## What Changes

- **后端** `capture_recovery.py`：启动恢复时，将孤儿 `CaptureTake`（状态为 `starting`/`recording` 且对应 FFmpeg 进程已不存在）终态化为 `failed`
- **后端** `sync_recorder_service.py`：`list_sessions` 自愈更新 session status → `failed` 时，同步终态化关联的 `CaptureTake`
- **后端** `session_service.py`：`list_sessions` 新增与双路对等的自愈逻辑：session JSON 说 `recording` 但内存中无活跃 session → auto-mark `failed` + 终态化 CaptureTake
- **前端** `AppSidebar`：`ActiveRecordingBlock` 当前活跃录制为孤儿（控制台无法操作）时，提供「强制终止」入口，调用 `cancelRecording` / `cancelSyncRecording` 清理
- **前端** `CaptureConsolePage`：hydrate 阶段若 session 已自愈为 `failed` 但 CaptureTake 仍为活跃，自动兜底清理

## Capabilities

### New Capabilities
- `orphan-capture-take-recovery`：服务端启动时扫描并修复所有孤儿 CaptureTake 记录，将其终态化为 failed，消除假「活跃录制」阻塞

### Modified Capabilities
- `capture-take-provisioning`：`CaptureTake` 启动恢复逻辑需补全——确保进程级恢复（recover_orphan_recordings）与 DB 级状态（CaptureTakeStatus）保持一致
- `app-sidebar`：`ActiveRecordingBlock` 需支持「活跃录制为孤儿（无法进入正常控制台停止）」场景的强制终止路径
- `frontend-capture-runtime`：hydrate 阶段需检测孤儿场景（session 已 failed/canceled 但 CaptureTake 未清理），提供兜底清理行为

## Impact

- `backend/app/camera/capture_recovery.py`：新增 CaptureTake 孤儿修复逻辑
- `backend/app/camera/session_service.py`：`list_sessions` 新增自愈分支
- `backend/app/camera/sync_recorder_service.py`：`list_sessions` 自愈分支补全 CaptureTake 同步
- `backend/app/services/capture_take_service.py`：可能需新增 `finalize_orphan_capture_takes()` 工具方法
- `src/hooks/useActiveCaptureTake.ts`：侧边栏 hooks 层（可能需要暴露 forceCancel 回调）
- `src/components/platform/AppSidebar.tsx`：`ActiveRecordingBlock` 组件新增「强制终止」按钮
- `src/hooks/useCaptureRuntime.ts`：hydrate 阶段新增孤儿兜底逻辑
- `src/pages/CaptureConsolePage.tsx`：可能需要感知孤儿状态渲染不同 UI
