## MODIFIED Requirements

### Requirement: Durable analysis job lifecycle

`canonicalStatus` SHALL 管理 `queued / running / succeeded / failed / canceled / interrupted` 六态任务生命周期；`interrupted` 表示本次 Worker 执行失联或被进程中断，不等价于 Pipeline 算法失败。系统 MUST 使用独立维度 `orchestrationStatus` 表达多视角 Parent 编排，不得将 `waiting_sources` 等编排状态塞入 `canonicalStatus`。任务摘要 SHALL 持久化 Worker lease、heartbeat 和 interruption 字段，并兼容读取没有这些字段的历史任务。

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

### Requirement: API and worker execution separation

系统 SHALL 将任务创建/查询/取消 API 与重型分析执行彻底分离。真实分析请求 SHALL 只在控制面创建 queued job 并通知或等待 external Worker 领取，不得在 Web 请求处理器或 FastAPI lifespan thread 中运行完整 Pipeline。

#### Scenario: API creates a job

- **WHEN** 客户端创建真实分析任务
- **THEN** API SHALL 校验请求、持久化 queued job、通知或等待 external Worker，并在完整分析执行前返回

#### Scenario: Worker executes a job

- **WHEN** external Worker 找到可执行 queued job
- **THEN** Worker SHALL 执行 Pipeline，通过 JobStore 写入 heartbeat/阶段进度，并持久化 terminal job/result/report 状态

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

### Requirement: Cancellation

系统 SHALL 支持 Web API 对 external Worker 执行的 queued/running job 发起协作式取消。取消请求必须通过跨进程控制面可见，terminal job（包括 interrupted）不得被普通取消修改。

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
