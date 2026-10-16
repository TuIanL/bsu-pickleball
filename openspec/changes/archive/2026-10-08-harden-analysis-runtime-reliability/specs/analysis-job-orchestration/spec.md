## MODIFIED Requirements

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

- **WHEN** 所有必需分析阶段和报告生成完成
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

### Requirement: Stage telemetry

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
The system SHALL support bounded timeout and retry behavior for explicitly configured stages.

阶段超时 MUST 作为控制信号到达编排层，SHALL NOT 被转成普通任务失败。

重试 SHALL 是幂等的：每次重试 SHALL 是对执行体的一次完整重新执行，而不是从失败阶段续跑。系统在进入下一次重试尝试前 MUST 清理上一次尝试已写出的产物，或写入显式的「未完成」标记。磁盘上已写出的产物与控制面记录的任务状态 MUST NOT 永久分叉：不得出现控制面记录为 failed/canceled/interrupted、而磁盘上却存在一份声明 `completed` 的结果文件的组合。

#### Scenario: Stage exceeds timeout
- **WHEN** a stage exceeds its configured timeout
- **THEN** the system records a timeout error code and either retries the stage if it is retryable or fails the job with a user-facing timeout message

#### Scenario: Retryable stage fails
- **WHEN** a retryable stage fails with a retryable error and retry attempts remain
- **THEN** the system records the failed attempt, increments the retry count, and retries the stage according to the configured policy

#### Scenario: Non-retryable stage fails
- **WHEN** a non-retryable stage fails
- **THEN** the system fails the job without retrying and preserves the diagnostic context

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
