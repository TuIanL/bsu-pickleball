## ADDED Requirements

### Requirement: 工程任务控制台入口
分析任务管理能力 SHALL 作为 Engineering Task Console 保留，但从用户一级导航移除，通过工程/开发者模式进入。

#### Scenario: 工程入口可达
- **WHEN** 用户处于工程模式并进入分析任务
- **THEN** 系统 SHALL 呈现完整的 task management 能力（Parent/child 可见、进度、stage、cancel、delete、batch delete、retry、历史任务、失败状态、internal visibility）

#### Scenario: 普通用户默认不可达
- **WHEN** 普通用户在默认导航浏览
- **THEN** 分析任务管理 SHALL 不作为一级入口出现

### Requirement: 用户层消费 LibraryItem 而非后台 Job
单摄/双摄/上传的分析任务 SHALL 通过 LibraryItem 与 LibraryItemWorkspace 呈现，而不要求普通用户直接面对 AnalysisJob。

#### Scenario: 上传任务以素材呈现
- **WHEN** 一个上传任务存在
- **THEN** 用户层 SHALL 以一个 LibraryItem（upload）呈现，其分析状态作为该素材的生命周期
- **AND** 用户不直接首层面对 AnalysisJobRecord

### Requirement: 删除 AnalysisJob 不删除 Library 源资产
Engineering Console 删除 AnalysisJob SHALL 只删除 job 及其 artifacts，不得连带删除 Library source video / RecordingSession；源资产删除为经 LibraryItem 显式触发的独立动作。

#### Scenario: 删除最后的 Job 保留上传源视频
- **WHEN** 用户删除最后一个引用某 upload video 的 AnalysisJob
- **THEN** 系统 SHALL 仅删除该 job 及其产物
- **AND** SHALL NOT 删除 source video，`LibraryItem(upload)` 继续存在

#### Scenario: 录制/双摄资产不受 Job 删除影响
- **WHEN** 用户删除某录制派生的分析任务
- **THEN** 系统 SHALL 仅删除 job 产物
- **AND** RecordingSession / SyncRecordingSession（MediaAsset）SHALL 保留，LibraryItem 卡不消失

## REMOVED Requirements

### Requirement: Analysis task management page
**Reason**: 任务管理从用户一级页面降为 Engineering Task Console；公开的用户路径改由 LibraryItem 承载
**Migration**: 保留全部工程操作（cancel/delete/batch/retry/stage/progress/父子任务）于 Engineering Task Console；Library 卡片的分析状态吞并其用户层呈现

### Requirement: Terminal task bulk cleanup
**Reason**: 归属工程任务控制台能力，用户层主路径改为 LibraryItem 生命周期清理
**Migration**: 该一键清理保留于 Engineering Task Console