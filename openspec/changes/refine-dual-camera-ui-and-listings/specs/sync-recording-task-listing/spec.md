## ADDED Requirements

### Requirement: 双摄录制任务列表

系统 SHALL 在 `/tasks` 页面提供「双摄录制」Tab，展示已完成的双摄同步录制会话。

#### Scenario: 进入双摄录制 Tab
- **WHEN** 用户点击「双摄录制」Tab
- **THEN** 系统调用 `listSyncRecordings()` API 获取所有双摄录制会话
- **AND** 系统按 Field Session 分组展示会话
- **AND** 每条会话展示底线机位 A/B 视频信息、录制时长、分段数、重启次数和状态

#### Scenario: 双摄录制列表为空
- **WHEN** 系统中没有双摄录制会话
- **THEN** 系统展示空状态提示，引导用户前往采集控制台创建双摄录制

#### Scenario: 点击双摄录制卡片
- **WHEN** 用户点击某个双摄录制会话卡片
- **THEN** 系统导航到对应的 Field Session 采集控制台（`/capture/:id`）

### Requirement: 双摄录制卡片

系统 SHALL 用 `SyncRecordingTaskCard` 组件渲染每条双摄录制会话，全文不使用"主机位/副机位"称谓。

#### Scenario: 展示录制摘要
- **WHEN** 系统渲染一条双摄录制会话卡片
- **THEN** 卡片展示底线机位 A 视频和底线机位 B 视频信息
- **AND** 卡片展示录制时长、分段数量和总重启次数
- **AND** 卡片展示状态标签（completed / failed / canceled）

#### Scenario: 展示默认分析入口
- **WHEN** 双摄录制会话的 `default_analysis_video_id` 存在
- **THEN** 卡片提供「创建分析任务」入口
- **AND** 点击后跳转到分析创建页面

#### Scenario: 分析不可用
- **WHEN** 双摄录制会话的 `default_analysis_video_id` 为空且状态为 completed
- **THEN** 卡片展示「分析不可用」提示及原因
