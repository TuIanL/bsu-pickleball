## Why

单摄现场录制时无法看到盘/局/分实时时间线和事件标注，结束录制时每次都需要手动点击"重试恢复"才能完成。这两个问题让单摄录制基本不可用。

## What Changes

### 修复单摄停止路由缺少的导入

`routes_recording.py` 的 stop 端点在组装 `CaptureStopResult` 时调用 `get_session_factory`，但从未导入该函数，导致每次停止都返回 HTTP 500。双摄路由 `routes_sync_recording.py` 有正确的导入，两处不一致。

### 接入真实 MiniTimeline

`CaptureConsolePage` 当前只用时间戳胶囊占位，未导入真正的 `MiniTimeline` 组件。替换为完整的三层时间线（盘/局/分），显示开放片段、非比赛区间、换边标记和实时播放头。

### 修复 Live Coding 数据流

`useLiveCoding` 两处 `listTimelineEvents` 调用参数错误（对象被转换为 `[object Object]`），且 `addTimelineEvent` 同时走 Outbox 和直接 `createTimelineEvent` 存在双写入风险。统一为 Outbox → coding-actions 单一权威入口。

### 加固前端停止恢复

停止异常进入 `recovering` 后自动查询服务器状态，不再强制用户手动点击。同时修复 `operationError` 显示、`RECOVERED` 状态映射、恢复结果丢失 `tracks`/`videoId`/`analysisAvailable` 的问题。

## Capabilities

### New Capabilities

- （无新增能力，均为回归修复）

### Modified Capabilities

- `recording-session-control`: 单摄停止路由必须返回完整 `CaptureStopResult`，不得在媒体已停止后因响应组装错误返回 500
- `frontend-capture-runtime`: 停止结果未知时自动恢复；查询失败不立即判定录制失败；恢复后保留完整媒体和分析入口
- `live-coding-console`: 前端时间线从占位实现替换为真实 MiniTimeline 组件；Outbox 成为事件写入唯一入口
- `session-timeline-events`: `listTimelineEvents` 调用参数修复；合并重复加载

## Impact

| 范围 | 内容 |
|------|------|
| `backend/app/api/routes_recording.py` | 增加 `get_session_factory` 导入 |
| `backend/app/api/routes_recording.py` | 停止路由返回完整 `CaptureStopResult`（含 capture_take, tracks, analysis_available） |
| `src/services/captureAdapter.ts` | 新增 `normalizeRecoveredSingleResult` / `normalizeRecoveredDualResult` |
| `src/pages/CaptureConsolePage.tsx` | 替换 MiniTimeline 占位为组件实现；新建 MiniTimeline 导入 |
| `src/hooks/useLiveCoding.ts` | 修复 `listTimelineEvents` 调用参数；删除双写路径；合并重复 Timeline 加载 |
| `src/hooks/useCaptureRuntime.ts` | 自动恢复机制；恢复控制元数据（次数/飞行中/定时器）；`operationError` 显示；状态映射；联合 Source Session + CaptureTake 恢复完整结果 |
