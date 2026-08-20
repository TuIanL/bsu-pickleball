# sync-recording-task-listing Specification

## Purpose
TBD - created by syncing change refine-dual-camera-ui-and-listings.
## Requirements
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

### Requirement: SyncRecording 收敛为单一 LibraryItem
双摄录制 SHALL 在用户层收敛为一个 LibraryItem，而非独立的一级 Tab；其合并、分析均作为该 LibraryItem 的生命周期呈现。

#### Scenario: 双摄录制作为库卡片
- **WHEN** 存在某 SyncRecordingSession
- **THEN** 用户层 SHALL 以 `sync_recording:<sourceId>` 单一稳定卡片呈现
- **AND** 内部双摄合并 / A/B / Parent 等细节 SHALL 收入该卡片生命周期或工程层

### Requirement: sync ownership 契约
针对新建 sync recording 分析，`AnalysisJob.recordingSessionId` SHALL 作为 canonical ownership reference；`metadata.capture_take_id` MUST 仅作为 legacy fallback，且不得使用 fileName / video title / timestamp 等模糊匹配。

#### Scenario: 新建 Parent 写入 recordingSessionId
- **WHEN** 从 SyncRecordingSession 创建 public multiview Parent
- **THEN** `Parent.recordingSessionId MUST == SyncRecordingSession.session_id`
- **AND** Library projection SHALL 优先使用 `recordingSessionId`

#### Scenario: 历史任务 fallback
- **WHEN** 历史任务缺失 `recordingSessionId`
- **THEN** Library projection MAY 使用 `metadata.capture_take_id` 作为 fallback 归属
- **AND** SHALL NOT 使用 fileName / video title / timestamp 等模糊匹配

#### Scenario: 无可用归属
- **WHEN** 任务的 recordingSessionId 与 capture_take_id 均无法命中任何 LibraryItem
- **THEN** 任务 SHALL 保留在工程视图或未归属范围，SHALL NOT 被错误挂载到某个 LibraryItem

### Requirement: A/B 单摄分析下沉
对于双摄素材，用户层主结果 SHALL 只认 Multiview Parent；A/B 单摄分析 SHALL 作为工程/技术详情中的次级能力暴露，不成为用户层主入口。

#### Scenario: 用户层只见 Parent 结果
- **WHEN** 双摄素材存在 Parent 与 A/B 单摄 child
- **THEN** 用户层主结果 SHALL 指向 Multiview Parent
- **AND** A/B 单摄分析 SHALL 退到技术详情/工程模式

