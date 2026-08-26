## Context

当前后端已经在真实分析 pipeline 中从 canonical 球员场地轨迹生成 `StructuredVisualizationData`，其中包含 `heatmaps`、`scatter_plots` 和 `zone_stats`，并通过 `GET /api/analysis/jobs/{job_id}/visualization-data` 暴露。视频分析页已经读取该接口并渲染“区域空间热力图”。

报告页的 `PbCourtCoverage` 走的是另一条证据路径：`usePlayerReportEvidence` 会读取报告、球路、发球事件、canonical events 和 metric snapshot，但没有读取结构化可视化 artifact；场地覆盖组件还将位置热力图网格包装成 `heatmaps.players` 后交给只接受 `zone_stats` 的 `StructuredZoneHeatmap`，因此真实报告页无法显示区域统计。

工作区当前把“报告可用”近似为“存在 completed Job 和 result manifest”。这无法区分“任务完成但没有有效球员轨迹/运动指标/区域统计”和“确实可以生成报告”的情况。该变更需要同时处理报告数据加载、证据归属、工作区 Tab、视频分析页报告动作和直接报告路由。

## Goals / Non-Goals

**Goals:**

- 让报告页从现有结构化可视化 artifact 消费真实 `zone_stats`，不新增第二套区域统计算法。
- 让区域空间热力图、三区占用率、NVZ 占用率、平均站位距厨房线和数据充分性提示保持 canonical player 身份与 provenance。
- 建立可复用的纯函数报告有效性判断，区分 loading、available、unavailable 和明确原因。
- 当没有有效报告证据时，工作区顶部“报告”Tab、视频分析页下级报告入口和任务结果页报告入口均不可点击；直接 URL 也进入明确空态。
- 保持历史任务、旧 PNG、旧报告 schema 和显式 demo 路由兼容。

**Non-Goals:**

- 不重新设计球员检测、轨迹投影、区域分区或 KCR 计算算法。
- 不把位置网格热力图与区域占用热力图合并为一个数据结构；两者继续分别消费 `heatmaps` 和 `zone_stats`。
- 不改变球网场景标定、双摄同步、`displayViewId` 或 canonical frame 语义。
- 不删除 `/visualization-data`、PNG manifest 或历史 artifact；不强制为旧任务补算缺失数据。
- 不把动作诊断、击球、落点、胜负等当前未生成的语义标记为可用报告内容。

## Decisions

### 1. 报告页统一消费 `StructuredVisualizationData`

报告加载路径复用现有 `getStructuredVizData(jobId)`，与任务、报告和 pipeline result 的读取并行执行。结构化数据进入 `PlayerReportEvidenceSources.visualization`，由 `buildPlayerReportEvidence` 依据 selected canonical player 提取区域统计和位置热力图证据，组件只消费 `PlayerReportEvidence`。

这样可以满足报告指标单一来源和 provenance 约束，也避免 `PbCourtCoverage` 直接读取散落的 `report` 或再次请求 artifact。`zone_stats` 是区域空间热力图的唯一数据源；`metrics.heatmap` 或 `heatmaps.visual_grid` 不得被当作区域占用数据。

### 2. 在证据层增加区域统计证据

`PlayerReportEvidence.courtCoverage` 增加区域统计的 `EvidenceValue`。当结构化数据含有与 selected canonical player 匹配的 `zone_stats.players` 时，返回 `available`，并携带 `structured_visualization` provenance；当接口 404、加载失败、没有该球员或区域数组为空时，返回 `unavailable`/`failed` 及可读原因。

`PbCourtCoverage` 使用该区域统计证据构造仅含当前球员 `zone_stats` 的 `StructuredVisualizationData` 视图并交给 `StructuredZoneHeatmap`。真实 job 缺数据时显示 `PbEvidenceUnavailable`，不得显示看起来像真实结果的静态球场占位图；demo 路由仍由 demo 数据契约单独管理。

### 3. 报告有效性以“有效证据”而非“任务存在”为准

新增共享的纯判断函数，至少检查：

- Job 已完成且 result manifest 已读取；
- 至少存在一类可用于报告的真实证据：有效 canonical 场地轨迹点、有效运动指标条目，或状态为 available 且可读取的结构化位置可视化 artifact；
- 不把空数组、全为非有限值的坐标、仅有失败/跳过状态的 artifact 或 demo fallback 计为有效证据。

只要存在一类真实运动证据，报告整体可以打开，缺失的单个模块在报告内部显示 unavailable；只有完全没有有效证据时，报告整体才不可用。这样不会因为区域热力图暂缺而锁死仍有有效移动距离的报告。

该判断优先消费现有 `AnalysisPipelineResult` 的 `tracks`、`metrics` 和 `artifacts` 字段，不新增必须同步的后端 availability API。未来若需要更细的报告类型级门控，可在不破坏本判断函数的情况下增加可选报告能力摘要。

### 4. 所有报告入口共享同一门控

`LibraryItemWorkspace` 的 `report` capability、`VisionPage` 的下级报告动作、`AnalysisJobPage` 的完成态按钮和嵌入式 `onSelectView("report")` 均消费同一有效性判断及原因。入口保留可见性，但在 unavailable/loading 时使用原生 `disabled`、禁用样式和可读 `title`；事件处理也必须有 guard，避免通过程序化导航绕过按钮禁用。

直接访问 `/analysis/:jobId/reports/:type` 时，报告内容层再次执行 fail-closed 检查。Job 报告没有有效证据时渲染“暂无有效报告数据”状态，并保留返回当前素材/任务的路径；无 job 的显式 demo 路由仍可渲染 demo 内容并显示“演示数据”。

### 5. 多摄数据继续使用 canonical 结果

区域统计从 Parent/当前 selected Job 的 structured artifact 读取，始终使用 `Player_N` canonical identity 和统一 canonical court frame；前端展示视角切换不参与区域统计计算，也不使用某一路视频像素坐标重建热力图。这样与现有 multiview display-view 和 metric scene calibration 变更保持解耦。

### 6. 兼容旧任务和加载失败

`getStructuredVizData` 404 或旧任务没有 structured JSON 时不使整份报告请求失败。若报告还有有效移动证据，报告继续打开，区域卡显示不可用；若所有报告证据均缺失，报告入口置灰。视频分析页原有 PNG fallback 继续保留，报告页不从 PNG 反推 `zone_stats`。

## Risks / Trade-offs

- **[报告页增加一次结构化 artifact 请求]** → 与已有 job/report/result 请求并行，并在 evidence hook 内按 job 生命周期复用结果，避免组件级重复请求。
- **[任务有移动指标但没有区域统计]** → 报告整体仍可用，只有“场地覆盖”卡显示 unavailable，避免把模块缺失误判为整份报告无效。
- **[历史任务没有 structured JSON]** → 保留旧 PNG 和视频分析页降级；报告页明确显示区域统计不可用，不猜测区域占用。
- **[不同入口门控逻辑漂移]** → 只允许共享纯函数作为 capability 来源，并为 Tab、下级动作、完成页按钮和直接 URL 增加一致性测试。
- **[canonical player 映射不完整]** → 复用现有 canonical identity resolver；未能映射的球员返回 unavailable，不按展示名或尾号猜测。
- **[result manifest 的数组存在但内容为空]** → 有效性判断检查真实条目和有限坐标/状态，而不是仅判断字段存在或数组长度。

## Migration Plan

1. 扩展前端 evidence 类型和转换函数，接入 `getStructuredVizData`，完成报告页区域热力图真实渲染。
2. 提取共享 report capability 判断，先接入 `LibraryItemWorkspace` 顶部 Tab，再接入视频分析页、任务完成页和嵌入式导航 guard。
3. 为直接报告 URL 增加无有效证据空态，保留 demo 路由和历史报告兼容逻辑。
4. 增加前端单元/组件测试、API artifact 缺失测试和多入口一致性测试；使用真实 job fixture 验证 canonical player、区域统计和 unavailable 原因。
5. 若新 evidence 读取或区域渲染异常，可关闭报告页区域模块消费，继续使用旧报告其他可用指标；不删除或改写已有 artifact。

## Open Questions

- 当前没有阻塞实现的开放问题。首版采用“任一真实运动证据即可开放整份报告、缺失模块单独降级”的门控粒度；未来若需要按“表现/移动/诊断”分别禁用，可另建报告类型级 capability 变更。
