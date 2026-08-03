## ADDED Requirements

### Requirement: 录制→分析迷你配置面板

系统 MUST 提供一个从录制 session 到创建分析任务的迷你配置页面，展示继承自录制的只读元数据，并允许为选定机位的视频完成四角标定后直接创建分析任务。

#### Scenario: 从双摄录制卡片打开分析

- **WHEN** 用户在一个已完成合并的双摄录制任务卡片上点击「分析 A 机位」或「分析 B 机位」
- **THEN** 系统 SHALL 导航到 `/capture/<sessionId>/analyze?cam=<cam_1|cam_2>`
- **AND** 系统 SHALL 渲染 `RecordingAnalyzePage` 而非 `NewAnalysisPage`

#### Scenario: 只读元数据展示

- **WHEN** `RecordingAnalyzePage` 加载完成
- **THEN** 页面顶部 SHALL 以只读 banner 展示从录制 session 继承的元数据：场地名称、比赛时间、帧率、比赛形式、相机角度、选定机位
- **AND** banner SHALL NOT 包含任何可编辑表单控件

#### Scenario: 四角标定

- **WHEN** 页面加载完毕且视频流就绪
- **THEN** 系统 SHALL 渲染共享组件 `<CourtCornerCalibrator />` 用于标定球场四个角点
- **AND** 标定组件 SHALL 提供「自动识别」与「手动点选」两种方式
- **AND** 标定完成后 MUST 产出 calibrationId

#### Scenario: 确认启动分析

- **WHEN** 用户已完成标定并点击「确认并启动分析」
- **THEN** 系统 SHALL 使用录制 session 的元数据快照构建 `AnalysisUploadMetadata`
- **AND** 系统 SHALL POST `/api/analysis/jobs` 携带 `{ videoId, calibrationId, metadata, recording_session_id, camera_slot }`
- **AND** 成功后 SHALL 跳转到 `/analysis/<jobId>`

#### Scenario: 标定未完成时按钮禁用

- **WHEN** 标定状态不为完成
- **THEN** 「确认并启动分析」按钮 SHALL 处于禁用状态

### Requirement: 分析任务归属录制

系统 MUST 在分析任务创建时记录所属的录制 session ID 与机位 slot，并在分析任务查询接口中支持按录制 session 过滤。

#### Scenario: 创建分析任务携带归属

- **WHEN** 分析任务通过录制→分析迷你面板创建
- **THEN** `AnalysisJobCreate` MUST 包含 `recording_session_id` 与 `camera_slot` 字段
- **AND** 后端 MUST 将这些字段存入任务元数据

#### Scenario: 按录制 session 过滤分析任务

- **WHEN** 前端请求 `GET /api/analysis/jobs?recording_session_id=<sid>`
- **THEN** 后端 SHALL 返回所有 `metadata.recording_session_id` 匹配的分析任务摘要

#### Scenario: 录制卡片展示关联分析任务

- **WHEN** 录制任务卡片渲染且存在派生分析任务
- **THEN** 卡片 SHALL 列出关联分析任务的状态与链接
- **AND** 卡片 SHALL 不阻塞于无关联任务的录制

## MODIFIED Requirements

（无——`recording-analysis-bridge` 为全新 capability，不修改现有 spec）

## REMOVED Requirements

（无）
