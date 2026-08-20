# legacy-analysis-workflow-consolidation Specification

## Purpose
TBD - created by archiving change stabilize-codebase-and-remove-legacy-debt. Update Purpose after archive.
## Requirements
### Requirement: 分析任务使用规范路由并兼容历史入口

系统 SHALL 使用 `/analysis/tasks` 作为分析任务列表的规范入口，并保留 `/tasks` 兼容别名。

#### Scenario: 规范入口打开分析任务列表

- **WHEN** 用户访问 `/analysis/tasks` 或点击侧边栏的“分析任务”
- **THEN** 系统 SHALL 渲染同一个 `AnalysisTasksPage`
- **AND** 当前导航分区 SHALL 为分析任务对应的稳定字面量

#### Scenario: 历史入口保持可用

- **WHEN** 用户访问 `/tasks` 或使用历史页面中的任务列表链接
- **THEN** 系统 SHALL 渲染与 `/analysis/tasks` 等价的任务列表
- **AND** SHALL NOT 渲染已删除的旧页面组件

#### Scenario: 两个入口的路由契约一致

- **WHEN** 路由测试分别解析 `/tasks` 和 `/analysis/tasks`
- **THEN** 两个结果 SHALL 指向同一个页面入口
- **AND** `shellMode`、`navigationSection` 与任务页面行为 SHALL 有明确且一致的测试断言

### Requirement: 真实 API 失败必须可见

前端 SHALL 区分真实分析任务、明确创建的本地 demo 任务和真实 API 请求失败，不得把请求失败静默转换为已完成分析。

#### Scenario: 真实视频任务请求失败

- **WHEN** 创建任务时携带 `videoId` 且 API 返回网络错误或 HTTP 4xx/5xx
- **THEN** `analysisClient` SHALL 抛出可识别的 API 错误
- **AND** SHALL NOT 创建 `status = completed` 的本地 demo job

#### Scenario: 明确的 demo 任务仍可离线运行

- **WHEN** 用户没有真实视频输入且调用方明确允许 demo fallback
- **THEN** 系统 MAY 创建本地 demo job
- **AND** 任务 SHALL 带有可识别的 demo/source 标记

#### Scenario: 真实任务查询失败

- **WHEN** 查询真实任务、报告或结果接口失败且 localStorage 只有 demo 数据
- **THEN** 页面 SHALL 展示错误或不可用状态
- **AND** SHALL NOT 用无关 demo 报告覆盖真实任务状态

### Requirement: SHALL 保留旧路由兼容映射
旧有 route SHALL 作为兼容 alias 保留，普通用户经新 Library-first 导航进入新入口，同时不粗暴断链历史 URL。

#### Scenario: 工程任务旧入口兼容
- **WHEN** 用户或历史链接访问 `/analysis/tasks` 或 `/tasks`
- **THEN** 系统 SHALL 渲染工程任务控制台（Engineering Task Console）
- **AND** 保留 Parent/child、进度、cancel/delete/batch/retry 等能力

#### Scenario: 上传/报告旧入口兼容
- **WHEN** 用户访问 `/upload`、`/reports/:type` 等旧入口
- **THEN** 系统 SHALL 提供等价能力迁移到 Library/Workspace 上下文或返回兼容视图
- **AND** 失败路径 SHALL 回退而非渲染破坏态

#### Scenario: 来源上下文保留
- **WHEN** URL 携带 `source` / `session` 等来源上下文
- **THEN** 系统 SHALL 在迁移后仍能还原到对应的素材库或工程任务上下文

### Requirement: 采集与工程入口保留
Capture 链路（`/capture`、`/capture/new`、`/capture/:id`）与工程链路（双摄同步、可观测性）SHALL 保留，作为专业/工程层能力，不对其做 Library 化重写。

#### Scenario: 采集控制台保留
- **WHEN** 用户进入现场采集
- **THEN** 系统 SHALL 保留 `/capture/:id` 实时录制/摄像头/打点/比分/时间线能力
- **AND** 采集链路不被 Library 化改动破坏

#### Scenario: 工程诊断保留
- **WHEN** 处于工程层
- **THEN** 双摄同步、Multiview Observability、Pipeline Diagnostics 等能力 SHALL 可访问且语义不变

