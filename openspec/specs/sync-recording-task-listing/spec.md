# sync-recording-task-listing Specification

## Purpose
TBD - created by syncing change refine-dual-camera-ui-and-listings.

## Requirements
### Requirement: 双摄录制任务列表

系统 SHALL 在 `/tasks` 页面提供「双摄录制」Tab，展示所有双摄同步录制会话及其持久化的视频合并状态。

#### Scenario: 进入双摄录制 Tab
- **WHEN** 用户点击「双摄录制」Tab
- **THEN** 系统调用 `listSyncRecordings()` API 获取所有双摄录制会话
- **AND** 系统按 Field Session 分组展示会话
- **AND** 每条会话展示底线机位 A/B 视频信息、录制时长、分段数、重启次数和状态
- **AND** 每条会话展示待合并、合并中、已完成或失败的合并状态

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
- **AND** 每条会话展示待合并、合并中、已完成或失败的合并状态

#### Scenario: 待合并任务展示合并按钮

- **WHEN** 双摄任务已停止且合并状态为待合并或失败
- **THEN** 卡片 MUST 展示“合并视频”或“重新合并”按钮
- **AND** 点击按钮 MUST 提交该任务的双路合并操作

#### Scenario: 合并中禁止重复提交

- **WHEN** 双摄任务合并状态为合并中
- **THEN** 卡片 MUST 展示处理中状态
- **AND** 合并按钮 MUST 禁止重复提交
- **AND** 卡片 MUST 不提供播放或分析入口

#### Scenario: 展示默认分析入口
- **WHEN** 双摄录制会话的两路合并均成功且 `default_analysis_video_id` 存在
- **THEN** 卡片提供创建分析任务入口
- **AND** 点击后跳转到分析创建页面

#### Scenario: 分析不可用
- **WHEN** 双摄录制会话尚未完成两路合并
- **THEN** 卡片展示待合并或失败原因
- **AND** 卡片 MUST 不展示可播放视频和分析入口
