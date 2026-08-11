## Why

双摄同步分析页面已经允许用户选择分析时间窗口，并将 `clipStartMs/clipEndMs` 发送到后端，但当前窗口语义没有覆盖所有执行路径。默认的 late fusion 路径仍可能在生成叠加视频时读取全片，`joint_tracking_v2` 更会直接从视频开头分析到结尾，导致短窗口验证失去意义并产生不必要的计算成本。

本 change 用于把双摄分析窗口从“请求参数已接收”补齐为端到端可验证的执行契约，确保跟踪、同步、融合、指标、可视化和进度展示都遵守同一窗口语义。

## What Changes

- 统一双摄分析窗口的公共时间轴语义：窗口以 reference view 的 take 时间轴表示，secondary view 通过权威同步校准映射到自身媒体时间轴。
- 修复 `late_fusion_v1` 的分析产物生成，使叠加视频和相关可视化不再无条件读取整段源视频。
- 为 `joint_tracking_v2` 增加窗口起止帧、预热区间和 secondary 同步映射，禁止 joint tracking 默认分析整段视频。
- 保留必要的 pre-roll/post-roll 上下文，但指标、融合样本、统计结果和用户可见分析范围只计入请求窗口。
- 修正 child 的分析范围元数据、任务进度分母和结果诊断，使任务状态不会把窗口分析误报为全片分析。
- 增加前端请求、后端编排、实际解码、叠加视频和 joint tracking 的回归测试；无窗口时继续保持全场分析行为。

## Capabilities

### New Capabilities

无。本 change 补齐已有分析窗口能力，不新增独立用户能力。

### Modified Capabilities

- `analysis-job-orchestration`: 明确多视角 Parent/Child 的窗口持久化、窗口范围与预热范围，以及进度和诊断语义。
- `multiview-analysis-orchestration`: 明确窗口在 Parent、late fusion child 和 joint Parent 中的传播与同步换算。
- `analysis-job-executor-dispatch`: 要求 SingleView、late fusion 和 joint tracking 执行体都实际遵守窗口，并约束可视化产物范围。
- `recording-analysis-bridge`: 明确双摄录制分析页面选择的公共时间窗口必须影响最终分析和叠加输出。

## Impact

- 前端：`MultiViewAnalysisSetupPage`、双摄分析请求契约和任务进度/范围展示。
- 后端：`MultiViewAnalysisCoordinator`、`SingleViewAnalysisExecutor`、`MultiViewJointExecutor`、`MultiViewJointRun`、`AnalysisPipeline` 和 `OverlayVideoWriter`。
- 数据契约：沿用现有 `clipStartMs/clipEndMs` 字段，补充窗口诊断、解码范围和有效处理帧数的可追溯信息；不改变同步校准、Canonical Timeline 或融合身份语义。
- 测试：前端请求测试、编排测试、合成视频范围测试、joint tracking 窗口测试和无窗口兼容性测试。
