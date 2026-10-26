# analysis-run-trace Specification

## Purpose
定义分析任务失败的可追溯性契约：每次执行尝试产生结构化事件轨迹，失败被归入稳定类别，重试与取消不得覆盖已发生的失败证据，从而让「为什么失败」在本机落盘数据上可回答，而不只能靠反复重跑试错。
## Requirements
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

### Requirement: 失败归因与稳定错误码正交并存

系统 SHALL 同时提供两个正交维度：稳定错误码 `error_code` 表达「哪一步失败」，失败归因 `failure_class` 表达「为什么失败」。`failure_class` MUST 取自固定枚举：`input_media`、`calibration`、`model_environment`、`resource_timeout`、`worker_lease`、`orchestration`、`internal_defect`。归因判定 MUST 由不依赖视觉运行时（不 import `cv2` / `ultralytics`）的纯逻辑模块完成，以便独立测试。无法判定时 MUST 归为 `internal_defect`，且原始 `exception_type` 与 `exception_message` MUST 始终保留以便事后重新归因。

#### Scenario: 归因与错误码同时给出

- **WHEN** 任何阶段失败被记录
- **THEN** 该记录 SHALL 同时包含一个稳定错误码与一个失败归因类别，二者 MUST NOT 相互替代

#### Scenario: 未知异常不被吞掉原始信息

- **WHEN** 归因器无法把异常映射到具体类别
- **THEN** 系统 SHALL 使用 `internal_defect` 作为类别，并 SHALL 保留原始异常类型与消息

#### Scenario: 同一异常可被聚合

- **WHEN** 同一根因的异常在不同尝试或不同阶段反复出现
- **THEN** 这些事件 SHALL 具有相同的 `traceback_digest`，使消费者可聚合同一异常

### Requirement: 终态不得抹除运行中失败证据

任务进入 `canceled`、`interrupted` 或 `failed` 终态时，系统 MUST 保留运行期间已经产生的失败证据。任务摘要 SHALL 提供独立的 `failureEvidence`（首次失败的错误码、归因类别、时间与所属 `attempt`）与 `retryHistory`（每次重试的阶段、归因类别与时间）。写入终态字段 MUST NOT 清空或覆盖 `failureEvidence`。消费者的 `error_code` 与 `failureEvidence` 语义 MUST 分离：前者表达最终去向，后者表达曾经的失败。

#### Scenario: 取消不掩盖真实失败

- **WHEN** 一个曾因阶段异常发生重试的任务随后被用户取消
- **THEN** 任务摘要 SHALL 同时表达终态为 `canceled` 与「曾因某类原因失败并重试 N 次」
- **AND** 运行期间记录的失败错误码与归因类别 MUST NOT 被取消码覆盖

#### Scenario: 失联不掩盖真实失败

- **WHEN** 一个曾发生失败重试的任务随后因 Worker 失联被标记为 `interrupted`
- **THEN** 系统 SHALL 保留此前的 `failureEvidence` 与 `retryHistory`

#### Scenario: 历史任务无证据字段时兼容

- **WHEN** 读取一个在本能力上线前创建、不含 `failureEvidence` / `retryHistory` 的历史任务
- **THEN** 系统 SHALL 按既有字段正常返回，MUST NOT 因缺字段而报错

### Requirement: 轨迹 artifact 的落盘位置与不可用降级

轨迹 MUST 落盘到该任务的产物目录，即与其余分析产物同址；对正式采集任务而言该目录位于外接存储。当目标位置不可写时，系统 MUST NOT 静默改写到其他位置，而 SHALL 记录一条 `event=trace_sink_unavailable`（含目标路径与失败原因）并保持任务正常执行。轨迹 MUST 随任务删除一并清理。

#### Scenario: 双摄任务的轨迹落在外接存储

- **WHEN** 一个正式采集的双摄任务产生运行轨迹
- **THEN** 轨迹 SHALL 位于该任务产物根目录（`<session_dir>/analysis/<job_id>`）之下，与其余产物同址

#### Scenario: 目标不可写时显式声明而非静默改写

- **WHEN** 轨迹目标位置不可写（例如外接存储未挂载）
- **THEN** 系统 SHALL 记录 `trace_sink_unavailable` 事件并说明目标路径与原因
- **AND** 系统 MUST NOT 把轨迹静默改写到一个用户不期望的位置
- **AND** 任务执行 MUST NOT 因轨迹写入失败而中断

#### Scenario: 删除任务同时清理轨迹

- **WHEN** 用户删除一个分析任务
- **THEN** 该任务的轨迹 artifact SHALL 随任务产物一并清理

### Requirement: 轨迹与运行日志的只读读取接口

系统 SHALL 提供只读接口以按 `job_id` 读取运行轨迹，返回解析后的事件序列以及可用性状态（`available` / `unavailable`）与不可用原因。系统 SHALL 提供只读接口以按 `job_id` 读取运行日志，日志读取 MUST 施加返回行数上限，MUST 依据任务领取时间与结束时间构成的时间窗口过滤，并在匹配不到时显式返回不完整可用性与原因，而非返回空结果。轨迹 MUST NOT 被内联进任务列表摘要，以避免高频轮询体积随重试次数膨胀。

#### Scenario: 读取轨迹返回事件与可用性

- **WHEN** 客户端请求一个具备轨迹的任务
- **THEN** 接口 SHALL 返回按 `seq` 有序的事件序列，并标注可用性为 `available`

#### Scenario: 无轨迹时给出原因

- **WHEN** 客户端请求一个在上线前创建、不存在轨迹文件的任务
- **THEN** 接口 SHALL 返回可用性 `unavailable` 与明确原因，MUST NOT 返回错误状态或空结果冒充成功

#### Scenario: 日志读取有界且可解释

- **WHEN** 客户端请求某任务的运行日志
- **THEN** 接口 SHALL 返回不超过上限的行数，且仅包含落在该任务执行时间窗口内、与该任务标识匹配的行
- **AND** 当无法匹配到该任务的行时，接口 SHALL 返回不完整可用性与原因

#### Scenario: 任务摘要不内联轨迹

- **WHEN** 客户端以进度轮询频率读取任务列表或任务摘要
- **THEN** 响应 MUST NOT 内联完整事件轨迹

### Requirement: 前端呈现分析进程与失败原因

任务详情 MUST 呈现本次分析的可读进程：已尝试次数、每次重试的原因与是否还会继续重试；并且 MUST 提供技术详情入口以查看内部诊断信息。当轨迹不可用时，界面 SHALL 显示不可用原因，MUST NOT 报错或伪装为正常运行。

#### Scenario: 详情页展示重试进程

- **WHEN** 用户打开一个发生过重试的任务详情
- **THEN** 界面 SHALL 展示尝试次数与每次重试的原因
- **AND** 界面 SHALL 标明是否还会继续重试

#### Scenario: 内部诊断信息可展开

- **WHEN** 用户在任务详情中展开技术详情
- **THEN** 界面 SHALL 展示内部诊断信息（含原始异常摘要），而不是仅展示面向用户的通用文案

#### Scenario: 轨迹不可用时降级展示

- **WHEN** 任务不存在轨迹或轨迹目标不可写
- **THEN** 界面 SHALL 展示不可用原因，且任务其余信息 SHALL 保持正常可用

#### Scenario: 取消任务同时展示历史失败

- **WHEN** 用户查看一个「曾失败重试后又被取消」的任务
- **THEN** 界面 SHALL 同时展示终态（已取消）与历史失败原因

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
