# workspace-content-composition Specification

## Purpose
把 LibraryItemWorkspace 缺失的「Workspace → Content」composition contract 落地：修复各 view 条件渲染正确性、双摄视频接入、view capability 门控，并把旧整页拆成可嵌入 workspace 的 `*Content` 组件，彻底消灭「页面套页面」。

## Requirements
### Requirement: 每个 view 只在当前激活时渲染一个分支

LibraryItemWorkspace 的内容区 SHALL 为每个 view 使用 `effectiveView === xxx && (gate ? Content : EmptyState)` 结构，确保非当前 view 既不渲染内容、也不渲染其空态。

#### Scenario: 概览视图不渲染其他视图的空态
- **WHEN** 用户处于 `?view=overview`
- **THEN** 内容区 SHALL 只渲染概览内容
- **AND** SHALL NOT 渲染「暂无可用视频回放」「暂无可用分析结果」「暂无可用球路」等其他 view 的空态

#### Scenario: 数据分析视图不渲染其他空态
- **WHEN** 用户处于 `?view=analysis` 且存在分析结果
- **THEN** 内容区 SHALL 渲染分析内容
- **AND** SHALL NOT 渲染「暂无可用视频回放」「暂无可用球路」「暂无可用报告」等非当前 view 的空态

### Requirement: 视频 view 三类来源统一分派

Workspace 的 `video` view SHALL 按素材来源统一分派：`upload` 用 `SourceVideoContent(videoId)` 播放源视频（经 `GET /api/videos/{videoId}/stream`）；`recording` 与 `sync_recording` 用 `RecordingWorkspaceContent(sessionId)`（内部依据 `getRecording` / `getSyncRecording` 自动判定 single/dual 并正确回放）；`availabilityState=unavailable` 时展示明确不可用状态。

#### Scenario: sync_recording 打开视频
- **WHEN** 用户打开一个 `sync_recording` 素材并进入 `?view=video`
- **THEN** 系统 SHALL 渲染双摄视频回放视图
- **AND** SHALL NOT 显示「暂无可用视频回放」

#### Scenario: upload 打开视频
- **WHEN** 用户打开一个 `upload` 素材并进入 `?view=video`
- **THEN** 系统 SHALL 经 `GET /api/videos/{videoId}/stream` 播放源视频
- **AND** SHALL NOT 因「upload 无回放」判空态

#### Scenario: 视频资产不可用
- **WHEN** 素材 `availabilityState=unavailable`（如外置存储掉线）
- **THEN** 系统 SHALL 在视频 view 显示明确不可用状态
- **AND** SHALL NOT 假造可回放的画面

### Requirement: Content 组件抽取（消灭页面套页面）

System SHALL 将 `VisionPage / ReportPage / BallTrajectoryPage / RecordingWorkspacePage / SegmentManagerPage / MultiviewObservabilityPage / AnalysisDetailsPage` 拆出可嵌入式 `*Content` 组件（数据加载与渲染一起抽取），并提供两种挂载方式：legacy 路由 `PageFrame + Content`，workspace `Content`。

#### Scenario: 旧路由保留原页面外壳
- **WHEN** 用户访问独立的旧结果页路由（未经过 workspace）
- **THEN** 系统 SHALL 以 `PageFrame` + `*Content` 渲染，保持原有标题/返回/导航语义，不回归

#### Scenario: 数据分析 view 无第二套页面外壳
- **WHEN** 用户处于 workspace `?view=analysis`
- **THEN** 内容区 SHALL 只渲染该分析的 `*Content`
- **AND** SHALL NOT 显示旧页面的「返回任务管理」「视频分析结果」第二套标题与按钮

### Requirement: view capability 门控基于 AnalysisResult manifest

Workspace 结果类 view（分析/球路/报告/技术详情）可开性 SHALL 依据「primary Job 状态 + AnalysisResult artifact manifest」一次判定，而非仅看 `primaryAnalysisJobId` 是否存在；初始门控 SHALL NOT 通过逐 view 拉取重产物（trajectory/report/heatmap/overlay…）来判断。缺产出的合法 view SHALL 停在原 URL 显示缺产物提示；非法 view（该 source 根本不支持）SHALL replace 落到 overview。

#### Scenario: 有任务但缺该 view 产出物（合法但缺产物）
- **WHEN** 素材存在分析任务但未产出球路/报告等特定 artifact（如 completed job 无 trajectory artifact）
- **THEN** 用户仍停在原 URL（如 `?view=trajectory`）
- **AND** 系统 SHALL 显示「本次分析未生成该数据」类提示
- **AND** SHALL NOT 把 URL/UI 双双改到 overview 造成二次不一致

#### Scenario: 非法 view
- **WHEN** 用户访问该素材 source 根本不支持的 view（如 `upload?view=segments`）
- **THEN** 系统 SHALL replace 到 overview

#### Scenario: 初始门控不拉重产物
- **WHEN** Workspace 首次判定各 view 可开性
- **THEN** 系统 SHALL 仅基于 Job 状态与 AnalysisResult manifest 的 artifact URL（如 `cleaned_ball_trajectory_url` / `ball_trajectory_url` / report 证据）一次完成
- **AND** SHALL NOT 因逐一拉取 trajectory/report/heatmap 等重产物而触发请求风暴

#### Scenario: 无分析结果时
- **WHEN** 素材无成功分析
- **THEN** 结果类 view SHALL 不可用并落入 overview + 待分析提示