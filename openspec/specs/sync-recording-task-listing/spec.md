# sync-recording-task-listing Specification

## Purpose
TBD - created by syncing change refine-dual-camera-ui-and-listings.
## Requirements
### Requirement: 双摄录制任务列表

系统 SHALL 在规范入口 `/analysis/tasks` 的「双摄录制」Tab 展示所有双摄同步录制会话及其持久化的视频合并状态，并通过 `/tasks` 兼容别名提供相同页面。

#### Scenario: 进入双摄录制 Tab

- **WHEN** 用户在 `/analysis/tasks` 或 `/tasks` 点击「双摄录制」Tab
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

#### Scenario: 旧任务链接保持兼容

- **WHEN** 用户通过历史 `/tasks` 链接进入任务列表
- **THEN** 系统 SHALL 渲染与 `/analysis/tasks` 相同的任务页和 Tab
- **AND** 页面内新生成的任务列表链接 SHALL 优先使用 `/analysis/tasks`

### Requirement: 双摄录制卡片

系统 SHALL 用 `SyncRecordingTaskCard` 组件渲染每条双摄录制会话，全文不使用“主机位/副机位”称谓。卡片 SHALL 将录制资产状态与分析任务状态分区展示；分析任务 SHALL 按双摄协同 Parent、A 机位单摄、B 机位单摄分组，并对每组展示最新任务与可展开的历史任务。

#### Scenario: 展示录制摘要

- **WHEN** 系统渲染一条双摄录制会话卡片
- **THEN** 卡片展示底线机位 A 视频和底线机位 B 视频信息
- **AND** 卡片展示录制时长、分段数量和总重启次数
- **AND** 每条会话展示状态标签（completed / failed / canceled）
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
- **AND** 点击后跳转到录制分析桥接页面或已有分析详情页面

#### Scenario: 分析不可用

- **WHEN** 双摄录制会话尚未完成两路合并
- **THEN** 卡片展示待合并或失败原因
- **AND** 卡片 MUST 不展示可播放视频和分析入口

#### Scenario: 分析任务按类型分区

- **WHEN** 双摄录制会话存在公开分析任务
- **THEN** 卡片 SHALL 分别展示双摄协同、A 机位和 B 机位任务区域
- **AND** 每个区域 SHALL 默认展示最近更新任务
- **AND** internal child SHALL NOT 作为独立任务区域展示

#### Scenario: 历史任务可展开

- **WHEN** 任一任务区域存在多个公开任务
- **THEN** 卡片 SHALL 展示历史任务数量和展开控制
- **AND** 展开后 SHALL 显示每个历史任务的状态、时间和具体操作

#### Scenario: 操作作用于明确任务

- **WHEN** 用户点击某个当前或历史分析任务的操作
- **THEN** 操作 SHALL 使用该任务对应的 job id
- **AND** SHALL 不因同组存在其他任务而作用于错误任务

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

### Requirement: 分析任务分组网格布局

双摄录制会话卡片内的分析任务分组 SHALL 采用网格化布局：**A 机位分析** 与 **B 机位分析** 并排于同一行，**双摄协同分析** 单独占据一行；当存在其他分析任务分组时 SHALL 保持尾部全宽展示。各组的最新任务、历史任务展开与任务操作行为 MUST NOT 因布局变化而改变。

#### Scenario: A/B 机位分析并排

- **WHEN** 双摄录制会话存在 A 机位与 B 机位分析任务分组
- **THEN** 页面 SHALL 将两个分组卡片并排渲染在同一行
- **AND** 每个分组 SHALL 保持独立的标题、任务数徽标、历史展开与操作按钮

#### Scenario: 双摄协同分析独占一行

- **WHEN** 双摄录制会话存在双摄协同分析任务分组
- **THEN** 页面 SHALL 将该分组单独渲染为一行全宽卡片
- **AND** 该分组 MUST NOT 与 A/B 机位分组并排

#### Scenario: 窄屏回退为纵向堆叠

- **WHEN** 视口宽度不足以容纳并排的两列任务分组
- **THEN** 页面 SHALL 回退为纵向堆叠展示
- **AND** 各分组 SHALL 保持完整功能

#### Scenario: 其他分析任务保留尾部

- **WHEN** 存在无法可靠映射到 A/B 机位的历史公开任务分组
- **THEN** 该分组 SHALL 渲染在网格布局之后的全宽行

