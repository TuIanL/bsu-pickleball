## MODIFIED Requirements

### Requirement: 采集任务与录制的关系

系统 SHALL 将 Field Session 作为顶层容器，Recording 是其下的视频采集活动。停止录制后返回统一的 `CaptureStopResult`，前端通过此结构判断分析可用性。

#### Scenario: 创建录制关联采集任务

- **WHEN** 用户在采集控制台中开始录制
- **THEN** 系统调用 `startRecording` 或 `startSyncRecording` API 并传入当前 `field_session_id`
- **AND** Recording 的 `auto_analyze_after_stop` 根据向导中的 `analysisIntent` 设置

#### Scenario: 停止录制返回统一结果

- **WHEN** 用户在采集控制台中停止录制
- **THEN** 系统调用 `stopRecording` 或 `stopSyncRecording` API
- **AND** 两者均返回 `CaptureStopResult`（统一 schema）
- **AND** 前端从 `CaptureStopResult` 读取 tracks、analysis_available、warnings
- **AND** 前端不再需要 `isDualMode ? dualStopResponse : completedRecording` 分支

### Requirement: 双摄录制完成面板

系统 SHALL 在双摄同步录制停止后展示双摄录制完成面板，使用统一的 `CaptureStopResult` 数据结构。

#### Scenario: 双摄录制正常完成

- **WHEN** 用户停止双摄同步录制且会话状态为 completed
- **THEN** 系统从 `CaptureStopResult.tracks` 展示两路摄像头的保存摘要
- **AND** 系统展示录制时长、分段数量和输出状态
- **AND** 若 tracks 中存在 status=completed 的 track，系统提供创建分析任务入口
- **AND** 系统通过 `analysis_available` 和 `analysis_blocked_reason` 判断分析入口状态
- **AND** 系统提供继续采集入口

#### Scenario: 双摄录制完成但分析入口不可用

- **WHEN** 双摄录制完成但 `analysis_available` 为 false
- **THEN** 系统展示录制已保存
- **AND** 系统展示 `analysis_blocked_reason` 说明不可用原因
- **AND** 系统不得跳转到失效的分析创建流程

### Requirement: 采集控制台内录制状态机

系统 SHALL 在采集控制台内部用「preview → recording → stopped」三状态驱动 UI。停止录制后 `capturePhase` 和 `outboxHealth` 为正交状态，Outbox 未同步不阻塞媒体完成。

#### Scenario: 录制停止状态

- **WHEN** 控制台处于 stopped 状态
- **THEN** 系统展示录制完成面板（覆盖在预览区上或作为独立区块）
- **AND** `capturePhase` MAY 为 `"completed"` 同时 `outboxHealth` MAY 为 `"pending"`
- **AND** 面板展示未同步事件数量提示（如果有）
- **AND** 用户操作后面板可关闭，状态回到 preview

## ADDED Requirements

### Requirement: Outbox 同步与媒体完成正交

系统 SHALL 将录制停止后的 capturePhase 和 outboxHealth 作为两个独立的正交状态维度，允许在媒体已完成但事件未同步时正常展示完成面板。

#### Scenario: 媒体完成 + Outbox 未同步

- **WHEN** 录制停止完成但 Outbox 有未同步事件
- **THEN** capturePhase MUST 为 `completed`
- **AND** outboxHealth MUST 为 `pending`（显示待同步事件数量）
- **AND** 完成面板 MUST 正常展示（不被 Outbox 阻塞）
- **AND** 面板 MUST 提示「有 N 条现场标记待同步」

#### Scenario: 媒体完成 + Outbox 已同步

- **WHEN** 录制停止完成且 Outbox drain 全部成功
- **THEN** capturePhase MUST 为 `completed`
- **AND** outboxHealth MUST 为 `synced`
- **AND** 面板 MUST 不显示同步相关提示
