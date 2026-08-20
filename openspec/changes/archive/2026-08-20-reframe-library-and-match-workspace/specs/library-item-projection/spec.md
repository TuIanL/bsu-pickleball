## ADDED Requirements

### Requirement: 统一 LibraryItem 投影

系统 SHALL 将 upload / recording / sync_recording 三类来源投影为统一的 `LibraryItemViewModel`，作为用户层主对象，暴露统一身份、三轴生命周期状态（media × availability × analysis）与展示元数据。

#### Scenario: 三类来源统一被投影为 LibraryItem
- **WHEN** 前端存在一个 upload video、一个 RecordingSession、一个 SyncRecordingSession
- **THEN** 三类数据均 SHALL 投影为 `LibraryItemViewModel`，且携带各自的 `LibraryItemRef`（kind + sourceId）

#### Scenario: 展示元数据
- **WHEN** 渲染某个 LibraryItem
- **THEN** 系统 SHALL 提供 title、thumbnailUrl、previewUrl、sourceType、matchFormat、cameraSetup、startedAt、durationSec、venue、courtName 等字段（缺失时隐藏对应展示而非伪造）

### Requirement: LibraryItem identity 与 AnalysisJob identity 分离

LibraryItem 的稳定身份（`LibraryItemRef`）SHALL 与 AnalysisJob 解耦；AnalysisJob 的存在与变化不得改变 LibraryItem 的 URL 或主卡身份。

#### Scenario: 重跑分析不改变 LibraryItem 身份
- **WHEN** 同一 SyncRecordingSession 下先后创建 Parent Job #1、#2
- **THEN** 前端仍只显示 `sync_recording:sr-123` 一张卡，URL `/library/sync/sr-123?view=analysis` 不失效
- **AND** `primaryAnalysisJobId` 跟随 D9 契约变化，但 `LibraryItemRef` 不变

#### Scenario: 双摄分析的子 job 不单独生成主卡
- **WHEN** 一个同步录制产生 Parent Job 与 A/B 单摄 child job
- **THEN** 用户层只呈现该录制对应的单一稳定卡片，child job 不产生额外 Library 主卡

### Requirement: Upload 拥有独立资产生命周期

Upload LibraryItem 的资产身份（`videoId`）SHALL 独立于任一 AnalysisJob 存在；删除 AnalysisJob MUST NOT 摧毁 Library source video，删除源视频 SHALL 为经 LibraryItem 显式触发的独立动作。

#### Scenario: 只读 video catalog 可枚举上传资产
- **WHEN** 前端需要列出所有独立上传视频
- **THEN** 系统 SHALL 通过只读 `GET /api/videos` 枚举现有 VideoMetadata，而非依赖 `listAnalysisJobs()` 反推

#### Scenario: 删除 Job 不删除源视频
- **WHEN** 用户在 Engineering Console 删除最后一个引用某 upload video 的 AnalysisJob
- **THEN** 系统 SHALL 仅删除该 job 及其 artifacts
- **AND** SHALL NOT 连带删除 source video，LibraryItem(upload) 继续存在

#### Scenario: 删除源视频为独立动作
- **WHEN** 用户删除 Library 中的源视频
- **THEN** 系统 SHALL 显式执行删除，并对该视频关联的 AnalysisJob 另行处理（如提示/级联分析产物）

### Requirement: 三轴生命周期状态

LibraryItem SHALL 使用正交的媒体生命周期（mediaState）、可访问性（availabilityState）与分析生命周期（analysisState），而非单一合并状态。

#### Scenario: 状态派生
- **WHEN** mediaState 为 `ready` 且 analysisState 为 `running`
- **THEN** UI 显示「正在分析 62%」

#### Scenario: 录制中
- **WHEN** mediaState 为 `recording`
- **THEN** UI 显示「正在录制」

#### Scenario: 分析完成/失败
- **WHEN** mediaState 为 `ready` 且 analysisState 为 `succeeded`
- **THEN** UI 显示「分析完成」
- **WHEN** analysisState 为 `failed`
- **THEN** UI 显示「分析失败」

#### Scenario: 存储暂不可用不等同于失败
- **WHEN** mediaState 为 `ready`、analysisState 为 `succeeded` 且 availabilityState 为 `unavailable`（如外置存储掉线）
- **THEN** UI SHALL 显示「分析完成 · 视频存储暂不可用」
- **AND** SHALL NOT 将 mediaState 解释为 `failed`

### Requirement: source-specific 状态映射与 requiredAction

LibraryItemAdapter SHALL 以显式的 source-specific 映射表将各来源源状态转换为 ViewModel 三轴状态与 `requiredAction`，不得简单合并为单一 mediaState。

#### Scenario: sync merge pending 映射为需合并动作
- **WHEN** SyncRecordingSession 的 merge_status 为 `pending`
- **THEN** Adapter SHALL 映射为 mediaState=processing + `requiredAction=merge_required`
- **AND** UI SHALL 提供「合并视频」操作，而非仅显示「处理中」

#### Scenario: sync merge running
- **WHEN** merge_status 为 `running`
- **THEN** Adapter SHALL 映射为 mediaState=processing + `requiredAction=none`

### Requirement: Primary Analysis Selection

LibraryItem 的 `primaryAnalysisJobId` SHALL 由显式契约决定，`latestPublicAnalysisJobId` 不作为正确语义；internal child 与 A/B 工程单摄 MUST NOT 成为 primary 结果。

#### Scenario: 双摄 primary 取 multiview Parent
- **WHEN** 一个 sync_recording 会话同时存在 multiview Parent 与 A/B public single-view job
- **THEN** `primaryAnalysisJobId` SHALL 选取该会话最新 public `analysisKind=multiview` Parent
- **AND** A/B public single-view SHALL NOT 成为 primary

#### Scenario: recording/upload primary 取单摄
- **WHEN** 素材为 recording 或 upload
- **THEN** `primaryAnalysisJobId` SHALL 选取匹配 sourceId（recordingSessionId==sourceId 或 videoId==sourceId）的最新 public single-view 任务

#### Scenario: analysisHistoryCount
- **WHEN** ViewModel 渲染
- **THEN** 系统 SHALL 提供 `analysisHistoryCount` 以展示历史分析数量