## Why

当前双摄同步锚点工作台只能把草稿保存在浏览器并下载 JSON，用户仍需离开系统运行 CLI、再把结果放回录制目录；同时分析创建页无法区分“人工锚点已确认”和“仅有自动降级估算”。这使同步质量状态不透明、操作链路繁琐，也导致同一 CaptureTake 创建新分析时无法可靠复用已经完成的标注。

## What Changes

- 将同步锚点标注建模为双摄 CaptureTake 的可选前置任务，而不是某一次 AnalysisJob 的临时操作。
- 在系统内完成锚点草稿保存、提交、后端拟合、质量校验和确认，不再要求下载 JSON 或手工运行 CLI。
- 为 CaptureTake 暴露明确的同步锚点状态、来源、质量、覆盖率、残差、版本和失效原因，区分人工确认与自动降级估算。
- 在双摄分析素材检查阶段根据录制级状态显示“无需人工锚点”“需要标注”“标注未完成”“人工锚点已确认”或“仅自动估算”等提示，并按策略门控后续步骤。
- 锚点确认后自动返回原分析向导；同一 CaptureTake 后续创建分析时直接复用已确认的校准。
- 当关联视频、camera identity 或 timing provenance 发生变化时使既有人工确认失效；仅创建新分析、调整分析窗口或更换算法不使其失效。
- 保留 anchors JSON 下载作为诊断/导出能力，但不再作为主流程的完成方式。

## Capabilities

### New Capabilities

- `sync-anchor-workflow`: 定义 CaptureTake 级同步锚点状态、内置标注草稿、提交确认、复用、版本与失效规则。

### Modified Capabilities

- `dual-camera-timestamp-alignment`: 将人工多锚点拟合纳入后端 API 主流程，并要求持久化原始锚点、拟合结果和质量摘要。
- `multiview-analysis-setup-page`: 将同步锚点状态变为素材检查阶段的动态前置任务和显式门禁，并支持工作台完成后恢复向导。
- `capture-take-unified-timeline`: 要求同步锚点及校准作为 CaptureTake 的版本化时间线资产被查询、复用和失效管理。

## Impact

- 后端新增 CaptureTake 同步锚点状态、草稿与确认 API，以及复用现有拟合函数的服务层。
- CaptureTake 详情或专用状态响应增加同步校准摘要；时间线目录持久化原始 anchors、确认元数据及 `sync_calibration.json`。
- 双摄分析 preflight 改为消费录制级状态，不再仅依据文件是否存在判断人工确认。
- 前端调整 `MultiViewAnalysisSetupPage`、`SyncCalibrationWorkbenchPage`、`analysisClient` 和相关类型、路由返回上下文。
- 增加服务、API、状态机、失效判定、前端交互和跨分析复用测试；现有 CLI 保留为维护与兼容工具。
