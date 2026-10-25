## MODIFIED Requirements

### Requirement: Progress 返回与完成去向 origin 化

AnalysisJobPage SHALL 依据 resolveAnalysisFlowOrigin 决定返回文案、返回路径与完成、失败或取消后的 CTA 目的地，而不得无条件使用 taskListPathForJob(job)。Library origin 的完成结果 CTA SHALL 显式锁定当前完成 Job。以下 Workspace/工程报告 CTA 场景适用于 legacy_v1（含缺省 engine）；modular_v1 SHALL 由当前任务路由展示模块结果，返回路径仍遵循相同 origin，不渲染完整报告 CTA。

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

#### Scenario: 模块完成后保留当前 Job 与来源
- **WHEN** modular_v1 任务到达终态，无论 origin 为 library、capture 或 task-console
- **THEN** 当前任务路由 SHALL 展示该 Job 的模块结果和诊断，保留对应 origin 的返回控件
- **AND** SHALL NOT 导航到 legacy Workspace view 或以读取完整报告决定完成去向

### Requirement: 稳定结果与瞬时执行分离（primaryResult / active）

系统 SHALL 将「稳定结果」与「瞬时执行」拆为两个 selection contract：`primaryResultAnalysisJobId` SHALL 为最新 **completed** 的 legacy_v1（含缺省 engine）权威完整结果，并保留既有双摄 Parent 选择规则（驱动结果 view 门控）；`activeAnalysisJobId` SHALL 为最新公开 active 任务（包括 modular_v1）（驱动进度展示，不参与结果门控）。再次分析进行中，旧 completed 结果 SHALL 保持可用，不得被 active 任务顶掉。

#### Scenario: 再次分析期间旧结果保持可用

- **WHEN** 素材已有 `primaryResultAnalysisJobId=Job A(completed)` 且用户触发再次分析（`activeAnalysisJobId=Job B(processing)`）
- **THEN**「数据分析 / 球路 / 报告 / 技术详情」SHALL 继续由 Job A 供给，保持可用
- **AND** 概览 SHALL 显示「正在重新分析 · N%」而不锁定结果视图

#### Scenario: 完成后切换 primaryResult

- **WHEN** 符合完整结果选择规则的 legacy_v1 Job B 由 processing 转为 completed
- **THEN** 经 reconciliation 重投影后 `primaryResultAnalysisJobId` SHALL 切换为 Job B
- **AND** 无其他 active 任务时 `activeAnalysisJobId` SHALL 清空；否则 SHALL 指向剩余最新 active 任务

#### Scenario: primaryResult 只取 completed

- **WHEN** `libraryAdapter` 选择 primaryResult
- **THEN** 系统 SHALL 只从 completed 的 legacy_v1（含缺省 engine，且 public、非 internal child）完整任务中按既有素材规则选取最新者
- **AND** active（queued / uploaded / processing）任务 SHALL NOT 成为 `primaryResultAnalysisJobId`

#### Scenario: 专项完成不替换完整报告
- **WHEN** 已有完整结果 A，较新的模块任务 B 完成
- **THEN** reconciliation SHALL 更新 B 的历史记录与 active 状态，primaryResultAnalysisJobId SHALL 仍为 A
- **AND** A 的报告及球路可用性 SHALL 不受 B 的原始观测影响

#### Scenario: 素材只有专项结果
- **WHEN** 素材存在 completed 模块任务而无已完成完整分析
- **THEN** primaryResultAnalysisJobId SHALL 为空，模块历史 SHALL 显示专项分析完成
- **AND** 完整报告和球路 SHALL 不因模块 completed 而启用

### Requirement: Workspace 的 analysisJob 是 canonical 结果版本参数

素材工作区 SHALL 使用 analysisJob=:jobId URL query 表达用户显式选中的分析版本。对 legacy_v1（含缺省 engine），该参数 SHALL 在刷新、工作区 Tab 切换和 embedded 结果内部跳转中保留。对属于当前素材的 modular_v1 参数，系统 SHALL 先完成归属校验再 replace 到携带原素材 return 的模块任务路由，不把模块清单传给 Workspace 的完整结果消费者。

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

#### Scenario: 模块版本深链分流
- **WHEN** 用户刷新带当前素材 modular_v1 Job 的 analysisJob 深链
- **THEN** 系统 SHALL replace 到 `/analysis/:jobId?return=<当前素材概览>`，不加载 legacy 结果
- **AND** 跨素材模块 Job SHALL 继续按无效参数规则拒绝，不跳转到其结果
