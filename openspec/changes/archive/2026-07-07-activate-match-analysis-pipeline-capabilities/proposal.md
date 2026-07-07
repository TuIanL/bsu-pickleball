## Why

项目已经具备球轨迹与弹跳点后处理引擎、分析 artifact 合同和若干配置入口，但现有 spec 与 pipeline 仍保留“球识别/球轨迹/事件分析不属于当前流程”的阶段锁。现在需要把这些历史限制改成可配置、可诊断、可逐步扩展的真实分析能力，避免后续功能被旧 MVP 边界反向约束。

## What Changes

- 将当前“不得生成或消费球相关 artifact”的限制改为“默认可关闭、配置启用、缺依赖时明确 unavailable/skipped”的激活策略。
- 将 `ball-trajectory-and-bounce-engine` 从独立测试引擎接入真实 `AnalysisPipeline`，在启用球检测/弹跳检测且输入满足时生成球检测、原始轨迹、清洗轨迹和弹跳候选 artifact。
- 扩展 multi-target 感知合同，使 `ball` 成为可支持目标类别；`paddle` 继续作为后续可扩展目标，不在本 change 强制接入。
- 让分析结果、artifact API、可视分析工作台和报告页面在 artifact 存在时展示球轨迹、弹跳候选和相关状态，在 artifact 缺失、跳过或失败时显示真实状态。
- 保留语义边界：本 change 不承诺完整 rally segmentation、击球分类、得分判定或战术结论；这些仍需后续专门能力支持。
- 更新文档和配置说明，避免“future/out of scope/MVP 暂不生成”等措辞被理解为永久禁用。

## Capabilities

### New Capabilities

- `match-analysis-pipeline-capabilities`: 定义真实比赛分析 pipeline 的能力激活原则、配置门控、状态降级和“事实 artifact 优先、语义结论后置”的扩展边界。

### Modified Capabilities

- `ball-tracking`: 从禁用球分析改为可配置启用球检测、轨迹与弹跳候选 artifact，并保留未启用/无模型/无检测时的降级状态。
- `multitarget-perception`: 将 `ball` 纳入可支持目标类别和检测记录合同，允许 player 与 ball 在同一检测 artifact 中共存。
- `ball-trajectory-and-bounce-engine`: 移除“保持断开当前 pipeline”的限制，要求引擎可被真实分析任务调用并保持独立单测能力。
- `analysis-artifacts`: 明确新增球相关 artifact 在启用 pipeline 后应由真实任务写入并被 `AnalysisPipelineResult` 引用。
- `visual-analysis-workspace`: 允许真实任务在 artifact 可用时加载球轨迹、弹跳候选和球层状态，而不是一律隐藏球分析。
- `interactive-performance-report`: 允许报告展示由真实 artifact 支撑的球轨迹/弹跳候选事实，同时继续避免未实现的击球、落点、战术和比分结论。
- `serve-start-detection`: 允许发球候选检测在未来可用时消费球轨迹/弹跳候选作为辅助信号，但不得因此推断完整回合语义。

## Impact

- 后端：`AnalysisPipeline`、pipeline stage 记录、`AnalysisPipelineResult.artifacts`、artifact 路径/API、配置读取、球检测适配器、球轨迹与弹跳引擎接入。
- 前端：可视分析工作台的 overlay/layer 状态、artifact 加载、报告模块可用性判断和真实/示例数据区分。
- 文档与模型资产说明：`models/README.md`、`storage/README.md` 和相关环境变量说明需要从“保持禁用”更新为“可配置启用并诊断缺失依赖”。
- 测试：需要覆盖默认关闭、启用但缺模型、启用并生成 artifact、artifact API 读取、前端降级显示等路径。
