# library-analysis-start Specification

## Purpose
素材开始分析的入口分派与来源上下文携带，以及创建成功后统一进入分析进度页的返回契约。

## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: 素材工作区返回路径的携带

系统 SHALL 在从 Library 素材工作区分派「开始分析」时，为生成的分析创建入口 URL 附加 `return=/library/:kind/:sourceId?view=overview`，作为该次分析的来源契约。

#### Scenario: 未分析素材开始分析携带 return

- **WHEN** 用户在素材工作区对未分析素材触发「开始分析」
- **THEN** 目标创建页 URL SHALL 携带 `return=/library/:kind/:sourceId?view=overview`
- **AND** 该 `return` SHALL 贯穿创建页 → 进度页，直到回到同一工作区
