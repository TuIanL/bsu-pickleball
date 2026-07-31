## ADDED Requirements

### Requirement: Hydration 孤儿检测与兜底清理

`useCaptureRuntime.hydrate()` 过程中，若通过 `listRecordings` / `listSyncRecordings` 发现 session 已为终态（`failed`/`canceled`/`completed`）但 `GET /api/capture-takes/active` 仍返回活跃记录（CaptureTake 未清理），MUST 提供兜底清理行为。

#### Scenario: session 已自愈为 failed 但 CaptureTake 未清理

- **WHEN** hydrate 调用 `listRecordings({ status: "recording" })` 返回空
- **AND** `listRecordings({ status: "failed" })` 返回该 fieldSessionId 下的 session（表明 session 已被自愈为 failed）
- **BUT** `GET /api/capture-takes/active` 仍返回该录制为活跃
- **THEN** hook SHALL 暴露 `isOrphan: true` 标志
- **AND** runtime phase SHALL 设为 `idle`（不进入 recording 状态）
- **AND** 调用方 MAY 展示「检测到僵尸录制」提示和终止按钮

#### Scenario: session 正常活跃无需兜底

- **WHEN** hydrate 调用 `listRecordings({ status: "recording" })` 找到活跃 session
- **AND** session 有有效的 `capture_take_id`
- **THEN** runtime phase MUST 进入 `recording`
- **AND** `isOrphan` MUST 为 false
