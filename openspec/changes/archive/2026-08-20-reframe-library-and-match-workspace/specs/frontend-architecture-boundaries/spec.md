## ADDED Requirements

### Requirement: Library 与 Workspace 路由契约
前端 Pathname/Search 解析 SHALL 保持纯函数、可测试，并新增对 Library 与 Workspace 路由的无歧义解析。

#### Scenario: Library 路由解析
- **WHEN** pathname 为 `/library/recording/r-1?view=analysis`
- **THEN** 解析器 SHALL 生成 `{ name: "library-item", kind: "recording", sourceId: "r-1", view: "analysis" }` 单一 RouteState
- **AND** 该解析 SHALL 与顺序敏感的兄弟 states（analysis-job / vision / report 等）无歧义
- **AND** 非法 kind / sourceId / view SHALL 安全回退，不抛解析异常

#### Scenario: Workspace view query 契约
- **WHEN** `view` 处于受支持枚举（overview / video / analysis / trajectory / report / segments / technical）
- **THEN** 系统 SHALL 渲染对应 View
- **WHEN** `view` 缺失或不支持
- **THEN** 系统 SHALL 回退到 `overview`

#### Scenario: 可刷新深链
- **WHEN** 用户直接打开某 LibraryItem 某 view 的完整 URL
- **THEN** 系统 SHALL 恢复到对应素材与 view，无需额外前置状态

### Requirement: view 历史语义契约
系统 SHALL 对 Workspace 内一级 view 切换使用 replace 历史语义（复用 `NavigateOptions.replace`），对 Library→Workspace 及 Workspace→外部对象跳转使用 push 语义。

#### Scenario: 层级跳转入栈
- **WHEN** 用户从 `/library` 进入某比赛
- **THEN** 系统 SHALL 新增历史项（push）

#### Scenario: view 切换不污染历史
- **WHEN** 用户在同一素材下切换 `?view`（含 `?view=video&t=...` 证据跳转）
- **THEN** 系统 SHALL 使用 replace 语义，不新增历史项

#### Scenario: 返回行为
- **WHEN** 用户在 `?view=analysis` 按一次浏览器 Back
- **THEN** 系统 SHALL 回到 `/library`，而非逐个 view 回退

#### Scenario: Legacy route 保留 sibling RouteState
- **WHEN** 用户访问旧 route `/analysis/job-123/vision`（不含 sourceType/sourceId）
- **THEN** 迁移期系统 SHALL 先以旧 sibling RouteState 直渲
- **AND** 由 `LegacyLibraryRouteResolver` 异步加载 job → `resolveLibraryItemRef(job)` → replace 到 `/library/...`

### Requirement: view capability gate 与 stable fallback

系统 SHALL 依据素材 availability/analysisState 门控 workspace 各 view，并在无可用结果时提供 stable fallback，不允许空白页。

#### Scenario: 无成功分析时深链结果 view
- **WHEN** 用户深链至 `?view=report`（或 trajectory/multiview）而素材无成功的 primary analysis
- **THEN** 系统 SHALL 落到 stable fallback（如 `overview` + 待分析提示）
- **AND** SHALL NOT 渲染空白页

### Requirement: 上传/采集默认落点

Library-first 后，上传与现场采集的完成落点 SHALL 指向对应 LibraryItem，而非回到任务列表。

#### Scenario: 上传创建分析后进入比赛详情
- **WHEN** 用户完成上传 + 四角标定 + 创建分析
- **THEN** 系统 SHALL 进入 `/library/upload/{videoId}?view=analysis`
- **AND** 直接展示该素材「正在分析」状态，而非导航回 `AnalysisTasksPage`

#### Scenario: 采集 durable 后进入库卡片
- **WHEN** 现场采集完成后素材 durable 化
- **THEN** 该素材 SHALL 以对应 LibraryItem 呈现在比赛库中