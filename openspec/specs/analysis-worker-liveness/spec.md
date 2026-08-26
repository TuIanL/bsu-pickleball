# analysis-worker-liveness Specification

## Purpose
TBD - created by archiving change externalize-analysis-worker-liveness. Update Purpose after archive.
## Requirements
### Requirement: Worker heartbeat and execution lease

系统 SHALL 为每次 Worker 领取的运行任务建立持久化 execution lease，并独立记录 `workerId`、`workerPid`、`workerRunId`、`claimedAt`、`workerHeartbeatAt` 和 `lastProgressAt`。Worker SHALL 在长阶段没有进度事件时仍持续发送 heartbeat。

#### Scenario: Worker claims a job

- **WHEN** Worker 成功领取一个 queued job
- **THEN** 系统 SHALL 原子地写入 Worker 身份、运行实例 ID、领取时间和首次 heartbeat
- **AND** 同一个 queued job SHALL NOT 被另一个 Worker 同时领取

#### Scenario: Long stage has no progress event

- **WHEN** Pipeline 在一个长阶段内暂时没有新的阶段进度事件
- **THEN** Worker SHALL 继续更新 `workerHeartbeatAt`
- **AND** 系统 SHALL 不得仅因 `updatedAt` 或 stage progress 未变化就判定任务失联

### Requirement: Worker heartbeat timeout detection

系统 SHALL 使用独立于普通任务更新时间的 heartbeat timeout 判定运行中任务是否失联。超时判定 SHALL 使用任务当前的 `workerRunId` 或等价租约条件更新，避免覆盖已经完成、取消或被新运行实例领取的任务。

#### Scenario: Heartbeat remains fresh

- **WHEN** running job 的最近 heartbeat 未超过配置的 timeout
- **THEN** 系统 SHALL 保持任务为 running/processing
- **AND** 前端 SHALL 继续显示真实的分析进度而不是“任务失联”

#### Scenario: Heartbeat expires

- **WHEN** running job 的最近 heartbeat 超过配置的 timeout
- **THEN** 系统 SHALL 将任务置为 `canonicalStatus=interrupted`
- **AND** SHALL 记录 `interruptedAt`、`interruptionCode=worker_heartbeat_timeout` 或等价稳定错误码
- **AND** SHALL 保留最后阶段、进度、Worker 身份和用户安全的中断说明

### Requirement: Startup recovery of analysis jobs

服务启动 SHALL 在启动新 Worker 前扫描持久化任务并执行恢复对账。queued 任务必须保持可领取；heartbeat 新鲜的 running 任务必须保留运行态；heartbeat 已过期的 running 任务必须标记为 interrupted。interrupted 任务默认不得被自动重复领取。

#### Scenario: Queued job survives restart

- **WHEN** 服务重启时发现 queued job
- **THEN** 系统 SHALL 保留其队列时间、优先级和输入配置
- **AND** 新 Worker SHALL 能够按既有调度规则领取该任务

#### Scenario: External worker survives API reload

- **WHEN** API 进程热重载但独立 Worker 仍持续发送新鲜 heartbeat
- **THEN** 系统 SHALL 不得将该 running job 标记为 interrupted
- **AND** Worker SHALL 能够继续写入阶段和 terminal 状态

#### Scenario: Worker crashed before restart

- **WHEN** 服务启动时发现 running job 的 heartbeat 已过期
- **THEN** 系统 SHALL 将其标记为 interrupted，而不是无限保留 processing
- **AND** 该任务 SHALL 暴露可重新分析或删除的恢复入口

### Requirement: Cross-process job control plane

Web API 与 analysis-worker SHALL 通过可跨进程安全访问的持久化控制面交互。claim、heartbeat、取消请求、阶段更新、terminal update 和 interruption recovery SHALL 具备原子条件更新语义，不得依赖对方进程的内存缓存。

#### Scenario: API cancels an external job

- **WHEN** API 对 running job 写入取消请求
- **THEN** external Worker 的 cancellation token SHALL 能读取到该请求
- **AND** Worker SHALL 在下一个安全检查点将任务置为 canceled 或继续报告取消处理中状态

#### Scenario: API and worker update concurrently

- **WHEN** API heartbeat watchdog、Worker heartbeat 或用户取消同时更新同一个 job
- **THEN** 系统 SHALL 根据 job 状态和 workerRunId 条件拒绝过期更新
- **AND** SHALL 不得产生损坏的任务摘要或回退覆盖较新的 terminal 状态

### Requirement: External worker process isolation

本地 external runtime SHALL 将 FastAPI API 和 analysis-worker 作为独立 OS 进程运行。API 的代码热重载、请求生命周期和 Web 服务 shutdown SHALL 不得直接停止独立 Worker。

#### Scenario: API reloads while analysis is running

- **WHEN** `uvicorn --reload` 重启 API 进程且 analysis-worker 未被停止
- **THEN** running job SHALL 继续执行并持续更新 heartbeat/progress
- **AND** 前端重新查询时 SHALL 获得最新任务状态

#### Scenario: Worker process starts without API lifespan worker

- **WHEN** local runtime 以 external 模式启动
- **THEN** FastAPI SHALL 不再创建内嵌分析 Worker thread
- **AND** analysis-worker 进程 SHALL 独立初始化执行 runtime、模型配置和任务循环
