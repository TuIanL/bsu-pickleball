## ADDED Requirements

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