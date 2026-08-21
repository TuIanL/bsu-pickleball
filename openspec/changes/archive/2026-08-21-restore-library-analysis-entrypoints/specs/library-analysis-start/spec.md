## ADDED Requirements

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

分析创建页（`MultiViewAnalysisSetupPage` / 单摄分析流程）SHALL 在其取消/退出/完成回跳时正确返回来源（该素材的工作区或比赛库），而非工程任务列表。

#### Scenario: 创建页取消返回来源

- **WHEN** 用户从素材工作区发起分析类型跳转，随后在创建页取消
- **THEN** 系统 SHALL 返回该素材工作区（`/library/:kind/:sourceId?view=overview`）或比赛库