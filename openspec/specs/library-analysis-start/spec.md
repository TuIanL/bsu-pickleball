# library-analysis-start Specification

## Purpose
TBD - created by archiving change restore-library-analysis-entrypoints. Update Purpose after archive.
## Requirements
### Requirement: 未分析素材进入分析创建页

系统 SHALL 让未开始分析的 LibraryItem 从比赛库卡片 / 素材工作区进入对应的分析创建页，而不是落入分析结果空态。入口分派 SHALL 依据素材类型：
- `sync_recording` 双摄素材且存在 `captureTakeId`：进入双摄协同分析创建页（`MultiViewAnalysisSetupPage`，路径 `/capture/takes/:captureTakeId/analyze?session=:sessionId`）。
- 单摄 `recording` 素材：进入该录制的既有单摄分析入口（预填录制 videoId 的分析创建流程），并带上 `source=recording` 与 `sessionId` 上下文。
- `upload` 素材：进入预填该上传 videoId 的分析创建流程（`?videoId=:sourceId`）。

编制返回路径时 SHALL 携带来源上下文，保证用户在创建页取消/完成后能回到比赛库或该素材工作区，而不是默认任务列表。

#### Scenario: 双摄未分析素材开始分析

- **WHEN** 用户在比赛库打开一个 `sync_recording` 且无 primary 分析、存在 `captureTakeId` 的素材，并触发「开始分析」
- **THEN** 系统 SHALL 导航到 `/capture/takes/:captureTakeId/analyze?session=:sessionId`

#### Scenario: 单摄录制未分析素材开始分析

- **WHEN** 用户对一个未分析的 `recording` 素材触发「开始分析」
- **THEN** 系统 SHALL 进入该录制预填 videoId 的单摄分析入口，并携带 `source=recording&sessionId` 上下文

#### Scenario: 上传素材未分析开始分析

- **WHEN** 用户对一个未分析的 `upload` 素材触发「开始分析」或菜单「重新分析」
- **THEN** 系统 SHALL 导航到 `?videoId=:sourceId` 的上传分析流程，直接以该既有视频开始分析

#### Scenario: 从卡片触发不落入结果空态

- **WHEN** 用户对未分析素材点击「开始分析」
- **THEN** 系统 SHALL NOT 导航到 `?view=analysis` 这类仅在有结果时才渲染数据的空态视图

### Requirement: 分析创建页返回路径正确

分析创建页（`MultiViewAnalysisSetupPage` / 单摄分析流程）SHALL 在取消/退出时正确返回来源（该素材的工作区或比赛库），而非工程任务列表；在 Job 创建成功后 SHALL 统一进入分析进度页（`/analysis/:jobId?return=:上游 return`），并将 `return` 原样转发给进度页，供进度页返回/完成时回到同一来源。

#### Scenario: 创建页取消返回来源

- **WHEN** 用户从素材工作区发起分析类型跳转，随后在创建页取消
- **THEN** 系统 SHALL 返回该素材工作区（`/library/:kind/:sourceId?view=overview`）或比赛库

#### Scenario: 创建成功后进入分析进度页

- **WHEN** 用户从素材工作区发起分析并成功创建 Job
- **THEN** 系统 SHALL 导航到 `/analysis/:jobId?return=<该素材工作区路径>`
- **AND** SHALL NOT 直接回跳素材工作区或任务列表

#### Scenario: 创建成功转发 return

- **WHEN** 分析创建页导航到进度页
- **THEN** 进度页 URL SHALL 携带与创建页一致的上游 `return`（如 `/library/:kind/:sourceId?view=overview`）
- **AND** 创建页 SHALL NOT 丢弃 `return` 或以任务列表路径替代

### Requirement: 素材工作区返回路径的携带

系统 SHALL 在从 Library 素材工作区分派「开始分析」时，为生成的分析创建入口 URL 附加 `return=/library/:kind/:sourceId?view=overview`，作为该次分析的来源契约。

#### Scenario: 未分析素材开始分析携带 return

- **WHEN** 用户在素材工作区对未分析素材触发「开始分析」
- **THEN** 目标创建页 URL SHALL 携带 `return=/library/:kind/:sourceId?view=overview`
- **AND** 该 `return` SHALL 贯穿创建页 → 进度页，直到回到同一工作区

