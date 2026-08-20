## ADDED Requirements

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

## MODIFIED Requirements

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
