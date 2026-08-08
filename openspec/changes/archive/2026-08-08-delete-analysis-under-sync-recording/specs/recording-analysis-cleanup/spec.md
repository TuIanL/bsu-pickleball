# recording-analysis-cleanup Specification

## Purpose

定义「删除双摄录制下分析任务」的能力：按录制会话定位该录制派生的所有分析任务（multiview Parent + internal child + 单摄任务），级联清理分析产物与融合产物，完整清除本地磁盘，同时严格保留录制本身（session、双路视频、CaptureTake、同步校准）。

## ADDED Requirements

### Requirement: 按录制会话删除分析任务

后端 SHALL 提供按录制会话删除分析任务的入口 `DELETE /api/sync-recordings/{session_id}/analysis`，查找该录制派生的所有分析任务并逐个删除，返回每个任务的删除结果；录制本身 MUST NOT 被删除。

#### Scenario: 按录制会话删除

- **WHEN** 用户请求删除 `session_id` 对应的录制下所有分析任务
- **THEN** 后端 SHALL 找到所有归属该录制的分析任务
- **AND** 对每个任务 SHALL 执行删除并返回 `AnalysisDeleteResult[]`

#### Scenario: 任务归属匹配规则

- **WHEN** 后端查找该录制的分析任务
- **THEN** 匹配规则 SHALL 命中 `metadata.recording_session_id == session_id` 或 `recordingSessionId == session_id` 的任务
- **AND** SHALL 额外命中 `metadata.capture_take_id == session.capture_take_id` 的任务（即使 session id 缺失也能按 take 归属）

#### Scenario: multiview Parent 级联删除

- **WHEN** 该录制派生任务中包含 multiview Parent
- **THEN** 删除 Parent SHALL 级联删除其 internal child 的分析产物与 fusion run 产物
- **AND** internal child SHALL NOT 被单独重复删除

#### Scenario: 录制本身保留

- **WHEN** 删除该录制的分析任务成功
- **THEN** 录制会话 JSON、双路视频资产、CaptureTake 与 `sync_calibration.json` SHALL 全部保留
- **AND** 录制卡片 SHALL 仍出现在「双摄录制」Tab

### Requirement: 活跃分析任务删除被阻断

按录制删除分析任务时，对处于处理中状态（`queued` / `uploaded` / `running` 等）的任务 SHALL 返回 `blocked`，不得删除其任何文件。

#### Scenario: 录制下有活跃任务

- **WHEN** 该录制派生任务中存在处理中状态的 multiview Parent 或单摄任务
- **THEN** 该任务的删除结果 SHALL 为 `blocked`
- **AND** 该任务的所有本地文件 SHALL 保持原样
- **AND** 其余可删除任务 SHALL 照常删除

### Requirement: 删除结果反馈

删除端点 SHALL 返回每个任务的独立结果，使前端能区分「已删除 / 被阻断 / 未找到 / 失败」。

#### Scenario: 混合结果

- **WHEN** 一次录制级删除同时包含已删除与被阻断的任务
- **THEN** 返回结果 SHALL 逐任务标注 `status`（`deleted` / `blocked` / `not_found` / `failed`）
- **AND** 前端 SHALL 据此报告哪些已删、哪些需处理
