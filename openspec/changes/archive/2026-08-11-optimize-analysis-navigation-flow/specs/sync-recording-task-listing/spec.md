## ADDED Requirements

### Requirement: 双摄任务操作保留来源上下文

双摄录制卡片中的双摄 Parent 任务、重试、任务详情、报告和录制工作台入口 SHALL 传递 `sync_recording` 来源及可用的 session id，使后续返回操作能够回到双摄任务管理上下文。

#### Scenario: 创建双摄分析后退出

- **WHEN** 用户从双摄录制卡片创建双摄协同分析并在向导中退出
- **THEN** 页面 SHALL 返回分析任务管理的双摄录制 tab
- **AND** SHALL NOT 返回普通视频管理或上传视频任务 tab

#### Scenario: 从双摄任务打开详情

- **WHEN** 用户从双摄录制卡片打开 Parent 任务详情或分析结果
- **THEN** 详情/结果页 SHALL 保留双摄来源上下文
- **AND** 返回任务管理时 SHALL 恢复双摄录制 tab

#### Scenario: 双摄录制工作台返回

- **WHEN** 用户从双摄任务卡片进入双摄录制工作台并点击返回任务列表
- **THEN** 页面 SHALL 返回双摄录制 tab
- **AND** SHALL 保留当前双摄 session 上下文

