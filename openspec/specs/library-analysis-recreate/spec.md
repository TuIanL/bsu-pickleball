# library-analysis-recreate Specification

## Purpose
TBD - created by archiving change restore-library-analysis-entrypoints. Update Purpose after archive.
## Requirements
### Requirement: 已分析素材提供「再次分析」入口

系统 SHALL 让已分析的 LibraryItem 从比赛库卡片与素材工作区提供「再次分析 / 再建一次分析」入口，从而对同一录制建立多个分析任务，行为与工程控制台一致但无需进入工程页面。该入口 SHALL 依据素材类型复用既有分析创建页：
- `sync_recording`：允许再建双摄协同分析（`/capture/takes/:captureTakeId/analyze`）与 A/B 机位单摄分析（`/capture/:sessionId/analyze?cam=...`）。
- 单摄 `recording`：允许再建单摄分析。
- `upload`：复用预填 videoId 的上传分析流程。

历史多次分析 SHALL 不被静默覆盖：`LibraryItemViewModel.analysisHistoryCount` 继续如实反映已建立的分析次数，新建任务后更新。

#### Scenario: 双摄已分析素材再建分析

- **WHEN** 用户对一个已有分析结果的 `sync_recording` 素材触发「再次分析」
- **THEN** 系统 SHALL 提供双摄协同分析入口 `/capture/takes/:captureTakeId/analyze?session=:sessionId`，创建新分析任务后原任务不受影响

#### Scenario: 已分析素材从卡片进入再次分析

- **WHEN** 用户在比赛库卡片对已分析素材（含录制/双摄/上传）右键菜单或直接操作选择「再次分析」
- **THEN** 系统 SHALL 打开对应的分析创建流程，而非仅跳转到已有结果视图

#### Scenario: 多次分析历史保持

- **WHEN** 用户对同一录制第二次发起分析并成功创建
- **THEN** 该素材的 `analysisHistoryCount` SHALL 增加，且之前的历史任务仍然存在、可被读取

### Requirement: 再次分析入口的可见性

比赛库卡片与素材工作区 SHALL 依据素材媒体生命周期决定「再次分析」入口是否可用：素材处于可分析状态（媒体就绪）时可见，正在录制/处理未就绪时不可用。

注意：「源视频流暂不可用」只 SHALL 阻断「未分析」素材的首次分析；对已分析素材的再次分析，即使视频流暂不可用（如双摄某一路源视频 unavailable），仍 SHALL 提供再分析入口——可基于已注册/已落盘的机位重新分析，避免出现「卡片显示已分析却无再次分析按钮」的死角。

#### Scenario: 可分析状态下可见

- **WHEN** 素材媒体就绪（`mediaState=ready`）且不是正在录制/处理中
- **THEN** 「再次分析」入口 SHALL 可见可用

#### Scenario: 未就绪状态（未分析素材）下不可用

- **WHEN** 素材正在录制或未分析的素材视频未就绪（合并未完成/源视频流不可用）
- **THEN** 「再次分析/开始分析」入口 SHALL 不可用或隐藏，且不得伪造可用

#### Scenario: 已分析素材视频流暂不可用仍可再次分析

- **WHEN** 素材已有分析结果（`primaryAnalysisJobId` 存在）但源视频流暂不可用（`availabilityState=unavailable`）
- **THEN** 「再次分析」入口 SHALL 仍可见可用，允许基于已注册/已落盘机位重建分析任务

### Requirement: 概览删除/取消单个历史分析任务

素材工作区概览 SHALL 列出该素材的历史分析任务（公开项，新→旧），并允许逐任务删除或取消，以管理多次分析而不删除原视频。

#### Scenario: 列出历史任务

- **WHEN** 素材存在一个或多个公开分析任务
- **THEN** 概览「分析状态」卡片 SHALL 展示「历史分析任务」列表，每项含任务类型（双摄协同/单视角）与状态

#### Scenario: 删除已完成任务

- **WHEN** 用户对一个已完成/失败/已取消的历史任务触发删除并确认
- **THEN** 系统 SHALL 调用任务删除接口（含本地产物清理），原素材视频保留，删除后概览 SHALL 刷新最新状态

#### Scenario: 取消进行中任务

- **WHEN** 用户对一个排队中/分析中的历史任务触发取消
- **THEN** 系统 SHALL 请求取消该任务并在安全检查点停止，概览 SHALL 刷新最新状态

### Requirement: 再次分析创建成功后进入分析进度页

再次分析（recreate）与首次分析 SHALL 遵循同一生命周期：Job 创建成功后统一进入分析进度页（`/analysis/:jobId?return=:上游 return`），进度页返回/完成时回到该素材工作区，而非任务列表或旧结果路由。

#### Scenario: 再次分析创建成功进入进度页

- **WHEN** 用户对已分析素材触发「再次分析」并成功创建新 Job
- **THEN** 系统 SHALL 导航到 `/analysis/:jobId?return=/library/:kind/:sourceId?view=overview`
- **AND** SHALL NOT 直接跳回素材工作区或 `/analysis/tasks`

#### Scenario: 再次分析后返回同一工作区

- **WHEN** 用户从再次分析的进度页点击返回
- **THEN** 系统 SHALL 回到同一素材工作区（`/library/:kind/:sourceId?view=overview`）
- **AND** 该素材的 `analysisHistoryCount` SHALL 已如实反映新增的分析次数

#### Scenario: 再次分析入口携带来源 return

- **WHEN** 比赛库卡片或素材工作区触发「再次分析」
- **THEN** 生成的分析创建入口 URL SHALL 携带 `return=/library/:kind/:sourceId?view=overview`
- **AND** 该 `return` SHALL 贯穿创建页 → 进度页，直到回到同一工作区

