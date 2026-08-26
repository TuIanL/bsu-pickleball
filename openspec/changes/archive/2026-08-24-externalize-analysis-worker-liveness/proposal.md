## Why

当前分析 Worker 运行在 FastAPI Web 服务进程的 daemon thread 中。开发环境的 `uvicorn --reload`、后端进程崩溃或 Worker 线程异常都会让分析任务停止，但任务摘要仍可能长期保持 `processing`，前端因此永远显示“分析中”。分析任务需要独立于 Web 服务生命周期运行，并且能够被可靠地判断为仍在执行、已经失联或已被服务重启中断。

## What Changes

- 将真实分析执行从 FastAPI 进程内 Worker thread 移到独立的 analysis-worker 进程；Web API 只负责创建、查询、取消和投影任务状态。
- 为运行中的任务增加 Worker 身份、运行实例、领取时间、心跳时间、最后进度时间和中断原因等持久化信息。
- 增加独立的心跳与超时检测策略，避免用普通 `updatedAt` 推断 Worker 是否存活。
- 服务启动时恢复可继续领取的 queued 任务，并将没有新鲜 Worker 心跳的 running 任务标记为 `interrupted`。
- 将任务控制面改造成可安全支持 Web API 与独立 Worker 跨进程访问的持久化边界；分析产物继续使用现有文件系统路径。
- 为取消、领取、心跳、状态更新和任务删除补充跨进程一致性语义，避免 stale cache 或并发写入覆盖状态。
- 前端新增“任务失联”展示和恢复动作；失联任务不再被当作活跃的“分析中”任务持续轮询或允许普通取消。
- 更新双摄 Parent/Child 编排，使 child 中断能够推进 Parent，而不会让 Parent 永远停留在 `waiting_sources`。
- 更新本地启动、停止、日志和 PID 管理脚本，使 Web API 热重载不会停止 analysis-worker。

## Capabilities

### New Capabilities

- `analysis-worker-liveness`: 定义 Worker 心跳、租约超时、失联判定、服务启动恢复和中断任务的持久化契约。

### Modified Capabilities

- `analysis-job-orchestration`: 修改任务控制面、Worker 领取、跨进程状态更新、恢复和 `interrupted` 生命周期语义。
- `analysis-task-management`: 修改任务列表对失联/中断任务的状态展示、轮询、删除和重新分析动作。
- `video-analysis-job-flow`: 修改任务详情页对失联任务的终态展示、错误说明和恢复入口。
- `local-runtime-commands`: 修改本地运行时，使 API 与 analysis-worker 分进程启动、停止、记录 PID 并分别记录日志。
- `multiview-analysis-orchestration`: 修改 Parent/Child 中断传播和启动对账语义。

## Impact

- 后端任务模型、JobStore、任务状态 schema、分析 Worker runtime、启动生命周期和 API 查询/取消路径。
- 可能新增或调整 SQLite 控制面表及迁移；现有任务 JSON、分析结果和视频产物需要兼容读取。
- `backend/app/services/job_orchestration.py`、`backend/app/services/mock_analysis.py`、`backend/app/services/multiview_coordinator.py`、分析 schema 与相关 API 路由。
- 前端分析任务类型、状态辅助函数、运行时轮询 store、任务列表、任务详情页、素材工作区和 Library 状态投影。
- `scripts/start-local-runtime.sh`、`scripts/stop-local-runtime.sh`、后端 Worker 入口、运行日志与 PID 文件。
- 不引入 Redis、Celery 或多主机调度；本变更面向单机本地产品运行，重点是跨 Web/Worker 进程的可靠任务控制面。
