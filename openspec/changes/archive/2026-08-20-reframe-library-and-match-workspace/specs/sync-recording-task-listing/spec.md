## ADDED Requirements

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

## REMOVED Requirements

### Requirement: 双摄录制任务列表
**Reason**: 双摄录制收敛为 LibraryItem 生命周期，不再作为 `/analysis/tasks` 下独立「双摄录制」Tab 的一等页面对象
**Migration**: 双摄会话以单一 LibraryItem 卡片呈现在比赛库；合并与分析状态在卡片生命周期内展示；`/analysis/tasks` 仅作为兼容别名保留