## Why

项目需要持续增加球拍识别、完整挥拍过程、动作分类以及动作与球路、落点和比赛上下文融合的击球语义。当前完整分析入口将检测、跟踪、姿态、球路、指标和报告耦合，短片实验仍可能触发整场切分或整体重试，难以定位变更影响、复用计算结果并验证新能力。

本次建立可持续扩展的分析运行骨架：完整能力地图先明确，算法逐步适配；单摄和双摄共用局部验证入口，完整产品分析继续保持 legacy 行为。

## What Changes

- 建立静态 Capability/Implementation 注册、类型化输入输出和冻结的 analysis-plan.v1；明确能力、算法实现、产物 schema、动作标签体系的独立版本。
- 复用现有 AnalysisJob、SQLite 控制面和 Worker。新增 analysisEngine=modular_v1 路径，历史请求默认 legacy_v1；模块结果直接返回运行清单，不隐式生成指标、洞察或报告。
- 规划器先解析实现、依赖、窗口和采样，再评估缓存；执行时绑定真实上游产物并重新核验。计划指纹排除随机 ID、时间和动态缓存状态。
- 建立不可变 Artifact、独立缓存索引及跨 Job 引用/血缘；支持损坏后同键重新生产、上游保留、受租约保护的原子发布和节点级恢复。
- 定义单摄/双摄时间、空间、身份和冻结上下文契约；引入有界窗口扩展、事件选择规则和截断状态，禁止隐式整场 fallback。
- 区分持久化产物、运行资源和上下文。v1 采用节点间产物边界及有界重新解码，不承诺跨节点单次解码；现有双摄 joint 内部协同保持不变。
- 首批真实适配 player.detect、ball.detect、pose.sequence；提供共用 CLI 和最小 API，用真实短片验证单摄与双摄时间映射、缓存、失败恢复和模型按需加载。
- 为球拍、人拍关联、运动证据、挥拍阶段、动作识别、Shot/Rally 语义和战术分析定义扩展位置及证据关联契约。本期不实现这些未来模型，也不将未实现能力伪装为可运行节点。
- 修改既有 Executor 返回、任务成功/进度和 trace 规格，显式区分 legacy 与 modular，消除新增规格与现有 MUST 条款的冲突。
- 不引入动态插件、分布式工作流平台，不调整现有算法阈值、身份门槛或 Shot/落点业务定义。

## Capabilities

### New Capabilities

- analysis-capability-runtime：静态注册、实现选择、类型化依赖、稳定计划指纹和全能力扩展地图。
- analysis-artifact-lineage：不可变产物、输入级缓存、缓存版本指针、跨任务引用、血缘和存储可用性。
- analysis-local-validation：单摄/双摄共用的 plan/run/inspect、最小 API、资源隔离及真实验收证据。
- analysis-evidence-association：主体与事件的版本化关联、动作属性和语义假设，保留歧义且禁止反写源证据。
- analysis-window-planning：依赖窗口反向传播、有限扩展预算、采样、输出选择和边界截断。
- analysis-context-contract：媒体/PTS 身份、机位、坐标/单位、主体命名空间和按消费范围绑定的冻结上下文。
- analysis-result-publication：节点执行状态、结果可用性/质量、发布事务、控制信号、恢复及资源生命周期。

### Modified Capabilities

- analysis-job-executor-dispatch：按 engine 分派返回 legacy 结果或 modular 清单，保留 legacy 单摄/双摄协议和业务行为。
- analysis-job-orchestration：按 engine 定义成功条件、进度与去重，持久化冻结计划并复用既有租约/取消/中断机制。
- analysis-run-trace：legacy v1 保持可读，modular v2 承载节点尝试、缓存和发布记录，并沿用失败证据保真。
- match-analysis-pipeline-capabilities：将固定阶段、严格模式和全量产品签名限定于 legacy，模块按目标和消费范围运行。
- pose-estimation-engine：保留原跟踪/球场过滤路径，新增 observation-scoped、无标定前提的模块姿态合同。
- analysis-artifacts：区分 Job 私有文件与共享不可变产物，保留旧固定字段/API 并使用新通用引用。
- analysis-task-management：模块任务打开运行清单，删除遵守共享引用与来源 pin，避免清理目录使消费者失效。

## Impact

主要新增 backend/app/analysis_runtime/ 和 backend/app/analysis_capabilities/；接入现有 schemas/analysis.py、analysis_executor_dispatch.py、job_orchestration.py、analysis_control_plane.py、storage_service.py、routes_analysis.py 和完成回调。vision 算法继续留在原目录，AnalysisPipeline、AnalysisArtifacts 和历史 API 保留。

SQLite 仅增加计划/节点记录及产物/缓存/引用索引，大型 payload 留在受控文件系统。前端仅增加模块任务的最小类型、状态和清单读取，不重构报告。

本提案基于 2665bc3。与仍活跃的四人身份 change 分离：可先实施独立契约、规划器和检测适配；触及共享 executor/身份输出前固定基线并协调文件归属。结构、集成、真实媒体与算法质量分别验收；依赖或素材缺失不计为真实推理通过。本轮仅创建提案，不实现应用代码。

