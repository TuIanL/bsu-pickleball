# analysis-job-orchestration Specification

## Purpose

定义分析任务的可持久生命周期与编排契约：API 与 Worker 执行分离、本地队列与优先级、资源限制、取消、超时重试与幂等提交，并覆盖源 FPS 传递、时间裁剪与预热区间、任务签名绑定正式切分配置及 prerequisite job 的恢复与取消。
## Requirements
### Requirement: Durable analysis job lifecycle

`canonicalStatus` SHALL 管理 `queued / running / succeeded / failed / canceled / interrupted` 六态任务生命周期；`interrupted` 表示本次 Worker 执行失联或被进程中断，不等价于 Pipeline 算法失败。系统 MUST 使用独立维度 `orchestrationStatus` 表达多视角 Parent 编排，不得将 `waiting_sources` 等编排状态塞入 `canonicalStatus`。任务摘要 SHALL 持久化 Worker lease、heartbeat 和 interruption 字段，并兼容读取没有这些字段的历史任务。

用户取消、execution lease 丢失与阶段超时是**控制信号**，SHALL 表达为 `canceled` 或 `interrupted` 等非算法失败结论，MUST NOT 被归因为 `internal_defect`。算法阶段抛出未归类的非控制信号异常时，才 SHALL 归为 `internal_defect`。

#### Scenario: Job is created

- **WHEN** 有效的真实分析请求被接受
- **THEN** 系统 SHALL 在返回前持久化 queued job、创建时间、排队时间、输入引用、分析配置、当前阶段、初始进度和初始 Worker liveness 字段

#### Scenario: Worker starts a job

- **WHEN** Worker 领取 queued job
- **THEN** 系统 SHALL 原子地标记 job 为 running，记录开始时间、Worker 身份、运行实例 ID、领取时间和首次 heartbeat
- **AND** SHALL 防止另一个 Worker 领取同一个 job

#### Scenario: Job is interrupted

- **WHEN** running job 的 Worker heartbeat 超时或服务启动确认其执行进程已中断
- **THEN** 系统 SHALL 将 job 标记为 `interrupted`
- **AND** SHALL 持久化中断时间、稳定中断原因和最后已知阶段/进度

#### Scenario: Job succeeds

- **WHEN** legacy_v1 的所有必需分析阶段和报告生成完成
- **THEN** 系统 SHALL 标记 job 为 succeeded，记录完成时间，保存结果/报告 artifact 引用，并保留阶段遥测

#### Scenario: Job fails

- **WHEN** 不可恢复的阶段错误发生
- **THEN** 系统 SHALL 标记 job 为 failed，记录完成时间、稳定错误码、用户错误信息和分离的内部诊断信息

#### Scenario: Job is canceled

- **WHEN** queued 或 running job 接收到有效取消请求
- **THEN** 系统最终 SHALL 标记 job 为 canceled，记录取消时间，停止或跳过剩余分析阶段，并在安全时清理临时文件

#### Scenario: 取消不被记为算法失败

- **WHEN** 一个运行中的 job 被用户取消，且取消信号在执行过程中被检测到
- **THEN** 系统 SHALL 记录终态为 canceled 并记录取消时间
- **AND** 失败归因 MUST NOT 为 `internal_defect`
- **AND** 若该次运行此前已发生阶段失败重试，SHALL 保留此前的失败证据

#### Scenario: 租约丢失不被记为算法失败

- **WHEN** 一个运行中的 job 的 execution lease 丢失
- **THEN** 系统 SHALL 表达租约丢失结论，SHALL NOT 归因为 `internal_defect`
- **AND** 不得把该结论表述为算法阶段失败

#### Scenario: 模块任务按目标成功
- **WHEN** modular_v1 的全部请求目标 completed/cached，或显式 best_effort 满足至少一个目标完成
- **THEN** 系统 SHALL 根据冻结失败策略记录 succeeded 与 complete/partial 完整性
- **AND** SHALL 保存运行清单与产物引用，不要求生成报告

#### Scenario: 模块目标失败但保留独立结果
- **WHEN** all_targets 的某个请求目标失败或被阻断
- **THEN** Job SHALL 为 failed，运行清单 SHALL 表达部分完成
- **AND** 独立完成产物 SHALL 保留并可检查

### Requirement: Stage telemetry

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

阶段遥测 MUST 保持既有 `AnalysisStage` 结构，并由当前分析模式的规范化阶段图生成。`single_view` MUST 继续使用既有单摄稳定阶段。需要正式双摄回合切分的 `late_fusion_v1` 与 `joint_tracking_v2` Parent MUST 将“回合自动切分”作为第一个聚合阶段；它先于素材与同步检查以及任一 A/B 或 joint 视觉执行。后续阶段仍分别按“素材与同步检查 / A 机位视觉分析 / B 机位视觉分析 / 多视角融合 / 指标重算 / 可视化输出 / 报告生成”和“素材与同步检查 / 双摄协同跟踪 / 双摄球路分析 / 指标重算 / 可视化输出 / 报告生成”顺序表达。双摄子阶段进度 MUST 经 `viewRuns` 暴露，运行中应反映最近可用的 child 或内部 `ViewRun` 状态；双摄专用阶段 MUST NOT 被追加到单摄阶段列表末尾。

总体进度 MUST 使用当前阶段图的稳定权重和阶段进度聚合，保持单调递增；MUST NOT 通过包含未来 `pending` 阶段的数量平均值覆盖真实的当前阶段进度。回合自动切分遥测 SHALL 从其 internal prerequisite job 投影到 public Parent。报告阶段 MUST 只能在前置分析和后处理阶段完成后开始。

阶段图 SHALL 与 Pipeline 结果中的产物状态字段表达同一个执行事实。同一阶段在阶段图中为完成时，对应的产物状态 MUST NOT 被后续赋值覆盖为 `skipped`、`unavailable` 或 `failed`。阶段状态与产物状态不一致时，系统 SHALL 以实际执行事实为准并使二者一致。

#### Scenario: Parent 显示回合自动切分
- **WHEN** 用户轮询一个刚创建的正式双摄 Parent
- **THEN** Parent `stages` SHALL 将“回合自动切分”显示为 active 或 pending 的第一个阶段
- **AND** A/B 视觉分析、joint tracking、融合、指标、可视化和报告 SHALL 在切分成功前保持 pending

#### Scenario: 切分失败不显示后续进度
- **WHEN** formal segmentation prerequisite 以 model/input/sync/low-evidence 失败
- **THEN** Parent SHALL 将“回合自动切分”标记为 failed 并提供稳定用户原因
- **AND** 后续双摄阶段 SHALL 不得显示 active 或 done

#### Scenario: Parent 聚合阶段
- **WHEN** 前端轮询切分成功后的 multiview Parent 摘要
- **THEN** Parent `stages` SHALL 展示与 `executionMode` 对应的完整聚合阶段和真实顺序
- **AND** `viewRuns`（`cam_1` / `cam_2` 各自的 `status / stage / progress`）在有子运行时 SHALL 提供两路子进度，运行中也反映 child 或内部 `ViewRun` 的最近状态

#### Scenario: joint tracking 不显示报告先于协同跟踪
- **WHEN** `joint_tracking_v2` 的协同跟踪阶段上报进度 95
- **THEN** `multiview-joint` SHALL 为 active，指标、可视化和报告 SHALL 仍按图保持 pending
- **AND** 总体进度 SHALL 按 joint 阶段权重聚合，而不是按单摄阶段数量平均

#### Scenario: 报告生成是终末阶段
- **WHEN** 双摄任务进入报告生成
- **THEN** 只有在切分、融合或协同跟踪、指标重算和可视化输出完成后，报告阶段才 SHALL 变为 active
- **AND** 报告完成后总体进度 SHALL 为 100

#### Scenario: 阶段完成不被产物状态二次覆盖

- **WHEN** 球轨迹阶段已在阶段图中被记录为完成
- **THEN** 对应产物状态字段 SHALL 表达该阶段已产生结果
- **AND** 产物状态 MUST NOT 在阶段记录之后被无条件改写为 `skipped`
- **AND** 前端展示的阶段状态与产物状态 MUST 一致

#### Scenario: 模块任务节点进度
- **WHEN** 查询 modular_v1 任务进度
- **THEN** 系统 SHALL 暴露独立的 nodeRuns，使用冻结计划的稳定权重聚合进度
- **AND** SHALL 不把任意节点映射为固定 AnalysisStage 或补建报告阶段
- **AND** 已完成或缓存节点 SHALL 不因另一个节点重试被重置，总体展示进度 SHALL 单调递增

### Requirement: API and worker execution separation

系统 SHALL 将任务创建/查询/取消 API 与重型分析执行彻底分离。真实分析请求 SHALL 只在控制面创建 queued job 并通知或等待 external Worker 领取，不得在 Web 请求处理器或 FastAPI lifespan thread 中运行完整 Pipeline。

#### Scenario: API creates a job

- **WHEN** 客户端创建真实分析任务
- **THEN** API SHALL 校验请求、持久化 queued job、通知或等待 external Worker，并在完整分析执行前返回

#### Scenario: Worker executes a job

- **WHEN** external Worker 找到可执行 queued job
- **THEN** Worker SHALL 通过 registry 执行对应 engine 的 Executor，通过 JobStore 写入 heartbeat 与阶段/节点进度，并按 engine 持久化 terminal Job 及结果/报告或模块清单

#### Scenario: API reads status during execution

- **WHEN** 客户端查询 queued、running 或 interrupted job
- **THEN** API SHALL 返回控制面中最新的持久化任务和阶段遥测
- **AND** API SHALL 不依赖 Web 进程内存中是否存在 Worker 或任务缓存

### Requirement: Local queue and priority execution

系统 SHALL 按优先级和创建顺序调度可领取的 queued job，并在进程重启后恢复队列。running job 的恢复 SHALL 由 heartbeat liveness 对账决定；失联运行任务标记为 interrupted，不得重新伪装成仍在 processing。

#### Scenario: Jobs have the same priority

- **WHEN** 多个 queued job 优先级相同
- **THEN** Worker SHALL 优先领取排队时间最早的可执行 job

#### Scenario: Jobs have different priorities

- **WHEN** 多个 queued job 可执行且优先级不同
- **THEN** Worker SHALL 在没有公平性策略阻止饥饿时优先领取高优先级 job

#### Scenario: Queue survives process restart

- **WHEN** 服务重启后存在 queued job 和 running job
- **THEN** queued job SHALL 保持可领取
- **AND** heartbeat 新鲜的 running job SHALL 保持 running
- **AND** heartbeat 过期的 running job SHALL 进入 interrupted，并可通过显式重新分析恢复

### Requirement: Resource-limited execution
The system SHALL limit local concurrent analysis work according to configured CPU and GPU resource settings.

#### Scenario: CPU limit is reached
- **WHEN** the configured maximum number of CPU jobs is already running
- **THEN** additional CPU-bound jobs remain queued until capacity is available

#### Scenario: GPU limit is reached
- **WHEN** the configured maximum number of GPU jobs is already running
- **THEN** additional GPU-bound jobs remain queued until GPU capacity is available

#### Scenario: Default local configuration is used
- **WHEN** no explicit resource configuration is provided
- **THEN** the system runs heavy analysis conservatively so one long or model-backed job cannot start unbounded concurrent analysis jobs

### Requirement: Cancellation

系统 SHALL 支持 Web API 对 external Worker 执行的 queued/running job 发起协作式取消。取消请求必须通过跨进程控制面可见，terminal job（包括 interrupted）不得被普通取消修改。

取消信号 MUST 作为控制信号穿透 Pipeline 执行体到达编排层，SHALL NOT 在执行体内部被转成普通任务失败结果。执行体 SHALL 在检测到取消请求时中止执行并把取消信号交回编排层，编排层 SHALL 记录 canceled 终态。

#### Scenario: Queued job is canceled

- **WHEN** 客户端取消 queued job
- **THEN** 系统 SHALL 在不运行 Pipeline 的情况下将其标记为 canceled

#### Scenario: Running external job is canceled

- **WHEN** 客户端取消 running job
- **THEN** API SHALL 持久化取消请求
- **AND** external Worker SHALL 在下一个安全检查点读取该请求并终止任务

#### Scenario: Interrupted job is not canceled

- **WHEN** 客户端对 interrupted job 发起普通取消
- **THEN** API SHALL 返回稳定的 terminal 状态响应
- **AND** SHALL 不改变 interrupted 的中断原因或删除其任务记录

#### Scenario: Terminal job cancellation is rejected

- **WHEN** 客户端取消 succeeded、failed、canceled 或 interrupted job
- **THEN** 系统 SHALL 返回稳定的非破坏性响应，不得改变 terminal 结果

#### Scenario: 取消信号穿透执行体

- **WHEN** 用户在 Pipeline 执行过程中请求取消，且进度回调在执行体内部被调用时检测到该请求
- **THEN** 取消信号 SHALL 到达编排层的取消处理分支
- **AND** 执行体 MUST NOT 把取消信号转换为 `failed` 结果并附带算法失败归因
- **AND** 编排层 SHALL 记录 canceled 终态

#### Scenario: 执行体报告阶段失败但实际是取消

- **WHEN** 执行体在已请求取消的 job 上抛出异常，且该异常在归因上属于取消信号
- **THEN** 系统 SHALL 记录终态为 canceled
- **AND** 失败归因 MUST NOT 为 `internal_defect`

### Requirement: Timeout and retry policy
系统 SHALL 对显式配置的阶段提供有界超时与重试。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

阶段超时 MUST 作为控制信号到达编排层，SHALL NOT 被转成普通任务失败。

重试 SHALL 是幂等的：每次重试 SHALL 是对执行体的一次完整重新执行，而不是从失败阶段续跑。系统在进入下一次重试尝试前 MUST 清理上一次尝试已写出的产物，或写入显式的「未完成」标记。磁盘上已写出的产物与控制面记录的任务状态 MUST NOT 永久分叉：不得出现控制面记录为 failed/canceled/interrupted、而磁盘上却存在一份声明 `completed` 的结果文件的组合。

#### Scenario: Stage exceeds timeout
- **WHEN** 阶段超过已配置的超时限制
- **THEN** 系统 SHALL 记录超时错误码；可重试时按策略重试，否则将任务置为失败并提供用户可读的超时说明

#### Scenario: Retryable stage fails
- **WHEN** 可重试阶段发生可重试错误且还有重试预算
- **THEN** 系统 SHALL 记录失败尝试、增加重试计数，并按已配置策略重试

#### Scenario: Non-retryable stage fails
- **WHEN** 不可重试阶段失败
- **THEN** 系统 SHALL 将任务置为失败并保留诊断上下文，不进行重试

#### Scenario: 阶段超时作为控制信号

- **WHEN** 执行体在执行过程中检测到阶段超时并抛出控制信号
- **THEN** 该信号 SHALL 到达编排层的超时处理分支
- **AND** 失败归因 SHALL 为超时类，SHALL NOT 为 `internal_defect`
- **AND** 任务 SHALL 记录用户可见的超时说明

#### Scenario: 重试前清理上一次尝试的产物

- **WHEN** 某次执行尝试已写出一份声明完成的结果文件，且该任务随后进入下一次重试尝试
- **THEN** 系统 SHALL 在开始下一次尝试前移除该结果文件，或把它改写为显式的未完成标记
- **AND** 任务最终为 failed、canceled 或 interrupted 时，磁盘上 MUST NOT 存在一份状态为 completed 的结果文件

#### Scenario: 结果读取接口不得返回已失效的成功报告

- **WHEN** 控制面记录的任务状态为 failed、canceled 或 interrupted，且磁盘上存在同名结果文件
- **THEN** 读取该任务结果的接口 MUST NOT 把该文件作为本次运行的完整成功报告返回
- **AND** 若该文件因任何原因仍存在，其内容 MUST 明确表达「本次运行未完成」

#### Scenario: 模块节点有限重试
- **WHEN** modular_v1 的一个可重试节点失败且尚有预算
- **THEN** 系统 SHALL 从该节点起始状态重新执行，不要求节点内部 checkpoint
- **AND** SHALL 保留并核验已发布上游与独立分支，不完整重跑整个 Executor

#### Scenario: 模块部分结果不伪装完整成功
- **WHEN** 模块 Job 终态为 failed、canceled 或 interrupted
- **THEN** 清单 SHALL 表达终态与未完成目标，已发布 Artifact SHALL 保持其真实完成事实
- **AND** API SHALL 不将部分清单返回为完整成功报告

### Requirement: Idempotent job submission
系统 SHALL 基于稳定输入和配置签名支持真实分析任务的幂等提交。 对于声明或消费正式 Team A/B 语义的任务，签名 MUST 包含 `AnalysisRosterSnapshot` hash、analysis-rally-context-set hash 与适用 formal plan input hash。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: Duplicate submission is detected
- **WHEN** 客户端以相同视频、标定、分析选项、模型/运行配置和 roster/context 签名提交，且未要求新版本
- **THEN** 系统 SHALL 返回或引用已有 queued、running 或 succeeded 任务，避免重复执行

#### Scenario: New version is requested
- **WHEN** 客户端对相同输入签名显式请求新的分析版本
- **THEN** 系统 SHALL 创建新任务版本，并记录与之前签名兼容任务的关系

#### Scenario: Configuration changes
- **WHEN** 同一视频使用实质不同的分析选项或模型/运行配置提交
- **THEN** 系统 SHALL 将其视为不同分析签名，并可创建独立任务

#### Scenario: 名册或回合上下文不同
- **WHEN** 相同媒体使用不同 roster snapshot 或 analysis-rally-context-set hash 提交
- **THEN** 系统 SHALL 视其为不同输入
- **AND** MUST NOT 返回采用旧身份、队伍或端位结果的 Job/artifact

#### Scenario: 模块任务按合同去重
- **WHEN** 相同 analysisEngine=modular_v1 与 plan_hash 被重复提交且未请求新版本
- **THEN** 系统 SHALL 复用或引用匹配的 queued/running/succeeded Job
- **AND** plan_hash SHALL 包含目标、已消费上下文、窗口、采样与失败策略，排除缓存提示和随机 ID

#### Scenario: 模块未消费名册
- **WHEN** 纯图像检测未消费 roster/context 且这些字段变化
- **THEN** 系统 SHALL 不因此改变该模块计划身份
- **AND** SHALL 不使用 legacy 的全量任务签名代替模块缓存键

### Requirement: Research-grade execution record
The system SHALL preserve enough execution metadata to support product debugging and research reproducibility.

进入终态时，系统 SHALL 对外暴露的失败说明 MUST 是面向用户的脱敏文案；异常原文、绝对文件路径、栈信息与内部诊断 MUST 收进只供内部诊断的字段。系统 MUST NOT 把异常原文直接作为对外文案。产物引用的公开 URL MUST NOT 泄漏本地绝对路径。

#### Scenario: Completed job is inspected for research
- **WHEN** a developer or researcher reviews a completed real analysis job
- **THEN** the job record exposes the input references, analysis configuration signature, stage timings, model/runtime availability, artifact references, and terminal status needed to reproduce or compare the run

#### Scenario: Internal diagnostics are stored
- **WHEN** internal error details or environment diagnostics are recorded
- **THEN** the system separates them from user-facing messages so the UI does not expose stack traces or sensitive local paths unnecessarily

#### Scenario: 对外失败文案脱敏

- **WHEN** 任务因读取输入视频失败、依赖缺失或其他异常进入 failed 终态
- **THEN** 对外暴露的失败说明 MUST NOT 包含本地绝对文件路径或异常原文
- **AND** 异常原文 SHALL 保留在内部诊断字段中
- **AND** 用户可见文案 SHALL 说明可执行的排查方向

#### Scenario: 内部诊断与公开文案分层一致

- **WHEN** 编排层把执行体返回的失败结论写入任务终态
- **THEN** 公开文案与内部诊断 MUST 来自两个独立字段
- **AND** 内部诊断 MUST NOT 缺失，即使公开文案已被脱敏

#### Scenario: 产物公开引用不泄漏绝对路径

- **WHEN** 任务结果对外暴露产物引用
- **THEN** 公开 URL MUST 是受控的可访问入口
- **AND** MUST NOT 是本地绝对路径

### Requirement: 任务调度保留并传递源 FPS
系统 SHALL 在分析任务创建、持久化、签名和 worker 执行过程中保留用户确认的源 FPS。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: 创建任务保存 FPS
- **WHEN** API 收到包含源 FPS 的分析任务创建请求
- **THEN** JobStore MUST 将该 FPS 保存到任务摘要或任务输入中
- **AND** 后续查询任务时 SHALL 能读取该 FPS

#### Scenario: Worker 传递 FPS 给 Pipeline
- **WHEN** AnalysisWorker 执行包含源 FPS 的任务
- **THEN** worker MUST 将源 FPS 传递给 AnalysisPipeline
- **AND** Pipeline MUST 使用该值计算 `effective_fps`

#### Scenario: FPS 纳入签名
- **WHEN** `analysis_signature()` 计算任务签名
- **THEN** 签名输入 MUST 包含源 FPS 或其规范化等价值
- **AND** 不同源 FPS 的任务 MUST 产生不同签名

#### Scenario: 模块时间元数据冻结
- **WHEN** modular_v1 消费来源 FPS、PTS 或同步信息
- **THEN** 系统 SHALL 在计划与产物中保留实际消费的时间元数据及版本
- **AND** 正式双摄 SHALL 使用既有权威 PTS/clock 映射，不以 FPS 替代

### Requirement: 分析任务支持时间裁剪与预热区间

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

系统 MUST 在 AnalysisJob JSON Schema 中支持 clip 参数（非数据库列），并在所有实际执行和派生可视化阶段使用统一的窗口语义。Pipeline 执行时使用预热区间，但正式指标、融合统计和用户可见叠加视频 MUST 只对应请求窗口。

#### Scenario: Job Schema 包含 clip 字段

- **WHEN** 创建含裁剪参数的分析任务
- **THEN** `AnalysisJobCreate` SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** `AnalysisJobSummary` SHALL 包含对应字段

#### Scenario: 任务签名包含 clip 信息

- **WHEN** `analysis_signature()` 计算
- **THEN** 输入 payload SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** 同一视频不同 Rally SHALL 产生不同签名

#### Scenario: Pipeline 预热区间

- **WHEN** 任务携带 clip 范围
- **THEN** 解码范围 SHALL = `[clip_start - pre_roll_ms, clip_end + post_roll_ms)`
- **AND** 默认 `pre_roll_ms=1500`、`post_roll_ms=500`
- **AND** 半开区间 `[start, end)`，相邻片段不会在边界重复处理
- **AND** 预热帧不纳入正式分析指标

#### Scenario: Pipeline 裁剪结果记录

- **WHEN** Pipeline 按 clip 范围执行
- **THEN** 结果 SHALL 记录 `requested_clip.start_ms/end_ms` 和 `decoded_range.start_ms/end_ms`
- **AND** SHALL 记录实际 `processed_frame_count` 与 `source_frame_count`

#### Scenario: 派生叠加视频遵守窗口

- **WHEN** 任务启用分析叠加视频且携带 clip 范围
- **THEN** 叠加视频 writer SHALL 只读取并写出请求窗口对应的帧
- **AND** 结果 SHALL 记录 `output_time_origin_ms`，使输出 artifact 能映射回源视频时间轴

#### Scenario: 无 clip 保持全场行为

- **WHEN** 任务未携带完整的 `clipStartMs/clipEndMs`
- **THEN** Pipeline、叠加视频和统计 SHALL 按完整源视频执行
- **AND** 结果 SHALL 将窗口字段标记为未启用或省略

#### Scenario: 模块局部范围不继承整场默认
- **WHEN** modular_v1 提交局部验证任务
- **THEN** 请求 SHALL 提供成对的有限窗口，并按 analysis-window-planning 解析上下文和输出选择
- **AND** 缺失或非法窗口 SHALL 被拒绝，不采用 legacy 的全场默认
- **AND** legacy 的默认 1500/500ms 预热 SHALL 不被自动加入无上下文需求的模块

### Requirement: 可执行判定统一为 is_runnable

JobStore.claim_next()/claim 的可执行判定 MUST 收口为 is_runnable(job)。canonicalStatus != queued SHALL 返回 False。analysisEngine=modular_v1 SHALL 仅在冻结计划已持久化、来源/输入准备完成且计划可执行时返回 True，不受 legacy Parent 的 fusion_ready 条件约束；缺省或 legacy_v1 SHALL 保留 single_view 可执行、multiview 仅在 orchestrationStatus 属于 fusion_ready/fallback_ready 时可执行的规则。MUST NOT 仅按 canonicalStatus == queued 领取。

#### Scenario: waiting_sources 不被领取

- **WHEN** `claim_next()` 遇到 `orchestrationStatus=waiting_sources` 的 Parent
- **THEN** 该 Parent SHALL 被跳过，不占用 Worker（杜绝 Parent 占锁等待 child 的死锁）

#### Scenario: fusion_ready 正常领取

- **WHEN** Parent 的 orchestrationStatus=fusion_ready
- **THEN** `claim_next()` SHALL 按既有优先级/排队规则领取

#### Scenario: 模块双摄原始检测可领取
- **WHEN** modular_v1 的双摄 ball.detect 计划与输入已就绪且 queued
- **THEN** Worker SHALL 可领取该任务
- **AND** SHALL 不等待无关的 child、正式切分或 fusion_ready

### Requirement: Worker 经 Executor registry 分发

AnalysisWorkerRuntime._execute MUST 通过统一 resolve_executor 入口先按 analysisEngine、再在 legacy 分支按 analysisKind/模式/角色解析执行体，并调用 execute(job, token, progress_callback)。Worker 主循环 MUST NOT 硬编码具体能力或算法。静态 registry SHALL 保留 SingleView/MultiView 与现有 prerequisite/联合执行角色，并增加 ModularAnalysisExecutor，不引入动态插件框架。取消/超时兜底继续归属 Worker；legacy 整体重试和 modular 节点重试 SHALL 按各自合同执行。

#### Scenario: 单摄执行不变

- **WHEN** 执行 legacy_v1 的 analysisKind=single_view 任务
- **THEN** 行为 SHALL 与改造前一致（SingleViewAnalysisExecutor 封装现有 Pipeline）
- **AND** 现有单摄回归测试 SHALL 通过

#### Scenario: 双摄执行链路

- **WHEN** 执行 legacy_v1、analysisKind=multiview、late_fusion_v1 的 Parent
- **THEN** MultiViewAnalysisExecutor SHALL 读 child 产物 → 执行 Fusion → Composer → 返回 Parent 结果

#### Scenario: 模块执行链路
- **WHEN** 执行 analysisEngine=modular_v1 的任务
- **THEN** Worker SHALL 调用 ModularAnalysisExecutor 并按 ModularRunManifest 发布
- **AND** SHALL 不强制生成 PipelineResult

### Requirement: 新增编排字段兼容读取

`AnalysisJobSummary` MUST 支持新增字段（`analysisKind` / `visibility` / `parentJobId` / `analysisScope` / `orchestrationStatus` / `fusionRunId` / `sourceJobs` / `viewRuns` / `referenceViewId` / `clipStartMs` / `clipEndMs`）的历史兼容读取：缺省按 `single_view` / `public` / `none` 解析，不破坏既有任务。

新增 analysisEngine、planId、planHash、resultKind 和 nodeRuns SHALL 兼容缺省读取；缺失 analysisEngine MUST 为 legacy_v1。历史任务不要求补建计划。

#### Scenario: 历史任务读取

- **WHEN** 读取不含新字段的历史 job
- **THEN** 系统 SHALL 按缺省值解析并正常渲染

#### Scenario: 历史 engine 缺省
- **WHEN** 读取没有 analysisEngine 或 planId 的历史 Job
- **THEN** 系统 SHALL 按 legacy_v1 正常读取
- **AND** SHALL 不启动模型、生成计划或改变历史文件

### Requirement: 历史迁移与运行期读取分离

系统 MUST 在启动迁移边界或显式重导命令导入历史 JSON；JobStore.get/list 与取消检查 SHALL 不扫描历史目录、不执行迁移、不刷新兼容文件。状态实际变更后 SHALL 继续维护所需快照。

#### Scenario: 热路径操作数恒定
- **WHEN** 分别存在 1、100、1000 个历史任务且重复查询同一任务或检查取消
- **THEN** 每次查询 SHALL 只访问所需控制面记录，历史扫描/JSON read/write 次数均为零，数据库操作数 SHALL 不随历史任务数增长

#### Scenario: 启动与重复迁移
- **WHEN** 首次启动或显式重导历史 JSON，或 API/Worker 同时启动
- **THEN** 导入 SHALL 幂等且不覆盖已有控制面任务，完成标记 SHALL 持久化，坏文件 SHALL 被记录并跳过

#### Scenario: 完成迁移后新增历史文件
- **WHEN** 导入完成后旧目录新增 JSON
- **THEN** 普通查询 SHALL 不自动发现，显式重导 SHALL 能安全导入缺失记录

#### Scenario: 跨进程取消仍可见
- **WHEN** API 提交取消且 Worker 在下一个既有安全检查点查询
- **THEN** Worker SHALL 读取新取消状态并遵循原取消/终态/lease 规则，不依赖长期内存缓存

### Requirement: 任务签名和执行记录绑定正式切分配置

需要正式回合切分的 Parent 输入签名 MUST 包含模型 package hash、decoder hash、required policy、CaptureTake 输入 fingerprint 和 sync calibration revision。Parent 与其 prerequisite job MUST 持久化 `segmentation_run_id`、`window_plan_hash`（成功后）及 prerequisite job reference，并在完成结果中暴露可复现但不泄露本地绝对路径的摘要。

#### Scenario: 模型版本变化创建新 Parent
- **WHEN** 同一 CaptureTake 以不同模型 package hash、decoder hash 或同步 revision 创建正式双摄任务
- **THEN** 系统 SHALL 视为不同分析输入
- **AND** SHALL 不复用旧 Parent 的成功结果或窗口计划

#### Scenario: 同配置重复提交
- **WHEN** 同一 CaptureTake 与相同切分配置重复提交，且未请求新版本
- **THEN** 系统 SHALL 复用或引用已有 queued、running 或 succeeded Parent
- **AND** SHALL 不额外创建重复 prerequisite job

### Requirement: prerequisite job 的恢复与取消

正式切分 prerequisite job SHALL 使用 durable Worker lifecycle。其 interrupted、failed、canceled 或成功状态 MUST 经 Coordinator 投影为 Parent 的稳定状态；重启 reconciliation MUST 不释放未成功切分的 late-fusion child，也不得重新发布已成功 run 的重复自动 Segment。

#### Scenario: prerequisite 在重启后中断
- **WHEN** 服务重启后 prerequisite job 的 heartbeat 已过期
- **THEN** Worker recovery SHALL 将该 prerequisite 标记为 interrupted
- **AND** Parent SHALL 进入明确 interrupted 或 failed 状态而不是无限等待

#### Scenario: 成功 prerequisite 重放
- **WHEN** 重启前 prerequisite 已成功发布 run 和 plan，但 Coordinator 尚未释放 Parent
- **THEN** reconciliation SHALL 使用已绑定的 run id 和 plan hash 推进 Parent
- **AND** SHALL 不重复创建 algorithm Segments 或 supersede 同一 run

### Requirement: 模块计划入队前冻结并持久化
模块请求 SHALL 在来源准备、能力/实现与必需输入校验、窗口解析后冻结计算合同，并在同一控制面中持久化计划和 queued Job。preview MUST 不持久化。Worker SHALL 读取冻结计划，不能根据最新默认配置重新规划。

#### Scenario: 排队期间配置变化
- **WHEN** 有效计划已入队而全局模型开关或默认实现变化
- **THEN** Worker SHALL 执行原冻结合同
- **AND** 无法核验原实现/模型时 SHALL 明确失败，不静默替换

### Requirement: 模块恢复复用节点发布记录
显式恢复 interrupted/failed 模块任务 SHALL 保留原计划和尝试证据，核验已发布输入/输出后仅重新调度必要节点。没有有效租约的旧运行 SHALL 不得继续发布。模块恢复 MUST 不调用 legacy 的整任务清理逻辑删除共享产物。

#### Scenario: 重启后恢复
- **WHEN** Worker 重启并将失联模块任务对账为 interrupted，随后收到显式恢复
- **THEN** 新尝试 SHALL 在原计划上复用有效节点
- **AND** SHALL 不重复发布有效完成产物或清空历史失败证据
