## MODIFIED Requirements

### Requirement: Worker heartbeat and execution lease

系统 SHALL 为每次 Worker 领取的运行任务建立持久化 execution lease，并独立记录 `workerId`、`workerPid`、`workerRunId`、`claimedAt`、`workerHeartbeatAt` 和 `lastProgressAt`。Worker SHALL 在长阶段没有进度事件时仍持续发送 heartbeat。检测到 lease 丢失时，Worker SHALL 只表达「本次运行已失去租约」这一单次运行结论，SHALL NOT 表达「整个 Worker 应当退出」。

#### Scenario: Worker claims a job

- **WHEN** Worker 成功领取一个 queued job
- **THEN** 系统 SHALL 原子地写入 Worker 身份、运行实例 ID、领取时间和首次 heartbeat
- **AND** 同一个 queued job SHALL NOT 被另一个 Worker 同时领取

#### Scenario: Long stage has no progress event

- **WHEN** Pipeline 在一个长阶段内暂时没有新的阶段进度事件
- **THEN** Worker SHALL 继续更新 `workerHeartbeatAt`
- **AND** 系统 SHALL 不得仅因 `updatedAt` 或 stage progress 未变化就判定任务失联

#### Scenario: 单次运行丢失租约

- **WHEN** Worker 在执行某个 job 期间检测到该 job 的 execution lease 已丢失
- **THEN** 系统 SHALL 只把该次运行表达为失败，并保留可解释的租约丢失原因
- **AND** Worker SHALL 保持可继续领取后续 queued job 的状态
- **AND** Worker 主循环 SHALL NOT 因单次租约丢失而永久退出

#### Scenario: 用户取消导致租约条件失配

- **WHEN** 用户取消一个正在运行中的 job，使该 job 不再处于 `running` 状态
- **THEN** Worker 的下一次 heartbeat 条件更新 SHALL 因状态失配而被拒绝
- **AND** 系统 SHALL 将该次运行表达为用户取消，SHALL NOT 表达为 Worker 故障
- **AND** Worker SHALL 在该 job 结束后继续领取后续 queued job

## ADDED Requirements

### Requirement: Worker 关停与单任务失败是两个独立语义

系统 SHALL 把「整个 Worker 应当停止领取任务」表达为独立的关停信号，SHALL NOT 复用任何用于表达单次运行结论（租约丢失、用户取消、阶段超时、阶段失败）的信号。关停信号 SHALL 只能由显式的关停意图触发（外部关停请求、进程退出、守护重启）。

单次运行结论 SHALL 只作用于该次运行：Worker SHALL 结束当前执行、回到空闲态，并继续按既有调度规则领取后续 queued job。当 Worker 运行在 API 进程内嵌（embedded）模式时，Worker 主循环意外终止 SHALL 存在恢复路径，使后续 queued job 仍能被处理。

#### Scenario: 显式关停才停止领取

- **WHEN** Worker 收到显式关停请求
- **THEN** Worker 主循环 SHALL 退出，SHALL NOT 再领取任何 queued job
- **AND** 该行为 SHALL NOT 依赖任何单次运行失败的判定

#### Scenario: 单任务失败后 Worker 继续服务

- **WHEN** 一个 job 的执行因租约丢失、用户取消、阶段超时或阶段失败而结束
- **THEN** Worker SHALL 回到可领取状态
- **AND** 队列中后续可执行的 queued job SHALL 能被该 Worker 领取并执行

#### Scenario: 租约丢失不等于 Worker 关停

- **WHEN** 一次 heartbeat 返回「租约不再有效」
- **THEN** 系统 SHALL NOT 因此把 Worker 标记为已关停
- **AND** Worker 的存活状态 SHALL 保持为可继续执行

#### Scenario: 内嵌 Worker 意外终止后可恢复

- **WHEN** 内嵌模式下的 Worker 主循环意外终止，且未收到显式关停请求
- **THEN** 系统 SHALL 能够重新拉起 Worker 主循环
- **AND** 队列中的 queued job SHALL 能够在恢复后被领取

### Requirement: Worker 存活的回归测试必须覆盖跨任务连续性

系统 SHALL 提供回归测试断言「单个 job 的租约丢失不会让 Worker 停止服务后续任务」。该测试 SHALL 构造两个可执行 job，使第一个 job 在执行期间失去租约，并断言第二个 job 仍能被同一 Worker 领取。该测试 MUST NOT 依赖真实模型的时序稳定性。

#### Scenario: 首个 job 丢租约后仍可领取下一个

- **WHEN** 回归测试让 Worker 执行第一个 job 时租约失效，并在队列中保留第二个可执行 job
- **THEN** 测试 SHALL 断言 Worker 主循环仍然存活
- **AND** 测试 SHALL 断言第二个 job 被成功 claim 并进入执行

#### Scenario: 断言的是领取能力而非退出

- **WHEN** 回归测试断言单任务租约丢失后的 Worker 行为
- **THEN** 断言 SHALL 针对「后续任务仍能被领取」
- **AND** 测试 MUST NOT 仅断言当前任务被标记为失败而放过 Worker 主循环已退出的情况
