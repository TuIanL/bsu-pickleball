## ADDED Requirements

### Requirement: 双摄协同详情快捷入口

视频分析结果页（`/analysis/:id/vision`）头部 SHALL 在任务为双摄协同（`analysisKind === "multiview"`）且分析完成时提供**查看双摄协同详情**按钮，点击直达 `/analysis/:id/multiview`；导航 SHALL 保留任务列表来源上下文。非双摄协同任务或未完成任务 MUST NOT 展示该入口。

#### Scenario: 双摄协同任务直达协同详情

- **WHEN** 用户在视频分析结果页查看一个已完成的双摄协同任务
- **THEN** 页面头部 SHALL 展示"查看双摄协同详情"按钮
- **AND** 点击 SHALL 直接导航到 `/analysis/:id/multiview`，无需先返回任务管理

#### Scenario: 非双摄任务不展示入口

- **WHEN** 视频分析结果页对应任务不是双摄协同（`analysisKind !== "multiview"`）
- **THEN** 页面 MUST NOT 展示"查看双摄协同详情"按钮

#### Scenario: 未完成任务不展示入口

- **WHEN** 双摄协同任务尚未完成
- **THEN** 页面 MUST NOT 展示"查看双摄协同详情"按钮

#### Scenario: 入口保留来源上下文

- **WHEN** 用户从双摄协同详情页点击返回
- **THEN** 返回目标 SHALL 保持在双摄任务管理上下文中
- **AND** 页面 SHALL 保留任务列表来源与 session 上下文参数
