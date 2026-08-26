## ADDED Requirements

### Requirement: Workspace 的 analysisJob 是 canonical 结果版本参数

素材工作区 SHALL 使用 analysisJob=:jobId URL query 表达用户显式选中的分析版本。该参数 SHALL 在刷新、工作区 Tab 切换和 embedded 结果内部跳转中保留。

#### Scenario: 刷新保留选中版本
- **WHEN** 用户访问带有 view=analysis 与 analysisJob=job-A 的素材工作区并刷新页面
- **THEN** 工作区 SHALL 继续将 Job A 解析为 selected Job
- **AND** SHALL 继续显示 Job A 的分析内容

#### Scenario: 切换结果 Tab 保留 Job ID
- **WHEN** 用户从 view=analysis 且 analysisJob=job-A 切换到球路、报告或技术详情
- **THEN** 目标 URL SHALL 保留 analysisJob=job-A
- **AND** view 切换 SHALL 使用 replace 语义，不为每个 Tab 新增浏览器历史项

#### Scenario: 切换到素材级 view 后返回
- **WHEN** 用户已选中 Job A，随后切换到视频或片段 view，再返回结果 view
- **THEN** 工作区 URL SHALL 在这些 Tab 切换中继续保留 analysisJob=job-A
- **AND** 返回结果 view 时 SHALL 继续显示 Job A

#### Scenario: 无效参数规范化
- **WHEN** analysisJob 无法通过当前素材的归属校验
- **THEN** 系统 SHALL 以 replace 语义移除无效 analysisJob
- **AND** SHALL 保留 view、t 与其他合法 workspace query

## MODIFIED Requirements

### Requirement: Progress 返回与完成去向 origin 化

AnalysisJobPage SHALL 依据 resolveAnalysisFlowOrigin 决定返回文案、返回路径与完成、失败或取消后的 CTA 目的地，而不得无条件使用 taskListPathForJob(job)。Library origin 的完成结果 CTA SHALL 显式锁定当前完成 Job。

#### Scenario: Library origin 返回比赛详情
- **WHEN** Progress 页的 origin 为 library
- **THEN** 顶部返回控件 SHALL 显示“返回比赛详情”
- **AND** 点击 SHALL 回到对应素材的 overview view

#### Scenario: Library origin 完成后 CTA 指向精确 Workspace 版本
- **WHEN** Progress 页的 origin 为 library 且 Job A 已完成
- **THEN** 查看数据分析、查看球路、查看报告和技术详情 CTA SHALL 分别指向对应 workspace view 并携带 analysisJob=job-A
- **AND** SHALL NOT 指向旧的独立结果路由
- **AND** SHALL NOT 依赖 Library reconciliation 已经将 Job A 选为 primary result

#### Scenario: Library origin 失败或取消 CTA
- **WHEN** Progress 页的 origin 为 library 且任务失败或取消
- **THEN** 系统 SHALL 提供“返回比赛详情”与“再次分析”入口
- **AND** SHALL NOT 显示与来源不符的“重新上传”文案

#### Scenario: Task Console origin 保留旧行为
- **WHEN** Progress 页的 origin 为 task-console
- **THEN** 返回路径 SHALL 保持 taskListPathForJob(job)
- **AND** 完成 CTA SHALL 保留旧的工程结果路由

#### Scenario: Capture origin 返回采集控制台
- **WHEN** Progress 页 origin 为 capture
- **THEN** 返回控件 SHALL 指向 return 携带的采集控制台路径

#### Scenario: Capture origin 完成后解析 Library 结果
- **WHEN** Progress 页 origin 为 capture 且 Job A 已完成
- **THEN** 查看分析结果 SHALL 经 resolveLibraryRefFromAnalysisJob(job) 解析 Library ref
- **AND** 解析成功时 SHALL 指向对应 workspace analysis view 并携带 analysisJob=job-A
- **AND** 解析失败时 SHALL 降级到 legacy 工程结果路由

#### Scenario: Progress 完成页不承担重型产物探测
- **WHEN** Progress 完成页需要展示结果 CTA
- **THEN** 必有“查看分析结果”与“返回比赛详情”
- **AND** 次级 CTA SHALL 仅在已有轻量 capability metadata 时显示
- **AND** SHALL NOT 为 CTA 加载 result、trajectory、report 或 observability 等重产物
- **AND** 进入 Workspace 后 SHALL 由 selected Job 的 LibraryViewCapabilities 统一门控结果可用性
