## ADDED Requirements

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
