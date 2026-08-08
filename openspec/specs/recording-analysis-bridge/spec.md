# recording-analysis-bridge

## Purpose

定义从双摄录制任务进入分析任务时的元数据继承、标定、任务创建和任务归属契约，确保真实录制来源、前端表单和后端分析 API 始终保持一致。
## Requirements
### Requirement: 录制→分析迷你配置面板

`RecordingAnalyzePage` 仍作为单摄分析（工程调试）入口保留：从录制继承只读元数据 + 四角标定 + 创建单摄任务。它 MUST 不再是双摄录制完成后的主流程。

#### Scenario: 单摄入口保留

- **WHEN** 用户通过次级操作选择「仅分析 A 机位」或「仅分析 B 机位」
- **THEN** 系统 SHALL 仍导航到 `/capture/<sessionId>/analyze?cam=<cam_1|cam_2>` 渲染 `RecordingAnalyzePage`
- **AND** 仍按既有契约创建单摄 AnalysisJob

#### Scenario: 双摄主流程改道

- **WHEN** 用户对已完成合并的双摄录制选择主操作
- **THEN** 主操作 SHALL 为「双摄协同分析」并导航到 `/capture/takes/:captureTakeId/analyze`
- **AND** 用户 SHALL 进入 `MultiViewAnalysisSetupPage` 而非单机位页

### Requirement: 分析任务归属录制

系统 MUST 在分析任务创建时记录所属的录制 session ID 与机位 slot，并在前后端任务摘要中同时提供可兼容读取的字段。

#### Scenario: 创建分析任务携带归属

- **WHEN** 分析任务通过录制→分析迷你面板创建
- **THEN** `AnalysisJobCreate` MUST 包含 `recording_session_id` 与 `camera_slot` 字段
- **AND** 后端 MUST 将字段存入任务 metadata 或规范化摘要
- **AND** 前端 `AnalysisJobSummary` SHALL 能读取 `recordingSessionId`、`cameraSlot` 以及旧任务缺失字段的 `undefined` 状态

#### Scenario: 按录制 session 过滤分析任务

- **WHEN** 前端请求 `GET /api/analysis/jobs?recording_session_id=<sid>`
- **THEN** 后端 SHALL 返回所有 `metadata.recording_session_id` 匹配的分析任务摘要

#### Scenario: 录制卡片展示关联分析任务

- **WHEN** 录制任务卡片渲染且存在派生分析任务
- **THEN** 卡片 SHALL 列出关联分析任务的状态与链接
- **AND** 卡片 SHALL 不阻塞于无关联任务的录制

#### Scenario: 历史任务字段缺失仍可展示

- **WHEN** 前端读取不包含录制归属字段的历史分析任务
- **THEN** 任务列表 SHALL 正常渲染文件、状态和时间信息
- **AND** SHALL 隐藏录制来源专属控件而不是抛出运行时异常

### Requirement: 确认启动分析

单摄路径的创建契约 MUST 保持不变（POST `/api/analysis/jobs` 携带 `{ videoId, calibrationId, metadata, recording_session_id, camera_slot }`，成功后跳转 `/analysis/<jobId>`）。双摄路径 MUST 由 `MultiViewAnalysisSetupPage` 一次创建一个 multiview Parent（见 `multiview-analysis-setup-page` 与 `multiview-analysis-orchestration`），并支持在 take 公共时间轴指定分析窗口（`clipStartMs/clipEndMs`，secondary 由后端经 sync 换算）。

#### Scenario: 单摄创建不变

- **WHEN** 用户从 `RecordingAnalyzePage` 确认启动单摄分析
- **THEN** 行为与既有契约一致，导航到 `/analysis/<jobId>`

#### Scenario: 双摄创建唯一 Parent

- **WHEN** 用户从 `MultiViewAnalysisSetupPage` 点击「开始双摄协同分析」
- **THEN** 系统 SHALL 只创建一个 multiview Parent
- **AND** 导航到 `/analysis/<parentId>`

### Requirement: cameraAngle 语义修正

`RecordingAnalyzePage` MUST 修复 `cameraAngle` 错误映射：不得用 `session.match_format`（`singles/doubles`）查询角度表（键为 `baseline_high/sideline/elevated...`），该错误几乎恒落 `unknown`。机位角度 MUST 来自真实机位来源（`camera_slots[camSlot].camera_angle`）。

#### Scenario: 角度来源真实

- **WHEN** 单摄任务创建时设置 `cameraAngle`
- **THEN** 该值 SHALL 来自真实机位来源
- **AND** SHALL NOT 由 `match_format` 查询角度表推导

