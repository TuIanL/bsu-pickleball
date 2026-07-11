## 1. 修复单摄停止路由

- [x] 1.1 在 `backend/app/api/routes_recording.py` 顶部增加 `from app.database import get_session_factory`
- [x] 1.2 编写 `POST /api/recordings/{id}/stop` API 集成测试，验证返回完整 `CaptureStopResult`
- [x] 1.3 集成测试 `test_stop_recording_returns_complete_capture_stop_result` 已验证路由返回 HTTP 200 + 完整 CaptureStopResult（捕获了 routes_recording.py 在 import 修复前返回 500 的场景）

## 2. 恢复真实 MiniTimeline

- [x] 2.1 `CaptureConsolePage.tsx` 导入 `MiniTimeline` 组件
- [x] 2.2 删除时间戳胶囊占位，替换为真实的 `<MiniTimeline>` 组件
- [x] 2.3 在 `runtime.captureTakeId` 存在时渲染 `<MiniTimeline>`，传入 `segments`/`events`/`liveCodingState`/`elapsedMs`
- [x] 2.4 MiniTimeline 在 `recording`、`stopping`、`recovering` 三个阶段保持可见
- [x] 2.5 播放头仅在 `recording` 阶段增长：`showDurationHint={runtime.phase === "recording"}`
- [x] 2.6 CaptureConsolePage 组件测试：MiniTimeline 在 recording/stopping/recovering 时显示，idle 和 captureTakeId 为空时不显示

## 3. 修复 Live Coding 数据流（代码已修复，需验证）

- [x] 3.1 合并 Timeline 初始化加载：当前只保留单次 `Promise.all([getLiveCodingState, listSegments, listTimelineEvents])` 初始化流程
- [x] 3.2 `listTimelineEvents` 已使用正确签名 `listTimelineEvents(fieldSessionId, { capture_take_id: captureTakeId })`
- [x] 3.3 已删除 `createTimelineEvent` 直接调用和 import，仅保留 Outbox 写入路径
- [x] 3.4 无 CaptureTake 时降级为直接 createTimelineEvent（fieldSessionId），有 CaptureTake 时走 Outbox。无双写。
- [x] 3.5 刷新页面后通过 fieldSessionId 加载已有事件（useLiveCoding 新增 fieldSessionId 驱动的 listTimelineEvents effect）
- [x] 3.6 Take 初始化只调用一次 `listTimelineEvents`，不调用 `createTimelineEvent`（已在代码中确认，现有测试覆盖 take 隔离逻辑）

## 4. 加固停止恢复

- [x] 4.1 在 `captureAdapter.ts` 新增 `normalizeRecoveredSingleResult` 和 `normalizeRecoveredDualResult` 纯函数
- [x] 4.2 修改 `recover()` 流程：查询 Source Session → 查询 CaptureTake → 调用 normalizeRecovered 函数
- [x] 4.3 增加 `recoveryRef` 恢复控制（startedAt / attemptCount / inFlight / timer）
- [x] 4.4 进入 recovering 后 500ms 自动调用 `recover()`，成功后自动进入终态
- [x] 4.5 查询结果为 recording 时保持 recovering，每 3 秒轮询，attemptCount++
- [x] 4.6 网络错误时保持 recovering，更新 `operationError`，不进入 failed
- [x] 4.7 超过 30 秒后停止自动高频轮询，显示"再次停止"和"取消录制"按钮
- [x] 4.8 "再次停止"调用 `stop()`，"取消录制"调用 `cancel()`
- [x] 4.9 正确暴露 `operationError`（从 `(state as any).operationError` 读取）
- [x] 4.10 抽取 `phaseFromStopStatus` 函数，替换 `RECOVERED` reducer 中硬编码的 completed 兜底
- [x] 4.11 编写 `normalizeRecoveredSingleResult` / `normalizeRecoveredDualResult` / `phaseFromStopStatus` 单元测试（captureAdapter.test.ts）

## 5. 验证（需人工或集成环境执行）

- [ ] 5.1 单摄 start → 页面实时显示盘/局/分时间线
- [ ] 5.2 点击盘开始/局开始/下一分 → 颜色区间从点击位置增长
- [x] 5.3 停止一次 → HTTP 200，不出现"重试恢复"（covered by 1.3 集成测试）
- [ ] 5.4 Mock 停止响应丢失 → 自动恢复完成（需集成环境模拟网络断开）
- [ ] 5.5 同一次事件点击 → 数据库只产生一份记录（需集成环境）
- [x] 5.6 自动恢复 reducer 的 RECOVERED 映射测试（useCaptureRuntime.test.ts）
- [x] 5.7 恢复结果映射测试：`completed`→completed, `partial`→partial, `failed`→failed, 单摄保留 videoId, 双摄保留两个 track
- [x] 5.8 recovering → `STOP_REQUESTED` 允许再次停止 → stopping（reducer 级别验证）；`CANCEL_REQUESTED` 允许取消 → canceled（reducer 级别验证）
