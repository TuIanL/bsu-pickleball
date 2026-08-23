# analysis-task-management Specification

## Purpose
分析任务管理作为 Engineering Task Console 保留；普通产品流（Library origin）完成/取消/失败后不再进入任务管理，Task Console origin 的返回保持回任务列表。

## ADDED Requirements

### Requirement: 普通产品流完成后不进入任务管理

从 Library 发起（`origin=library`）的分析，在进度页完成 / 失败 / 取消后，其去向 SHALL 是 Library Item Workspace，而不是 `AnalysisTasksPage`。`/analysis/tasks` 与 `/analysis/:jobId/...` 结果路由 SHALL 仅作为 Engineering Task Console 与兼容 deep-link 保留，普通产品流 SHALL NOT 主动把用户送过去。

#### Scenario: Library origin 完成后回工作区

- **WHEN** 从 Library 发起分析且进度页任务完成
- **THEN** 系统 SHALL 将结果入口指向 `/library/:kind/:sourceId?view=...`
- **AND** SHALL NOT 导航到 `/analysis/tasks`

#### Scenario: 工程控制台 deep-link 保留

- **WHEN** 用户经 Engineering Task Console 进入任务详情或结果页
- **THEN** 该入口 SHALL 保持可用的 `/analysis/:jobId/...` 路由与完整工程能力（Parent/child 可见、进度、stage、cancel、delete、batch delete、internal visibility）

#### Scenario: Task Console origin 返回任务列表

- **WHEN** 从 `/analysis/tasks`（或带任务上下文的任务列表）发起分析并进入进度页
- **THEN** 进度页返回 SHALL 回到 `/analysis/tasks`（含来源 tab 上下文）
- **AND** 完成 CTA SHALL 保留工程结果路由

#### Scenario: 进度页不得擅自切回任务管理

- **WHEN** Progress 页的 origin 为 `library` 或 `capture`
- **THEN** 其返回/完成 CTA SHALL NOT 进入 `/analysis/tasks`
