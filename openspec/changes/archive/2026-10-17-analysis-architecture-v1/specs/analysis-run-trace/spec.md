## MODIFIED Requirements

### Requirement: 每次运行产生结构化事件轨迹

系统 SHALL 为每一次分析任务的执行尝试产生 append-only 的结构化事件轨迹，事件以 JSONL 逐行落盘，使进程被中断后已写入的前缀仍然可读。每个事件 MUST 至少携带 `schema_version`、单调递增的 `seq`、`ts`、`job_id`、`attempt`、`worker_id`、`worker_run_id`、`stage` 与 `event`。`event` MUST 取自固定枚举：`start`、`end`、`retry`、`fail`、`lease_lost`、`canceled`、`trace_sink_unavailable`。轨迹 MUST 能按 `attempt` 还原每次尝试的阶段起止与最终结果。

legacy_v1 SHALL 保持 analysis-run-trace.v1 字段与读取兼容。modular_v1 SHALL 使用 analysis-run-trace.v2，并沿用上述 event 枚举；stage 可记录节点标识，MUST 增加 plan_id、node_id、capability_id、implementation_id、node_attempt 与 outcome。缓存命中/未命中及阻断 SHALL 使用 cache_decision/outcome 表达，不扩充旧枚举或伪装成模型执行。

Job 级控制事件没有所属节点时，节点/实现字段 SHALL 显式为 null；节点事件 MUST 绑定实际节点和 node_attempt，不使用虚构能力代替。

#### Scenario: 正常运行的阶段起止被记录

- **WHEN** Worker 领取到 job 并依次执行分析阶段
- **THEN** 每个阶段进入时 SHALL 写入 `event=start`、完成时 SHALL 写入 `event=end`，且事件携带所属 `attempt` 与 `stage`
- **AND** 轨迹中的 `seq` SHALL 在整个 job 生命周期内单调递增

#### Scenario: 按 attempt 区分多次尝试

- **WHEN** 同一 job 因重试或重新领取而执行多轮
- **THEN** 轨迹 SHALL 通过 `attempt` 区分不同轮次，且每轮的阶段事件 SHALL 归属于该轮 `attempt`

#### Scenario: 进程被杀后已写入的事件仍可读

- **WHEN** 分析进程在轨迹写入过程中被强制终止
- **THEN** 终止前已写入的 JSONL 行 SHALL 保持可解析，且每行 SHALL 是独立完整的 JSON 对象

#### Scenario: 缓存命中轨迹
- **WHEN** 一个模块节点被缓存满足
- **THEN** v2 SHALL 记录该节点的 start/end、outcome=cached、cache_decision=hit 和实际 ArtifactRef
- **AND** SHALL 明确推理次数为零

#### Scenario: v1 与 v2 混合读取
- **WHEN** inspect 读取历史 v1 或新 v2 trace
- **THEN** 系统 SHALL 按 schema_version 解析并保留其含义
- **AND** SHALL 不要求历史记录含 node_attempt

### Requirement: 阶段内重试必须留痕

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

需要正式双摄回合切分的双摄 Parent 与单摄任务在阶段内发生可重试失败时，系统 MUST 在重跑执行体之**前**写入 `event=retry` 事件。该事件 MUST 携带被捕获异常的 `exception_type`、截断后的 `exception_message`、`traceback_digest`、`traceback_frames`，以及 `retry_index`、`retry_limit`、`will_retry`。系统 MUST 同时把该异常的摘要写入该阶段 `internalMessage`，使未读取轨迹的消费者也能获得一行失败原因。重试事件 MUST 记录失败前后的阶段进度（`progress_before` / `progress_after`），使阶段进度回退可被解释为「重试所致」。系统 MUST NOT 在未写入重试事件的情况下静默重跑执行体。

#### Scenario: 可重试阶段失败留下完整原因

- **WHEN** 处于可重试阶段集合内的阶段抛出异常，且已用重试次数未达到上限
- **THEN** 系统 SHALL 写入携带该异常类型、摘要、digest 与末帧位置的 `retry` 事件
- **AND** 该阶段的 `internalMessage` SHALL 记录同一失败摘要，而非仅记录固定文案

#### Scenario: 重试决策对用户可见

- **WHEN** 一次重试被触发
- **THEN** `retry` 事件 SHALL 记录当前 `retry_index`、策略上限 `retry_limit` 以及本次之后是否还会再重试 `will_retry`

#### Scenario: 阶段进度回退来自重试

- **WHEN** 重试导致阶段状态或进度回退
- **THEN** `retry` 事件 SHALL 记录回退前的进度，使消费者可区分「重试回退」与「任务重新开始」

#### Scenario: 不可重试阶段不产生重试事件

- **WHEN** 失败发生在可重试阶段集合之外的阶段
- **THEN** 系统 MUST NOT 写入 `retry` 事件，SHALL 直接进入失败处理并写入 `fail` 事件

#### Scenario: 模块节点重试证据
- **WHEN** 模块节点失败后将进入有限重试
- **THEN** 系统 SHALL 在重跑节点前记录 retry 及原异常摘要/digest/frames、retry_index/limit/will_retry、节点进度前后值和 node_attempt
- **AND** 节点 internalMessage SHALL 保留同一诊断，job attempt SHALL 不被 node_attempt 替代
- **AND** 重试次数汇总 SHALL 不将同一失败在节点和 Job 两层重复计数

#### Scenario: 节点阻断不是重试失败
- **WHEN** 模块节点因必需上游失败而 blocked
- **THEN** trace SHALL 记录 outcome=blocked 和 upstream_failure 引用
- **AND** SHALL 不伪造该节点的异常或推理重试

## ADDED Requirements

### Requirement: 模块轨迹可以解释规划与缓存决定
modular_v1 的计划/节点记录与 trace SHALL 联合提供目标、依赖展开、窗口扩展理由、采样、实际输入绑定、缓存判定及失败策略。节点 end SHALL 记录发布产物、解码/推理计数、资源初始化和耗时摘要。大 payload SHALL 通过引用读取，不内联进高频任务摘要。

#### Scenario: 解释窄重算
- **WHEN** 仅姿态参数改变后 inspect 一个新 Job
- **THEN** 记录 SHALL 解释人框/球命中与姿态未命中的输入差异
- **AND** SHALL 显示实际重新解码范围和仅被初始化的模型

#### Scenario: 对外诊断脱敏
- **WHEN** API 返回模块错误或清单
- **THEN** 公开字段 SHALL 仅提供稳定错误码、可读原因与逻辑引用
- **AND** 本地绝对路径、异常原文和栈 SHALL 只出现在受控内部诊断字段
