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

单摄路径的创建契约 MUST 保持不变（POST `/api/analysis/jobs` 携带 `{ videoId, calibrationId, metadata, recording_session_id, camera_slot }`，成功后跳转 `/analysis/<jobId>`）。双摄路径 MUST 由 `MultiViewAnalysisSetupPage` 一次创建一个 multiview Parent，并支持在 take 公共时间轴指定分析窗口（`clipStartMs/clipEndMs`，secondary 由后端经 sync 换算）。该窗口 MUST 端到端影响实际跟踪、融合、指标和分析叠加视频，而不仅是保存在请求或任务摘要中。

#### Scenario: 单摄创建不变

- **WHEN** 用户从 `RecordingAnalyzePage` 确认启动单摄分析
- **THEN** 行为与既有契约一致，导航到 `/analysis/<jobId>`

#### Scenario: 双摄创建唯一 Parent

- **WHEN** 用户从 `MultiViewAnalysisSetupPage` 点击「开始双摄协同分析」
- **THEN** 系统 SHALL 只创建一个 multiview Parent
- **AND** 导航到 `/analysis/<parentId>`

#### Scenario: 用户窗口进入请求

- **WHEN** 用户勾选「仅分析指定窗口」并提交合法起止秒数
- **THEN** 前端请求体 SHALL 包含换算后的 `clipStartMs` 与 `clipEndMs`
- **AND** 两个双摄执行视角 SHALL 继承同一个公共物理窗口

#### Scenario: 关闭窗口时保持全场分析

- **WHEN** 用户未勾选指定窗口
- **THEN** 前端 SHALL 省略 clip 字段或发送未启用值
- **AND** 后端 SHALL 按完整 CaptureTake 执行，不得使用旧的残留窗口

#### Scenario: 窗口结果可解释

- **WHEN** 带窗口的双摄任务进入分析详情页
- **THEN** 页面或结果诊断 SHALL 能显示用户请求的时间范围
- **AND** SHALL 能区分请求范围、预热解码范围和源视频总时长

### Requirement: cameraAngle 语义修正

`RecordingAnalyzePage` MUST 修复 `cameraAngle` 错误映射：不得用 `session.match_format`（`singles/doubles`）查询角度表（键为 `baseline_high/sideline/elevated...`），该错误几乎恒落 `unknown`。机位角度 MUST 来自真实机位来源（`camera_slots[camSlot].camera_angle`）。

#### Scenario: 角度来源真实

- **WHEN** 单摄任务创建时设置 `cameraAngle`
- **THEN** 该值 SHALL 来自真实机位来源
- **AND** SHALL NOT 由 `match_format` 查询角度表推导

### Requirement: 录制分析入口区分双摄主流程和单摄工程流程

从双摄录制进入的主分析流程 SHALL 使用双摄任务上下文；A/B 单摄分析入口 SHALL 继续作为次级工程入口，并在返回任务管理时恢复其实际录制来源，不得默认伪装为上传视频任务。

#### Scenario: 双摄创建页退出

- **WHEN** 用户从双摄录制卡片进入 `MultiViewAnalysisSetupPage` 并点击退出
- **THEN** 页面 SHALL 返回双摄任务管理上下文
- **AND** SHALL NOT 返回单摄录制分析页或视频采集页

#### Scenario: 单摄工程入口返回

- **WHEN** 用户通过 A/B 单摄工程入口创建或查看分析任务
- **THEN** 页面 SHALL 保留普通录制来源及 session/camera slot 上下文
- **AND** 返回任务管理时 SHALL 进入录制视频任务视图

#### Scenario: 创建失败重试

- **WHEN** 录制分析创建失败
- **THEN** 页面 SHALL 提供留在当前创建流程重试或返回原录制任务的操作
- **AND** SHALL 不把用户送到无关的上传视频创建页

