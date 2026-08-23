## Why

当前双摄协同分析仍复用单摄的 12 个阶段列表，并把 `multiview-joint` 作为额外阶段追加到列表末尾，导致“报告生成”在视觉上先于“双摄协同跟踪”，阶段状态与真实执行顺序不一致。总进度还按阶段数量平均估算，实际双摄跟踪已接近完成时，页面仍可能只显示 30% 左右，用户无法判断任务是否正常推进。

现在需要建立按双摄执行模式区分的统一进度状态机，让后端、任务 API 和前端进度页面共享同一套可解释的阶段顺序、状态转换和进度聚合规则。

## What Changes

- 为 `single_view`、`late_fusion_v1` 和 `joint_tracking_v2` 定义稳定且互不混淆的顶层阶段图。
- 将双摄同步检查、A/B 机位处理、协同跟踪、融合、指标重算、可视化和报告生成按照真实执行顺序表达，禁止把双摄专用阶段追加到单摄阶段列表末尾。
- 统一阶段状态转换规则：同一时刻最多一个顶层阶段为 `active`，后续阶段保持 `pending`，阶段完成后才允许进入下一阶段；明确 `done`、`skipped`、`failed` 和 `canceled` 的语义。
- 重新定义总体进度聚合：进度必须单调递增，并反映当前执行模式和实际阶段权重；late fusion 的 Parent 需要汇总 A/B 子任务进度，joint tracking 需要覆盖协同跟踪和后处理阶段。
- 扩展任务状态 API 的进度遥测，使前端能够显示当前真实阶段、阶段详情、阶段进度、阶段耗时以及必要的 A/B 子进度，而不是依赖单摄阶段的占位状态。
- 更新任务状态页的阶段条和双摄子进度展示，隐藏空的 `viewRuns`，并保证运行中、失败、取消和完成状态的页面顺序与后端一致。
- 增加后端状态机、进度聚合、API 序列化和前端渲染回归测试，覆盖历史任务兼容、两种双摄执行模式以及报告生成顺序。

## Capabilities

### New Capabilities

- `multiview-progress-state-machine`: 定义双摄不同执行模式下的阶段图、状态转换、进度聚合、遥测契约和前端展示语义。

### Modified Capabilities

- `analysis-job-orchestration`: 修改阶段遥测和总体进度规则，使其支持模式化阶段图、真实阶段顺序和单调进度。
- `multiview-analysis-orchestration`: 修改 Parent 与 A/B 子进度的展示契约，保证编排状态能够投影为可解释的运行阶段。
- `multiview-execution-mode`: 为 `late_fusion_v1` 与 `joint_tracking_v2` 补充各自的阶段语义和终态顺序要求。

## Impact

- 后端：`AnalysisStage`/`AnalysisJobSummary` 数据契约、`JobStore` 阶段合并与进度计算、双摄 Coordinator/Executor/Composer，以及任务状态 API。
- 前端：`AnalysisJobPage`、`JobStageStepper`、双摄任务进度卡片、API 类型和相关测试。
- 持久化兼容：历史任务仍需可读取；旧的单摄任务不能因为新增阶段字段而改变状态或渲染。
- 运行行为：不改变 YOLO、RTMPose、球员跟踪、融合和报告算法本身，只调整执行状态的记录、聚合和展示。
