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

Workspace 结果类 view 的可开性 SHALL 依据 selected Job 状态与 selected Job 的 AnalysisResult artifact manifest 一次判定，而非仅看 primaryAnalysisJobId 是否存在。未显式选择时，selected Job SHALL 回退为 primaryResultAnalysisJobId。初始门控 SHALL NOT 通过逐 view 拉取重产物判断。缺产出的合法 view SHALL 停在原 URL 显示缺产物提示；非法 view SHALL replace 落到 overview。

#### Scenario: selected Job 缺该 view 产出物
- **WHEN** selected Job 存在但未产出球路或报告等特定 artifact
- **THEN** 用户 SHALL 仍停在原 URL
- **AND** 系统 SHALL 显示“该分析版本未生成该数据”类提示
- **AND** SHALL NOT 回退读取 primary Job 或其他 Job 的产物

#### Scenario: selected Job 改变后 capability 重算
- **WHEN** 用户从 Job A 切换到 Job B
- **THEN** 系统 SHALL 按 Job B 状态与 manifest 重算所有结果 view capability
- **AND** SHALL NOT 复用 Job A 的 manifest 或 capability 结果

#### Scenario: 非法 view
- **WHEN** 用户访问当前素材来源根本不支持的 view
- **THEN** 系统 SHALL replace 到 overview
- **AND** 若当前 analysisJob 合法，URL SHALL 保留该选择

#### Scenario: 初始门控不拉重产物
- **WHEN** Workspace 首次判定 selected Job 的各 view 可开性
- **THEN** 系统 SHALL 仅基于 Job 状态与 AnalysisResult manifest 的 artifact metadata 完成
- **AND** SHALL NOT 逐一拉取 trajectory、report、heatmap 或 overlay 等重产物

#### Scenario: 无可用 selected result
- **WHEN** 素材无 completed 结果且未显式选中可诊断的 terminal Job
- **THEN** 结果类 view SHALL 不可用并显示待分析或无结果提示

### Requirement: Job-bound Content 组件使用统一 selected Job

Workspace SHALL 从同一 SelectedAnalysisContext 向数据分析、球路、报告与技术详情 Content 传入 Job ID。素材级视频和片段 Content 不受 selected Job 数据源限制。

#### Scenario: 四个结果 Content 使用同一 Job
- **WHEN** selected Job 为 Job A
- **THEN** Vision、BallTrajectory、Report 和 Technical Content SHALL 全部获得 Job A 作为数据源
- **AND** 任一 Content MUST NOT 内部改回 primaryResultAnalysisJobId

#### Scenario: 快速切换版本不显示过期响应
- **WHEN** 用户在 Job A 的数据请求尚未完成时切换到 Job B
- **THEN** 系统 SHALL 取消或忽略 Job A 的过期响应
- **AND** 页面 SHALL NOT 在 Job B 的选中态下渲染 Job A 内容

#### Scenario: 素材级 view 不被历史结果替换
- **WHEN** 用户已选中历史 Job A 并进入视频或片段 view
- **THEN** 视频与片段 SHALL 继续表达当前 LibraryItem 素材
- **AND** SHALL NOT 将 Job A 误当成另一个素材容器
