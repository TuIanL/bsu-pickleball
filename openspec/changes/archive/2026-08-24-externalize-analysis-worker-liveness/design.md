## Context

当前系统已经有 `JobStore`、`AnalysisWorkerRuntime`、阶段遥测、取消令牌和启动时僵尸任务回收，但 Worker 仍然是 FastAPI 进程内的 daemon thread。开发脚本使用 `uvicorn --reload`，后端热重载会连同分析 Worker 一起退出；而任务摘要主要保存为 JSON，`JobStore` 的线程锁和内存缓存只覆盖单进程并发，不能直接作为 Web API 与独立 Worker 之间的可靠控制面。

本变更需要保留现有分析 Pipeline、报告和文件产物路径，兼容历史任务，并继续支持单摄、late-fusion 双摄和 joint-tracking 双摄。目标是先解决单机本地运行的可靠性，不引入 Redis、Celery 或多主机调度。

## Goals / Non-Goals

**Goals:**

- 让分析执行进程独立于 FastAPI Web 进程，Web 热重载不再杀掉正在运行的分析。
- 为每个运行中任务提供可持久化、可跨进程读取的 Worker 心跳和领取租约。
- 在 Worker 崩溃、进程被杀或长时间无心跳时，把任务稳定地标记为 `interrupted`，前端展示“任务失联”。
- 启动时恢复 queued 任务，并对运行中的任务进行心跳对账；不让任务永久停留在 processing。
- 保持取消、优先级、重试、阶段遥测、幂等提交和多视角 Parent/Child 编排能力。
- 让本地启动/停止脚本分别管理 API 与 analysis-worker 的 PID、日志和优雅退出。

**Non-Goals:**

- 不实现从任意中间帧精确续跑的检查点系统；失联任务默认显式重新分析。
- 不把分析结果迁移到数据库；视频、报告、Overlay 和其他 artifact 继续保存在文件系统。
- 不引入分布式队列、跨主机 Worker、用户鉴权或多租户资源调度。
- 不重写视觉算法和 Pipeline 阶段本身。

## Decisions

### 1. 使用独立 OS 进程承载 analysis-worker

本地运行时拆成两个长期进程：FastAPI API 进程和 `python -m app.analysis_worker` Worker 进程。API 进程可以继续使用 `--reload`；Worker 不由 FastAPI lifespan 创建，也不由 Web 进程的 daemon thread 承载。

`start-local-runtime.sh` 负责按顺序启动 API、analysis-worker 和前端，并分别写入 PID/log 文件。`stop-local-runtime.sh` 先停止 Worker，再停止 API 和前端。直接运行 API 时允许通过配置保留 embedded Worker 兼容模式，但一键本地运行默认使用 external 模式。

备选方案是把 Worker 放到 `multiprocessing` 子进程或 FastAPI `BackgroundTasks` 中。前者仍然受 Web 父进程生命周期和进程组管理影响，后者无法满足热重载隔离，因此不作为默认方案。

### 2. 使用 SQLite 作为任务控制面，文件系统继续保存分析产物

新增或扩展任务控制面记录，至少保存任务状态、队列排序字段、Worker 身份、领取租约、心跳、取消请求、尝试次数和完整任务摘要 payload。阶段列表和历史兼容字段可以继续序列化为 JSON payload；结果、报告和大型 artifact 不进入控制面表。

Worker claim 使用 SQLite 事务和条件更新实现单次领取，条件必须包含 `canonicalStatus=queued` 和当前编排可执行条件。API 查询、取消和 Worker heartbeat 使用独立数据库 session，不依赖另一进程的内存缓存。

历史 `data/outputs/jobs/*.json` 需要支持一次性导入或只读兼容读取，避免已有任务因控制面迁移而消失。新任务和状态更新以 SQLite 为权威，JSON 作为兼容迁移来源或调试快照。

备选方案是给 JSON Store 增加 `flock`、每次操作强制从磁盘刷新并移除进程内缓存。这种方案改动较小，但需要自行解决多字段条件更新、取消与心跳竞争、跨平台锁和 stale cache，可靠性不如已有 SQLite 基础。

### 3. 将业务生命周期与 Worker liveness 分开记录

业务生命周期扩展为：

```text
queued -> running -> succeeded
                 -> failed
                 -> canceled
                 -> interrupted
```

`interrupted` 表示本次执行没有得到可靠的 Worker 完成结果，不等价于 Pipeline 的算法失败。任务保留阶段进度、最后已知 Worker 信息和中断原因，允许用户显式重新分析。

运行中的任务另外记录：

```text
workerId / workerPid / workerRunId
claimedAt / workerHeartbeatAt / lastProgressAt
interruptedAt / interruptionCode
```

`workerHeartbeatAt` 独立于 `updatedAt`。这样在某个模型阶段长时间没有进度变化时，只要 Worker 仍存活，任务不会被误判为失联。

### 4. 心跳间隔与失联判定使用租约语义

Worker 领取任务后立即写入 lease，并以配置间隔持续 heartbeat。建议本地默认 heartbeat interval 为 5 秒、heartbeat timeout 为 30 秒；超时阈值必须大于多个 heartbeat 周期，并允许通过 `PICKLEBALL_` 环境变量调整。

轻量 watchdog 在 API 读取任务列表/详情时执行对账，启动时执行全量恢复；必要时 API 生命周期可以运行低频 watchdog 协程。检测到 running 任务的 heartbeat 超时后，使用条件更新将其置为 `interrupted`，避免重复覆盖已经完成或被新 Worker 重新领取的任务。

Worker 自身的 heartbeat 线程/循环必须独立于阶段进度回调，以覆盖“阶段仍在运行但没有阶段事件”的情况。heartbeat 更新失败时 Worker 记录日志并停止继续领取新任务，但不应伪造成功状态。

### 5. 启动恢复采取保守策略

启动顺序为：初始化数据库 → 导入/读取历史任务 → 回收失联运行任务 → 对账双摄 Parent/Child → 启动 external Worker。

- `queued` 任务保留为 queued，由新 Worker 正常领取。
- `running` 且 heartbeat 新鲜的任务保留 running；这允许 Web API 热重载时仍在运行的独立 Worker 继续工作。
- `running` 且 heartbeat 超时的任务置为 `interrupted`，记录 `worker_lost` 或 `worker_heartbeat_timeout` 原因。
- `interrupted` 默认不自动回队列；用户通过重新分析创建新的 job/version，避免重复执行和半成品 artifact 冲突。
- 收到正常 shutdown 时，Worker 停止领取新任务并尽可能完成当前安全检查点；若进程被强制终止，下一次启动按 heartbeat 超时处理。

### 6. 前端把 interrupted 作为可恢复终态

API summary 同时暴露 `interrupted`、`interruptionCode`、`interruptedAt`、`workerHeartbeatAt` 和用户安全的 `publicErrorMessage`。前端状态辅助函数、运行时轮询、任务列表、任务详情和素材工作区统一以 `interrupted` 结束 active watch。

用户文案使用“任务失联”，并说明“Worker 在规定时间内没有心跳，已保留最后进度；可以重新分析”。该状态不提供普通取消按钮，不开放结果 CTA，允许查看任务详情、重新分析和删除。API 网络不可达仍然是网络错误，不能被前端本地推断为任务失联。

### 7. 双摄中断按 child 终态参与 Parent 对账

Coordinator 将 `interrupted` 视为 child 的失败型终态：一条 child 成功、另一条 child 失联时，Parent 可以进入既有确定性单视角 fallback；两条 child 都失联或失败时，Parent 进入 `failed` 或 `interrupted` 的明确终态，不再停留在 `waiting_sources`。Parent 自身运行失联时直接标记 Parent `interrupted`。

## Risks / Trade-offs

- [Risk] SQLite 控制面迁移会增加模型、迁移和历史 JSON 兼容工作。→ Mitigation：保留现有 JSON 读取 fallback，先把控制面字段与大产物分离，增加迁移和重启回归测试。
- [Risk] Worker 进程被强制 kill 后无法精确恢复中间算法状态。→ Mitigation：明确 `interrupted` 语义，默认创建新 job 重跑，不伪装成可续跑。
- [Risk] watchdog 与 Worker heartbeat 可能发生状态竞争。→ Mitigation：所有 claim、heartbeat、terminal update 和 interruption update 使用 job id + workerRunId 的条件更新。
- [Risk] 默认超时过短会误判极慢的模型调用。→ Mitigation：heartbeat 不依赖进度回调，阈值必须覆盖多个 heartbeat 周期，并支持环境变量配置。
- [Risk] 新状态会影响现有多处前端 active/terminal 判断。→ Mitigation：统一状态辅助函数，补充任务列表、详情页、Library 和多视角 Parent/Child 测试。
- [Risk] Web 与 Worker 依赖相同本地模型和数据目录，配置不一致会导致 Worker 失败。→ Mitigation：启动脚本共享环境变量，并在 Worker 启动日志记录配置快照和运行实例 ID。

## Migration Plan

1. 增加控制面模型/迁移和历史 JSON 兼容读取，不改变已有 artifact 路径。
2. 为 JobStore 增加跨进程 claim、heartbeat、cancel、terminal update 和 interruption recovery API。
3. 增加独立 Worker 入口，让 API 在 external 模式不启动内嵌 Worker。
4. 将启动/停止脚本改为管理 API、Worker、前端三个进程，并补充日志/PID 清理。
5. 更新后端状态 schema、双摄协调器和启动恢复顺序。
6. 更新前端状态类型、任务详情页、任务列表、Library 轮询和恢复动作。
7. 先在兼容模式运行一轮本地冒烟，再将 external Worker 设为默认；保留 embedded 模式作为回滚开关。

回滚策略：关闭 external Worker 模式并恢复 embedded Worker；控制面保留新增字段，旧客户端继续通过兼容状态读取已完成、失败和取消任务。正在运行的 external Worker 若被回滚停止，其任务由下一次启动按 heartbeat 规则标记为 `interrupted`。

## Open Questions

- 是否需要为 `interrupted` 任务提供“原 job 原地重新排队”，还是始终创建新的 analysis version？本设计默认创建新 job/version。
- SQLite 控制面迁移是否需要在已有本地数据目录上自动执行，还是只对新安装环境启用？建议自动迁移并保留 JSON fallback。
- 正常执行 `app:stop` 时是否等待当前分析安全退出，还是立即结束 Worker 并让下次启动按失联恢复？建议先停止领取、等待有限时间，超时再按中断处理。
