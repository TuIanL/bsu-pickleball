# report-detail-pages Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
### Requirement: Typed report detail pages
The system SHALL provide focused report pages for supported analysis types.

#### Scenario: User opens movement report
- **WHEN** the user opens `/reports/movement`
- **THEN** the system presents movement or court coverage analysis with metrics, path or balance visualization, and coach-readable interpretation

#### Scenario: User opens diagnosis report
- **WHEN** the user opens `/reports/diagnosis`
- **THEN** the system presents motion diagnosis content with evidence, severity, suggested correction, and links to relevant training recommendations

#### Scenario: User opens a removed landing report
- **WHEN** the user opens `/reports/landing`
- **THEN** the system shows a stable fallback or redirects to the analysis details page instead of rendering a current real-job landing analysis

### Requirement: Report metrics and interpretation
Each report detail page SHALL pair numeric metrics with explanatory coaching context.

#### Scenario: User reads a report page
- **WHEN** a report detail page is displayed
- **THEN** the system shows core metrics, trend or comparison context, and at least one explanatory insight that translates data into action

### Requirement: Report visualizations
Report detail pages SHALL include visual analysis elements appropriate to the selected report type.

#### Scenario: User views a report visualization
- **WHEN** a report detail page is displayed
- **THEN** the system shows a chart, mini court map, heat visualization, route visualization, movement path, skill rating, or equivalent visual module that matches the selected report type

### Requirement: Report-to-training bridge
Report detail pages SHALL provide a clear path from findings to recommended practice.

#### Scenario: User sees a trainable weakness
- **WHEN** a report detail page identifies a weakness or improvement area
- **THEN** the system shows a training recommendation link or action related to that finding

### Requirement: Local mock report data
Report detail pages SHALL render from structured local mock data.

#### Scenario: Developer replaces mock report data later
- **WHEN** report definitions, metrics, insights, visualizations, and training links are inspected
- **THEN** they are represented as structured data objects rather than hard-coded unrelated page fragments

### Requirement: Job-specific report data

Report detail pages SHALL render completed analysis job report data using the authoritative generated report payload as the exclusive source for job-specific report pages; the frontend SHALL NOT assemble real-job reports from raw pipeline results or demo fallback data.

#### Scenario: User opens a completed job report

- **WHEN** the user opens movement, diagnosis, or performance report detail for a completed analysis job
- **THEN** the page renders metrics, visualization data, insights, and training links exclusively from that job's generated report payload without requiring raw algorithm result or overlay artifact downloads

#### Scenario: User opens a sample report

- **WHEN** the user opens the existing sample report route without a job identifier
- **THEN** the page continues to render structured local mock report data with subtle sample context

#### Scenario: Real-job report payload is unavailable

- **WHEN** a job-specific report route is opened and the authoritative report payload is not yet available or fails to load
- **THEN** the system shows a report-generating or report-load-failed state
- **AND** the system MUST NOT substitute demo report data or a frontend-assembled near-report built from raw pipeline results

### Requirement: Job-aware report states
Report detail pages SHALL communicate when job-specific report data is unavailable and distinguish report loading from visual overlay loading.

#### Scenario: User opens a report before job completion
- **WHEN** the user opens a report route for a job that is queued or processing
- **THEN** the system routes back to or displays the job status state instead of rendering incomplete report data

#### Scenario: User opens a report for a failed job
- **WHEN** the user opens a report route for a failed analysis job
- **THEN** the page shows a stable failed-analysis state with a return or retry action

#### Scenario: User opens an unknown job report
- **WHEN** the user opens a report route for a job identifier that cannot be found
- **THEN** the page shows a stable not-found or fallback state without rendering broken report modules

#### Scenario: User waits for report data
- **WHEN** a job-specific report page is waiting for the job summary or generated report payload
- **THEN** the loading state communicates that report data is being read and does not imply that heavyweight video overlay artifacts must finish loading first

### Requirement: Lightweight job report loading
Job-specific report detail pages SHALL render from the completed job summary and generated report payload without waiting for raw algorithm results, source video streams, tracking overlays, or pose overlay artifacts that are not required by the selected report page.

#### Scenario: Completed job report opens while large overlays exist
- **WHEN** the user opens `/analysis/:jobId/reports/:type` for a completed job whose generated report payload is available and whose overlay artifacts are large or slow to download
- **THEN** the report page renders the selected report content from the job/report payload without waiting for those overlay artifacts

#### Scenario: Report payload is still unavailable
- **WHEN** the user opens a job-specific report route and the job summary is found but the generated report payload is not available
- **THEN** the system shows a report-unavailable or still-generating state rather than blocking indefinitely on visual overlay artifacts

#### Scenario: Overlay artifact fails while report payload is available
- **WHEN** the user opens a job-specific report route and a tracking or pose overlay artifact would fail to load
- **THEN** the report page still renders from the available report payload unless the selected report explicitly requires that artifact

### Requirement: Report source metadata
Report detail pages SHALL show enough context for users to understand which match or analysis job produced the report.

#### Scenario: User views a job-specific report
- **WHEN** a report detail page renders completed job data
- **THEN** the page displays match metadata such as uploaded file label, venue, date, player context, report id, or job id where available

#### Scenario: User views a demo report
- **WHEN** a report detail page renders local sample data
- **THEN** the page preserves a subtle sample or demo context instead of implying the result came from an uploaded video

### Requirement: Result-scoped report navigation
Report detail pages SHALL behave as lower-level destinations reached from completed video analysis results or task management rather than as primary top-navigation peers.

#### Scenario: User opens a report from completed result
- **WHEN** the user selects movement or diagnosis from a completed job's status rail, report tabs, or task card
- **THEN** the system opens the matching job-specific report detail route with the completed task context preserved

#### Scenario: User returns from report to video result
- **WHEN** the user activates the report page's return action
- **THEN** the system navigates back to the associated job-specific visual analysis page when a job id is available

#### Scenario: User opens sample report route directly
- **WHEN** the user navigates directly to an existing sample report route without a job identifier
- **THEN** the system continues to render structured local mock report data with subtle sample context

### Requirement: 报告作为 Workspace view

报告 SHALL 作为 LibraryItemWorkspace 的「报告」view 呈现，而非独立的一级页面对象；报告天然属于某一场比赛/训练。报告承载按四层职责划分：`ReportContent`（useJobReport 驱动的数据与业务状态：loading/failed/canceled/no report）→ `PbReportContent`（Pb 视觉内容，NO Drawer、NO navigation）→ `PbVisionReportLayout`（仅 standalone 的 chrome：PbPlayerDrawer / Drawer expander / 独立间距）。Workspace 报告 view SHALL 直接以 `ReportContent` + `PbReportContent` 承载；`PbVisionReportLayout` SHALL 只用于独立报告路由。

#### Scenario: 报告进入统一工作区
- **WHEN** 素材存在分析结果且有报告
- **THEN** 用户 SHALL 在工作区的「报告」view 查看该比赛/训练的报告
- **AND** 报告中心不作为用户一级页面展示

#### Scenario: PB 风格组件在报告 view 中复用
- **WHEN** 素材存在权威分析结果
- **THEN** 报告 view SHALL 复用 PB 风格视觉组件（Skill Card / Player Header / Court Coverage / Serves & Returns / Coach Insight / Filter）
- **AND** SHALL NOT 展示报告独立抽屉栏或专属导航体系
- **AND** Workspace 报告 view SHALL 渲染 `ReportContent` + `PbReportContent`，不经过会挂载 Drawer / 独立间距的 `PbVisionReportLayout` 整页

#### Scenario: 报告职责四层不混
- **WHEN** 报告 view 因任务数据缺失进入 loading/failed/no report
- **THEN** 该状态的判定与文案 SHALL 由 `ReportContent` 负责
- **AND** `PbReportContent` SHALL 只在拿到 report data 后渲染视觉内容
- **AND** `PbVisionReportLayout` 的 Drawer/expander 逻辑 SHALL NOT 出现在 workspace 报告 view 中

#### Scenario: 独立报告路由保留
- **WHEN** 用户访问独立报告路由（`/reports/:type` 或 `/analysis/:jobId/reports/:type`）
- **THEN** 系统 SHALL 继续以既有方式渲染报告（`PbVisionReportLayout` 新布局含 drawer 或 legacy），不因 Workspace 重构而破坏

#### Scenario: 真实任务不得伪造 mock 结论
- **WHEN** 报告 view 面向真实任务
- **THEN** 无权威数据支撑的分析结论 SHALL NOT 被伪造填充
- **AND** 相关数据必须服从 performance-insights 证据约束

### Requirement: Performance report detail page

系统 SHALL 提供 `/analysis/{job_id}/reports/performance` 报告类型作为真实任务的默认用户结果页，首屏展示本场表现总结（整体状态、最明显优势、首要问题、下一次最值得练、数据可信度摘要），随后按序展示六维表现状态卡、关键 findings、数据证据、典型视频片段、训练建议与下次训练目标。

#### Scenario: 用户打开 performance 报告

- **WHEN** 用户从完成任务入口打开 `/analysis/{job_id}/reports/performance`
- **THEN** 页面从该 job 的报告 payload（含 `performanceInsights`）渲染总结、维度状态、findings 与训练目标
- **AND** 页面 SHALL NOT 因大型 overlay artifacts 未加载而阻塞渲染

#### Scenario: 维度状态展示

- **WHEN** 页面渲染六维表现
- **THEN** 每个维度 SHALL 展示状态（待改进 / 稳定 / 数据有限 / 暂不评价）与证据充分度标识
- **AND** SHALL NOT 展示数值技能评分

#### Scenario: 球员切换

- **WHEN** 任务为双打且存在多名 subjects
- **THEN** 页面 SHALL 提供 P1–P4（及 team_near / team_far）切换，切换后 findings、证据与训练目标随之过滤
- **AND** 每条 finding SHALL 绑定其 `subject_id`，MUST NOT 使用未映射的真实姓名指代

#### Scenario: Finding 跳转视频证据

- **WHEN** 用户点击某条 finding 的"查看视频证据"
- **THEN** 系统 SHALL 跳转到 `/analysis/{job_id}/vision?t={start_ms}`（毫秒），定位到该 finding 的 `evidence_windows` 起始时间
- **AND** finding 无时间窗时该入口 SHALL 显示为不可用而非跳转到错误时间

#### Scenario: 算法候选事实区

- **WHEN** 任务存在 ball trajectory / bounce candidate artifacts
- **THEN** performance 报告 SHALL 在独立的"算法候选事实"区展示候选数量与 confidence 摘要及片段入口
- **AND** 该区内容 MUST NOT 进入 performance findings，MUST NOT 表述为落点统计或战术结论

#### Scenario: demo 任务访问 performance 路由

- **WHEN** 用户对 demo 任务打开 performance 报告路由
- **THEN** 系统 SHALL 展示带样例标识的 demo 报告或重定向到 demo 报告页
- **AND** MUST NOT 将 demo 数据呈现为真实任务洞察

