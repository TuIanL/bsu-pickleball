# recording-analysis-bridge

## Purpose

定义从双摄录制任务进入分析任务时的元数据继承、标定、任务创建和任务归属契约，确保真实录制来源、前端表单和后端分析 API 始终保持一致。
## Requirements
### Requirement: 录制→分析迷你配置面板

系统 MUST 提供一个从录制 session 到创建分析任务的迷你配置页面，展示继承自录制的只读元数据，并允许为选定机位的视频完成四角标定后直接创建分析任务。页面使用共享的 `AnalysisUploadMetadata` 类型构建请求，不得在页面内重复定义不完整 metadata。

#### Scenario: 从双摄录制卡片打开分析

- **WHEN** 用户在一个已完成合并的双摄录制任务卡片上点击「分析 A 机位」或「分析 B 机位」
- **THEN** 系统 SHALL 导航到 `/capture/<sessionId>/analyze?cam=<cam_1|cam_2>`
- **AND** 系统 SHALL 渲染 `RecordingAnalyzePage` 而非 `NewAnalysisPage`

#### Scenario: 只读元数据展示

- **WHEN** `RecordingAnalyzePage` 加载完成
- **THEN** 页面顶部 SHALL 以只读 banner 展示场地名称、比赛时间、帧率、比赛形式、相机角度和选定机位
- **AND** banner SHALL NOT 包含任何可编辑表单控件

#### Scenario: 四角标定

- **WHEN** 页面加载完毕且视频流就绪
- **THEN** 系统 SHALL 渲染共享组件 `<CourtCornerCalibrator />` 用于标定球场四个角点
- **AND** 标定组件 SHALL 提供「自动识别」与「手动点选」两种方式
- **AND** 标定完成后 MUST 产出 `calibrationId`

#### Scenario: 确认启动分析

- **WHEN** 用户已完成标定并点击「确认并启动分析」
- **THEN** 系统 SHALL 使用录制 session 的元数据快照构建 `AnalysisUploadMetadata`
- **AND** 系统 SHALL POST `/api/analysis/jobs` 携带 `{ videoId, calibrationId, metadata, recording_session_id, camera_slot }`
- **AND** 成功后 SHALL 跳转到 `/analysis/<jobId>`

#### Scenario: 标定未完成时按钮禁用

- **WHEN** 标定状态不为完成
- **THEN** 「确认并启动分析」按钮 SHALL 处于禁用状态

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
