## Why

当前真实分析 pipeline 已经生成 `structured visualization data`，其中包含球员区域占用、NVZ 占用率和距厨房线距离，但报告页的“场地覆盖”卡仍未读取该 artifact，因而显示空白/占位球场，无法把真实分析结果带给用户。与此同时，报告入口目前主要依据“任务完成且存在 result manifest”开放；当任务没有有效球员轨迹、指标或区域统计时，用户仍可以进入没有有效内容的报告页。

本变更统一报告页的数据来源和可用性判断，让真实区域空间热力图可追溯地进入报告页，并在没有有效报告证据时将报告入口置灰、禁用且给出明确原因。

## What Changes

- 报告页复用现有 `/api/analysis/jobs/{job_id}/visualization-data` 结构化 artifact，直接消费 canonical `zone_stats`，渲染真实的区域空间热力图、三区占用率、NVZ 占用率、站位距离和数据充分性提示。
- 将结构化可视化 artifact 纳入报告证据加载链路，保留来源、球员身份和不可用原因，禁止把位置网格误当作区域统计或回退到演示数据。
- 建立统一的报告有效性门控：任务未完成、报告缺失、没有有效球员空间/运动证据或关键 artifact 不可读时，报告视图标记为不可用。
- 比赛库工作区顶部的“报告”标签在报告不可用时保持可见但置灰并设置 `disabled`，不可进入；正在核对结果时显示加载/禁用状态。
- 视频分析页的“下级报告”、任务完成页报告按钮和直接报告 URL 复用同一门控语义，避免从其他入口绕过置灰状态。
- 对真实 job 保持 fail-closed：无有效数据时显示明确空态和原因，不展示样例报告或伪造指标；显式 demo 路由仍可保留样例数据。

## Capabilities

### New Capabilities

- 无。本变更复用并扩展现有分析 artifact、球员报告证据和工作区导航能力。

### Modified Capabilities

- `player-zone-heatmap`: 区域空间热力图除视频分析页外，还必须能在真实报告页消费同一份 canonical `zone_stats`，并在 artifact 缺失或无有效球员点时显式降级。
- `player-report-evidence`: 报告证据加载器必须读取结构化可视化 artifact，按 canonical player 关联区域数据并保留 provenance；不得使用未经证明的占位热力图。
- `interactive-performance-report`: 真实报告必须只展示有效 pipeline 证据；区域空间热力图来自真实 artifact，缺少有效证据时显示不可用状态而不是 demo 内容。
- `library-item-workspace`: 顶部“报告”标签的 capability 判断必须从“有完成任务”收紧为“有有效报告证据”，不可用时置灰禁用。
- `visual-analysis-workspace`: 视频分析页的报告入口必须与工作区报告标签共享同一有效性判断，并在无有效报告时禁用或显示不可用原因。

## Impact

- 前端：`ReportContent`、`PbReportProvider`、`PbCourtCoverage`、`usePlayerReportEvidence`、`LibraryItemWorkspace`、`VisionPage`、`AnalysisJobPage` 及相关导航/空态组件。
- 后端/API：复用已有结构化可视化数据 API；如需补充报告可用性摘要，只增加向后兼容的可选字段，不改变现有 artifact 路径和历史任务读取方式。
- 数据契约：统一 `StructuredVisualizationData.zone_stats`、canonical `Player_N` 身份和 `EvidenceValue` 的 available/unavailable 语义。
- 测试：增加真实区域热力图报告渲染、无轨迹/无区域数据禁用报告入口、artifact 失败降级、历史 job 兼容和多入口一致性测试。
