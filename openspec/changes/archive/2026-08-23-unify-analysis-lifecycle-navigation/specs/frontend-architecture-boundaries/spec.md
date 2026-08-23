# frontend-architecture-boundaries Specification

## Purpose
路由解析、页面边界与历史语义契约的更新：上传/采集创建后统一经 Analysis Progress 进入工作区；analysis 路由从 `return` 推导 origin 与 `navigationSection`。

## MODIFIED Requirements

### Requirement: 上传/采集默认落点

Library-first 后，上传与现场采集的分析 SHALL 遵循统一生命周期：创建 Job 后先进入 Analysis Progress（transient），完成后再进入对应 LibraryItem Workspace，而不是回到任务列表或直接跳工作区。

#### Scenario: 上传创建分析后进入进度页再入比赛详情

- **WHEN** 用户完成上传 + 四角标定 + 创建分析
- **THEN** 系统 SHALL 先进入 `/analysis/:jobId?return=/library/upload/{videoId}?view=overview`（Analysis Progress）
- **AND** 任务完成后 SHALL 进入 `/library/upload/{videoId}?view=analysis`
- **AND** SHALL NOT 导航回 `AnalysisTasksPage`

#### Scenario: 采集 durable 后进入库卡片

- **WHEN** 现场采集完成后素材 durable 化
- **THEN** 该素材 SHALL 以对应 LibraryItem 呈现在比赛库中

#### Scenario: 全新上传无 return 时合成 Library return

- **WHEN** 用户从比赛库「上传视频」进入 `/upload`（无 `return` 且 `videoId` 尚未生成），上传成功并创建 Job
- **THEN** 系统 SHALL 先进入 `/analysis/:jobId?return=/library/upload/:videoId?view=overview`（Analysis Progress）
- **AND** 任务完成后 SHALL 进入 `/library/upload/:videoId?view=analysis`
- **AND** SHALL NOT 被识别为 task-console，也不进入 `/analysis/tasks`

## ADDED Requirements

### Requirement: 上传创建后不进入任务列表

上传/录制/双摄分析在创建与完成全流程中 SHALL NOT 将用户送入 `/analysis/tasks`；任务列表仅作为 Engineering Task Console 或带显式任务上下文的 deep-link 可达。

#### Scenario: 创建与完成均不进入任务列表

- **WHEN** 用户完成任一类型分析的创建并等待其完成
- **THEN** 系统 SHALL 全程停留在产品流（Progress → Library Item Workspace）
- **AND** SHALL NOT 主动导航到 `/analysis/tasks`

### Requirement: analysis 路由从 return 推导 origin 与导航段

路由解析 SHALL 在 analysis 系列路由（`analysis-job` / `vision` / `ball-trajectory` / `multiview-observability` / `analysis-details` / `report`）上读取 `return` 查询参数：`return` 以 `/library/` 开头则覆盖 `navigationSection` 为 `library`；以 `/capture/` 开头则覆盖为 `capture`；解析 SHALL 保持纯函数、可测，非法 `return` SHALL 安全忽略不抛错。

#### Scenario: Library return 覆盖导航段

- **WHEN** 解析 `/analysis/job-1?return=/library/sync_recording/sync_xxx?view=overview`
- **THEN** 返回 RouteState 的 `navigationSection` SHALL 为 `library`
- **AND** 其余字段（jobId、shellMode 等）SHALL 保持不变

#### Scenario: Capture return 覆盖导航段

- **WHEN** 解析 `/analysis/job-1?return=/capture/fs-1`
- **THEN** 返回 RouteState 的 `navigationSection` SHALL 为 `capture`

#### Scenario: 无 return 保持原语义

- **WHEN** 解析 `/analysis/job-1`（无 `return`）或 `return` 为非法值
- **THEN** `navigationSection` SHALL 保持路由原有值
- **AND** 解析 SHALL 不抛异常、不产生破损 RouteState

#### Scenario: return 可刷新深链

- **WHEN** 用户直接打开带 `return` 的 analysis 路由 URL
- **THEN** 系统 SHALL 恢复对应 job 与 origin 语义（含返回目的地），无需额外前置状态

### Requirement: 结果页面边界收敛为 Content 组件

系统 SHALL 将 Vision / BallTrajectory / AnalysisDetails / Multiview 的结果渲染收敛为 `*Content` 组件（沿用 ReportContent → PbReportContent 模式），由 Workspace 直接消费；`*Page` 外壳仅服务 standalone 渲染。`*Content` SHALL 接受 `onSelectView(view)` 用于 embedded 下的 view 切换。

#### Scenario: Workspace 消费 Content

- **WHEN** Workspace 渲染 `?view=analysis` / `?view=trajectory` / `?view=technical`
- **THEN** 系统 SHALL 直接消费对应 `*Content` 组件
- **AND** SHALL NOT 重新挂载完整 `*Page` shell

#### Scenario: embedded 下 view 切换回调

- **WHEN** `*Content` 以 embedded 方式渲染且用户触发结果切换（如查看球路/报告/技术详情）
- **THEN** 系统 SHALL 调用 `onSelectView(view)` 留在同一 Library Item
- **AND** standalone 时 SHALL 回退到 `/analysis/:jobId/...` 既有路由
