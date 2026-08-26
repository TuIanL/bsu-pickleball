## 1. 控制面与状态模型

- [x] 1.1 盘点现有 JobStore、任务 JSON、状态 schema 和历史任务读取路径，确定 SQLite 控制面字段与兼容映射
- [x] 1.2 增加 SQLite 控制面初始化与迁移，保存任务摘要、队列排序、取消请求、Worker lease、heartbeat、阶段遥测和 terminal 信息
- [x] 1.3 为历史 `data/outputs/jobs/*.json` 增加一次性导入或只读 fallback，确保旧任务可查询且不覆盖新控制面状态
- [x] 1.4 重构 JobStore 为跨进程安全的 claim、heartbeat、进度更新、取消、terminal update、interruption recovery、查询和删除接口
- [x] 1.5 扩展后端状态枚举与任务摘要 schema，加入 `interrupted`、Worker liveness 字段、中断原因和用户安全的错误说明

## 2. Worker 心跳与外置执行

- [x] 2.1 实现 `python -m app.analysis_worker` 独立入口，复用现有分析 Pipeline、模型配置、取消令牌和产物目录
- [x] 2.2 为 Worker 增加运行实例 ID、进程身份和 execution lease，领取任务后立即写入首次 heartbeat，并使用条件更新防止重复 claim
- [x] 2.3 实现独立于阶段进度回调的 heartbeat 循环，支持 `PICKLEBALL_` heartbeat interval/timeout 配置，并在控制面写入失败时停止领取新任务
- [x] 2.4 将 Worker 的阶段进度、成功、失败、取消和异常路径改为带 `workerRunId` 条件的持久化更新，避免 stale Worker 覆盖新状态
- [x] 2.5 让 Worker 在安全检查点读取跨进程取消请求，并实现优雅停止领取、有限等待和强制终止后的失联恢复语义
- [x] 2.6 保留可回滚的 embedded Worker 兼容开关，但 external 模式下 FastAPI lifespan 不得创建内嵌 Worker thread

## 3. 启动恢复与 API 任务操作

- [x] 3.1 在服务启动阶段按“初始化控制面 → 迁移历史任务 → 回收过期 running → multiview 对账 → 启动/连接 Worker”的顺序执行恢复
- [x] 3.2 实现 heartbeat watchdog：新鲜 running 保持运行，过期 running 条件更新为 `interrupted` 并记录稳定中断码、时间和最后进度
- [x] 3.3 更新创建、列表、详情、进度、取消、删除和重新分析 API，使查询读取持久化控制面，terminal 状态和失联任务操作符合规格
- [x] 3.4 为 API 增加 `interrupted` 的稳定响应与用户安全文案，区分任务失联和 API 网络不可达错误
- [x] 3.5 为并发取消、heartbeat、超时回收、完成提交和删除增加条件更新及幂等处理，并保证 terminal 状态不可被普通操作回退

## 4. 本地运行时进程管理

- [x] 4.1 修改 `scripts/start-local-runtime.sh`，分别启动 API、独立 analysis-worker 和前端，复用分析环境并记录独立 PID/log
- [x] 4.2 修改 `scripts/stop-local-runtime.sh`，按 Worker、API、前端顺序执行优雅停止，处理 stale PID 并清理运行时文件
- [x] 4.3 增加端口占用、重复启动、Worker 启动失败和配置不一致的诊断信息，不让 API reload 重新创建或停止 Worker
- [x] 4.4 更新本地运行文档，说明 external Worker、PID/log 位置、heartbeat 配置、优雅停止和任务失联排查方法

## 5. 双摄 Parent/Child 对账

- [x] 5.1 扩展 multiview coordinator 的 child 终态集合，将 `interrupted` 纳入失败型 child，并持久化机位最后进度与失联信息
- [x] 5.2 实现单路成功加另一路 failed/canceled/interrupted 时的确定性 fallback，以及双路失败型终态时 Parent 的明确 failed/interrupted 结束
- [x] 5.3 调整启动 reconciliation 顺序和幂等性，确保 child heartbeat 回收后 Parent 不再停留在 `waiting_sources`，可执行 Parent 能回到 queued
- [x] 5.4 增加 Parent/Child 摘要和 API 返回的历史字段兼容解析，避免旧单摄任务和旧双摄任务改变既有渲染

## 6. 前端失联状态与恢复入口

- [x] 6.1 扩展分析任务类型、状态辅助函数和文案映射，将 `interrupted` 作为独立终态并暴露 heartbeat、interruption code、last progress 字段
- [x] 6.2 更新 `analysisRuntimeStore` 与相关轮询逻辑：只轮询 queued/新鲜 running，收到 durable interrupted 后停止轮询且不把网络错误本地推断为失联
- [x] 6.3 更新任务列表和 Library 状态投影，显示“任务失联”、最后阶段/进度和恢复动作，不再把 interrupted 当作“分析中”或允许普通取消
- [x] 6.4 更新分析任务详情页和阶段 stepper，展示失联时间、最后 heartbeat、用户安全说明，并提供重新分析、查看详情和删除入口
- [x] 6.5 更新结果路由与操作按钮：interrupted 任务只进入恢复/not-ready 页面，不得因存在部分 artifact 而打开完成态结果
- [x] 6.6 覆盖单摄、双摄 Parent/Child、历史状态别名和失败/取消/完成任务的状态渲染，保持既有导航和权限边界

## 7. 自动化验证与本地冒烟

- [x] 7.1 增加控制面迁移、历史 JSON 兼容、单次 claim、heartbeat 条件更新、取消竞争和 terminal 幂等测试
- [x] 7.2 增加 heartbeat 超时、Worker 崩溃/强制终止、服务启动恢复和 API reload 不杀 Worker 的后端集成测试
- [x] 7.3 增加 Worker 长阶段无进度仍发送 heartbeat、成功/失败/取消/失联状态转换和 artifact 引用一致性测试
- [x] 7.4 增加 multiview child interruption、fallback、双路失败终止和启动 reconciliation 测试
- [x] 7.5 增加前端状态辅助函数、轮询停止、任务列表/详情文案、恢复按钮和结果路由测试
- [x] 7.6 执行格式检查、后端测试、前端测试和 local runtime 冒烟：启动后确认三组 PID，触发 API reload，观察 Worker heartbeat，并验证失联任务不再显示“分析中”
