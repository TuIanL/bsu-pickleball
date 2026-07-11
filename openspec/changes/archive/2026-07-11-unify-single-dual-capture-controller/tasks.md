## 0. 页面行为保护测试（现有组件级契约）

- [x] 0.1 新增 `CaptureConsolePage` 组件测试：单摄选择相机 → start → recording → Live Coding 初始化 → stop → 完成面板
- [x] 0.2 新增组件测试：双摄选择 slots → 短录测试 → start → stop → 完成面板
- [x] 0.3 新增组件测试：Outbox 停止行为——点击停止 → freeze 立即发生 → stop API 不等 flush → pending 提示保留
- [x] 0.4 新增组件测试：stop API 网络错误 → recovering → 查询 session 最终状态
- [x] 0.5 新增组件测试：完成面板——自动分析入口不消失 / 参数保留 sessionId/fps/videoId
- [x] 0.6 记录基线：`npm run build` + `npm run test`

## 1. 统一类型与 Normalizer

- [x] 1.1 新增 `src/types/capture.ts`：`UnifiedCaptureSession`、`CaptureTrackRuntime`、`NormalizedCaptureStopResult`、`CaptureStartIntent`、`CaptureRuntimeState`、`CaptureMode`
- [x] 1.2 `CaptureTrackRuntime.trackId` 可选（启动时不可得，停止后从 result.tracks 补充）
- [x] 1.3 `NormalizedCaptureStopResult.captureTakeId` 必填
- [x] 1.4 `CaptureRuntimeState` discriminated union：idle / starting / recording / stopping / recovering / completed / partial / failed / canceled
- [x] 1.5 `CaptureStartIntent` discriminated union：`{ mode: "single", cameraId, fps, autoAnalyze }` | `{ mode: "dual", slots, fps, autoAnalyze }`
- [x] 1.6 新增 `src/services/captureAdapter.ts`：`adaptRecordingSession()` + `adaptSyncRecordingSession()`，started_at 缺失抛 invariant error
- [x] 1.7 新增 `NormalizedCaptureStopResult` Normalizer：capture_take 缺失时进入 failed，不静默跳过
- [x] 1.8 测试：adapter 字段完整性、started_at 缺失抛错、dual slots 适配

## 2. 纯 Reducer 实现

- [x] 2.1 新增 `src/hooks/useCaptureRuntime.ts`：内部 reducer 管理 `CaptureRuntimeState`
- [x] 2.2 定义 `RuntimeAction` 联合类型：START / STARTED / START_FAILED / STOP_REQUESTED / STOP_SUCCEEDED / STOP_RESULT_UNKNOWN / RECOVERED / CANCEL_REQUESTED / CANCELED / FAILED / RESET
- [x] 2.3 `STOP_REQUESTED` 在请求发出前 dispatch（不等 API 返回）
- [x] 2.4 测试 reducer 所有合法状态转换（idle→starting→recording→stopping/recovering→completed/partial/failed/canceled）
- [x] 2.5 测试非法转换被拒绝（e.g. idle 直接到 completed）
- [x] 2.6 测试 `STOP_RESULT_UNKNOWN` → recovering → RECOVERED 恢复链

## 3. useCaptureRuntime Hook

- [x] 3.1 实现 `useCaptureRuntime({ fieldSessionId, onFieldSessionStarted })`
- [x] 3.2 `start(intent: CaptureStartIntent)`：先调用 `startFieldSession` → 根据 mode 调用 `startRecording` 或 `startSyncRecording` → dispatch STARTED → UnifiedCaptureSession
- [x] 3.3 `stop()`：调用 stop API → 用 `getRecording/getSyncRecording` 刷新 session → Normalizer → dispatch STOP_SUCCEEDED（completed/partial）
- [x] 3.4 `cancel()`：调用 cancel API → dispatch CANCELED
- [x] 3.5 网络不确定性：stop API 返回前网络断开 → dispatch STOP_RESULT_UNKNOWN → 按 sourceSessionId 查询 → dispatch RECOVERED
- [x] 3.6 `elapsedMs`：250ms clockNow + `Date.parse(session.startedAt)` 派生；停止后从 `result.capture_take.duration_ms` 读取
- [x] 3.7 录制中 session-specific polling：`getRecording(sourceSessionId)` / `getSyncRecording(sourceSessionId)`，不用全局 `/active`
- [x] 3.8 Runtime 不直接调用 `liveCoding.freeze()` 或 `liveCoding.flushWithDeadline()`
- [x] 3.9 返回 `{ phase, session, result, elapsedMs, error, start, stop, cancel, reset, captureTakeId }`，其中 `captureTakeId` 是 selector（recording→session.captureTakeId, completed→result.captureTakeId）

## 4. 单摄迁移（阶段 A）

- [x] 4.1 `CaptureConsolePage.tsx` 中单摄路径切换到 `useCaptureRuntime`
- [x] 4.2 单摄 start 使用 `CaptureStartIntent`
- [x] 4.3 单摄 stop 使用页面协调层（freeze → runtime.stop → flushWithDeadline）
- [x] 4.4 单摄完成面板读取 `runtime.result` + `runtime.session`
- [x] 4.5 双摄路径保持旧逻辑不变
- [x] 4.6 确认单摄不更新旧 `consoleState`/`activeRecording`（双真相源隔离）

## 5. 双摄迁移（阶段 B）

- [x] 5.1 双摄路径切换到 `useCaptureRuntime`
- [x] 5.2 删除 `/api/sync-recordings/active` 全局轮询，改用 session-specific polling
- [x] 5.3 删除双摄轮询中伪造空 `CaptureStopResult` 的逻辑
- [x] 5.4 双摄 start 使用 `CaptureStartIntent`（slots 组装）
- [x] 5.5 双摄 stop 使用页面协调层

## 6. 提取协作 Hook

- [x] 6.1 新增 `src/hooks/useCameraSetup.ts`：管理摄像机列表/选择/probeResults/previewTracks/startIntent/isReady（唯一所有者）
- [x] 6.2 新增 `src/hooks/useCapturePreflight.ts`：双摄短录测试，slots 变化时自动 resetPreflight
- [x] 6.3 新增 `src/hooks/useLiveCoding.ts`：接受 `{ fieldSessionId, captureTakeId, phase, elapsedMs }`
- [x] 6.4 `useLiveCoding` captureTakeId 变化时自动初始化（终止旧 sender → 清空 timeline → 获取 live state → 恢复 pending outbox → 创建新 sender → 防串线）
- [x] 6.5 设备抽屉（drawerOpen/drawerTab/newCameraForm）留在页面，不进入任何 Hook

## 7. JSX 统一（阶段 C 前半）

- [x] 7.1 控制栏统一：`<CaptureControls phase onStart onStop canStart />`，无 isDualMode fork
- [x] 7.2 计时器统一：`<CaptureTimer elapsedMs />`
- [x] 7.3 Live Coding 面板统一：不区分单摄/双摄独立渲染
- [x] 7.4 MiniTimeline 统一：不区分单摄/双摄
- [x] 7.5 完成面板统一：`<CaptureCompletePanel result session />`，从 NormalizedCaptureStopResult 读取
- [x] 7.6 错误提示统一：`<CaptureError error onRetry />`
- [x] 7.7 预览区统一：`<CapturePreviewGrid tracks />`，grid 根据 tracks.length 自适应
- [x] 7.8 保留 mode fork 仅限：摄像机选择方式、双摄测试按钮

## 8. 删除旧代码（阶段 C 后半）

- [x] 8.1 删除 `consoleState`、`dualState` 及其类型
- [x] 8.2 删除 `elapsedSec`、`dualElapsedSec` 及独立定时器
- [x] 8.3 删除 `activeRecording`、`activeSyncSession`
- [x] 8.4 删除 `completedRecording`、`dualStopResponse`
- [x] 8.5 删除 `handleStartRecording`、`handleDualStartRecording`
- [x] 8.6 删除 `handleStopRecording`、`handleDualStopRecording`、`performStopRecording`
- [x] 8.7 `isDualMode` 不再用于公共流程 fork
- [x] 8.8 验收：不存在双状态机、双 active session、双计时器、两套 start/stop handler

## 9. 构建与验证

- [x] 9.1 运行 `npm run test`：reducer + adapter + 行为保护 + 现有测试全部通过
- [x] 9.2 运行 `npm run build`：TypeScript 编译通过
- [x] 9.3 单摄 → 双摄完整流程手动验证
- [x] 9.4 确认 `isDualMode` 不出现在控制栏/计时器/Live Coding/完成面板 JSX
- [x] 9.5 确认完成面板可访问 `auto_analysis_job_id`、`fps`、`session_id`
