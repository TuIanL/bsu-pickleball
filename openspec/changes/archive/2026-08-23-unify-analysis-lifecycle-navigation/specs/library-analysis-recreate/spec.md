# library-analysis-recreate Specification

## Purpose
已分析素材「再次分析」入口的可见性、历史保持，以及再次分析创建成功后统一进入分析进度页的返回契约。

## ADDED Requirements

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
