## Why

2026-10-04 对全仓（后端 320 个 `.py` / 101,360 行，前端 278 个 `.ts|.tsx` / 57,550 行）做了一次覆盖式静态审核，结论是：**系统存在多处「静默失效」缺陷——它们不报错、不崩溃，只是 quietly 地停止工作、丢数据或说谎。** 这类缺陷比崩溃危险，因为崩溃会被发现。

四类实证：

1. **资源泄漏伪装成任务失败**：`analysis_pipeline.py:1778` 的 `cv2.VideoCapture` 是全文件 4 处中**唯一没有 `try/finally` 保护**的一处，裸打开 236 行后才在 `:2175` 释放。窗口内有 6 个可抛点（ROI 计算、标定诊断、模型装配、`BallTracker` 构造等），任一抛异常都跳过 `finally` 泄漏 ffmpeg 句柄，而异常本身被 `run()` 的 `except Exception` 吞成「任务失败」，运维无法定位是资源问题。

2. **用户取消一个任务会停掉整个 Worker**：`_heartbeat_loop`（`job_orchestration.py:1253`、`:1259`）在检测到租约丢失时调用 `self._stop_event.set()`。但 `_stop_event` 是「**整个 Worker 关停**」语义——`:1185` 的 `stop()` 用它，`:1220` 的 `_loop` 用它作 `while` 条件。置位后主循环**永久退出、不再领取任何后续任务**，且 embedded 模式无自愈路径（`main.py:47` lifespan 只启动一次）。而「用户取消一个运行中的任务」恰好就会让 `heartbeat` 返回 False（job 进终态 → `mutate` 的 `expected_status="running"` 失配）。

3. **失败归因体系被自己的异常处理绕过**：`:571` 的 `try` 块**包住**了 `:571-573` 的第一次 `_notify_progress(progress_callback, ...)`，而 `progress_callback`（`job_orchestration.py:1321-1324`）会 `raise WorkerLeaseLostError` / `token.raise_if_cancelled()`。这三个控制信号都继承 `RuntimeError`，于是落进 `:594` 的 `except Exception`，被转成 `status="failed"` 的 result 返回。编排层 `:1358-1366` 的捕获顺序**是正确的**（三个控制信号先于 `Exception`），但异常根本没机会冒上来。后果：租约丢失与用户取消被记成 `internal_defect`——**与刚建立的 7 类正交归因体系直接相悖**。

4. **外接盘掉线时全量产物静默改道本地盘**：今天已修`resolve_run_trace_path`（走只读的 `_read_capture_session_dir`），但 `_job_artifact_root`（`storage_service.py:103-104`）与其依赖的 `register_capture_job_from_take`（`:69-85`，`:80` 调用会 `mkdir` 的 `register_capture_job`、`:84` 吞掉异常）**仍在原处**。于是 `tracking` / `ball_trajectory` 等 **40+ 个artifact 路径**在盘离线时全部落到本地 `outputs/<job_id>`，任务**照常 `succeeded`、零降级痕迹**。`:84` 还把数据库连接失败、模型 package 错误等无关异常一并吞成 `None`，调用方无法区分「take 没有 session_dir」和「DB 挂了」。

此外还实测到：`app.sqlite3` 的 `journal_mode=delete`（非 WAL，而 `analysis_control.sqlite3` 是 WAL，两套配置不一致），在多线程/多进程并发写下会 `database is locked`；后端**全站零鉴权**且 `/docs`、`/openapi.json` 默认开启，使任何可达方可拉取完整 API 契约并读取含绝对路径的错误消息与运行日志；前端两处轮询在**一次网络抖动后永久停摆**（`AnalysisTasksPage` 的 `catch` 既不重排定时器又 `setJobs([])`，而同项目 `AnalysisJobPage.tsx:225` 做了 `scheduleLoad(3000)` —— 是遗漏而非设计）。

结论：这些不是可以排期到「以后再说」的技术债。**1、2、3 三条每天都在真实损伤现场能力**——泄漏句柄、停掉 Worker、把取消误报成失败。必须先修。

## What Changes

### 一、资源与关停语义（最高优先）

- 把 `_run_tracking` 的 `cv2.VideoCapture` 及其后全部逻辑包进同一个 `try/finally: capture.release()`，与同文件 `:151` / `:3132` / `:3182` 三处的正确写法对齐。
- `_heartbeat_loop` 在租约丢失时**只置 `failed_event`，不再置 `_stop_event`**。`failed_event` 已在 `:1321` / `:1446` / `:1457` 被正确检查，足以表达「租约丢失」。若确需退出 Worker，另立独立 `_fatal_event` 并交由守护循环重启。
- `pose_frames` 在中途失败时**保留已累积帧**，改为停止继续推理而非销毁已有结果（`:2137-2139` 当前 `pose_frames = []`）。

### 二、控制信号与失败归因

- `AnalysisPipeline.run` 在 `except Exception` 之前显式重抛 `JobCanceledError` / `WorkerLeaseLostError` / `StageTimeoutError`，使控制信号能到达编排层已有的正确捕获分支。三个异常下沉到独立模块以规避循环 import。
- 终态失败对外只暴露固定用户文案，异常原文（含绝对路径）收进 `internalErrorMessage`，与 `:1559-1583` 通用异常路径已做对的 public/internal 分层对齐。
- 阶段内重试在进入下一轮前清理上一次 attempt 的产物（或写 `_incomplete` 标记），消除「第 1 轮写 completed 的 `result.json`、第 2 轮失败但 `mark_failed` 不写该文件」导致的状态分叉。
- `ball_trajectory_status` 移除 `:1374-1376` 的二次覆盖，使 stage 图与 artifact 字段不再互相矛盾。

### 三、产物落盘一致性

- `register_capture_job_from_take` 区分「无 `session_dir`」（返回 `None` 合法）与「解析失败」（记 warning + 在 job 上标记降级）；`capture_take_id` 存在但解析失败时写入独立的 `outputs/_degraded/<job_id>`，不再与正常本地 job 共用根。
- 约 60 个路径构造器统一经单一 `_safe_join()` 入口，做 `is_relative_to` 越界校验。
- 临时目录补保留期与清理机制（当前 `tmp_dir` 被声明并创建但**零消费者**，`kill -9` 的任务残留永久堆积）。

### 四、SQLite 并发

- 把 `journal_mode` / `busy_timeout` / `synchronous` 收进 `get_engine()`，对所有库统一施加，消除两套配置不一致。**若主库可能落在外接盘则不得开 WAL**（依赖 `mmap`，USB 卷有损坏风险），须按路径分支处理。
- `StorageService._capture_job_roots` 加 `threading.RLock`，把 `mkdir` + 写入收进同一临界区，与 `JobStore` 已有的 `RLock` 对齐。

### 五、API 暴露面

- 新增共享鉴权依赖 `require_api_token`（`PICKLEBALL_API_TOKEN` + `secrets.compare_digest`），挂在 `include_router` 之外；**无 token 时拒绝启动而非放行**，本地开发用 `PICKLEBALL_AUTH_DISABLED=true` 显式豁免。
- 远端部署关闭 `/docs`、`/openapi.json`、`/redoc`。

### 六、前端轮询与竞态

- 任务列表轮询在 `catch` 中保留上一次 `jobs` 并继续退避重试，不再永久停摆。
- 录制恢复的计时起点在离开 `recovering` 时重置，避免第二次恢复立刻判超时并丢弃实际已就绪的数据。
- `useLiveCoding` 切 take 时用递增 seq 守卫，阻止旧异步结果覆盖新状态与 sender 泄漏。
- ECharts 的 `onEvents` 从 init effect 依赖中移出，避免每次重渲染 `dispose` + `init`。
- 轮询在 `document.hidden` 时暂停，恢复可见时补一次对账。
- 轮询依赖数组中的对象改为标量信号，并补in-flight 守卫。

### 七、门禁与可观测

- CI 接入 `ruff check backend/app`（配置已存在于 `pyproject.toml`，但 `quality.yml` 中出现 0 次；当前 545 个 lint 错误无人拦截）。
- 修正 OpenSpec 校验目标：现校验的是已归档对象，当前两个活跃 change 从未被 `--strict` 校验过。
- 引入 `@swallow(why=...)` 装饰器强制声明可吞异常的理由（当前 40 处 handler 只有 `pass`/`continue`；2026-10-04 复核修正，初版统计 115 处因判定条件把嵌套双层 except 计入），不逐个加日志。
- 补 `PICKLEBALL_RUNTIME_DIR` 的 export（当前脚本用了它写日志却不导出给后端，导致 `/logs` 端点恒返回 `no_matching_log_lines`）。

### 八、类型与主题一致性（低优先）

- 为核心读路径引入运行时 schema 校验（当前 `zod`/`valibot`/`ajv` 一个都没装，`requestJson` 直接 `as Promise<T>`）。
- 暗色模式未迁移的调色板类名与硬编码 hex 统一走 `--ui-*` 语义变量。

### 非目标（本次明确不做）

- **不改任何算法逻辑**：身份链门限、坐标变换、球检测策略、P1/P2=A端分侧假设等一律不动。本 change 只修「让正确逻辑被正确执行」的基础设施缺陷。
- 不做依赖 CVE 扫描与自动升级。
- 不做前端视觉回归验证（按项目约定由人工执行）。
- 不重构 `analysis_pipeline.py`（3317 行）等超长模块的结构，只在缺陷点做最小手术。
- 不处理多摄身份链的算法正确性（另一活跃 change `restore-confirmed-four-player-joint-analysis` 的范围）。

### 破坏性变更

- **后端默认启动行为改变**：未设置 `PICKLEBALL_API_TOKEN` 且未设置 `PICKLEBALL_AUTH_DISABLED=true` 时，服务**拒绝启动**。这是有意的——默认放行等于默认无保护。
- API 文档端点在远端部署后返回 404。

## Capabilities

### New Capabilities
<!-- 全新引入的能力。每项对应一个 specs/<name>/spec.md -->
- `resource-lifecycle-integrity`: 视频解码句柄、模型推理中间态、临时目录的生命周期契约——异常路径不得泄漏资源，不得销毁已累积的有效结果。
- `api-access-control`: 后端 API 的鉴权契约与文档端点暴露面控制，含无凭据时的启动行为。
- `runtime-silent-failure-guardrails`: 跨前后端的「静默失效」防护契约——轮询自恢复、异常吞没的显式化、类型假设的运行时校验。

### Modified Capabilities
<!-- 现有主规格中需求发生变化的。只有 spec 级行为变化才列入。 -->
- `analysis-worker-liveness`: 租约丢失不得停掉 Worker 主循环；Worker 关停与单任务失败必须是两个独立语义。
- `analysis-job-orchestration`: 控制信号异常（取消/租约丢失/阶段超时）必须穿透 pipeline 到达编排层，不得被转成普通任务失败；终态对外只暴露脱敏文案；阶段重试必须清理上一轮产物。
- `analysis-artifacts`: 路径构造必须做越界校验；外接存储不可用时产物降级必须显式可观测，不得与正常本地 job 混写同一根。
- `codebase-quality-gates`: CI 必须实际执行已配置的 `ruff`；OpenSpec 校验目标不得指向已归档 change。
- `frontend-capture-runtime`: 录制恢复的计时起点必须可重入；`elapsedMs` 在终态缺失轨迹时不得回退为 0；`CANCEL_REQUESTED` 必须有真实状态迁移。
- `frontend-architecture-boundaries`: 轮询 effect 的依赖不得含每次渲染新建的对象；`onEvents` 不得进入图表 init effect 的依赖数组。
- `analysis-task-management`: 任务列表轮询在请求失败后必须继续重试，且不得清空已有列表。

>刻意留空 `Modified Capabilities` 中的纯实现细节项（如 `@swallow` 装饰器本身的形态、SQLite PRAGMA 的具体取值）——它们由 `resource-lifecycle-integrity` / `codebase-quality-gates` 的新需求覆盖，不重复开 delta。

## Impact

**后端**
- `services/analysis_pipeline.py`（3317 行）：句柄保护、控制信号重抛、pose 帧保留、状态字段覆盖、重试产物清理
- `services/job_orchestration.py`（1679 行）：`_stop_event` 语义、控制信号异常模块、终态文案分层
- `services/storage_service.py`：路径构造收敛、`_capture_job_roots` 加锁、外接盘降级
- `app/database.py`：SQLite PRAGMA 统一
- `app/main.py`：鉴权依赖挂载、文档端点开关
- 新增：`app/services/analysis_errors.py`（控制信号异常）、`app/core/api_auth.py`（鉴权依赖）

**前端**
- `pages/AnalysisTasksPage.tsx`：轮询重试与保留列表
- `hooks/useCaptureRuntime.ts`：恢复计时重置、`elapsedMs` 终态回退
- `hooks/useLiveCoding.ts`：seq 守卫
- `components/platform/viz/EChart.tsx`：事件绑定解耦
- `components/platform/Modal.tsx`：dialog 语义与焦点管理
- 暗色未迁移类名与硬编码 hex（散布于`DeleteToast` / `RecordingTaskCard` / `ScoreBoard` / `AnalysisSegmentPanel` 等通知类组件）

**CI**
- `.github/workflows/quality.yml`：接入 `ruff`、修正 OpenSpec 校验目标

**兼容性**
- 现有前端 728 用例、后端 1689 用例必须保持通过（后端唯一既有失败 `test_analysis_worker_liveness.py::test_worker_heartbeat_runs_without_stage_progress_callbacks` 为时序敏感且已证既有，本次不修）。
- 前端全量测试仍须 `--maxWorkers=2`。
- 鉴权默认拒绝启动会改变本地起服务的方式，需同步 `start-pickleball.command` 与文档。
