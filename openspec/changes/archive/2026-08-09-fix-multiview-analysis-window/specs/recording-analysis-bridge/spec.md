## MODIFIED Requirements

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
