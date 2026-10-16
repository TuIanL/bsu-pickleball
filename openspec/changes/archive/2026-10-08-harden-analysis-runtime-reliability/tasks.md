> 语言约定：本文档用简体中文撰写；`API` / `REST` / `JSON` / `PRAGMA` 等技术术语保留英文。
>
> **执行顺序约束**：第0 组是硬前置——本 change 与 `add-analysis-run-trace-and-error-reporting` 修改同一批文件
> （`analysis_pipeline.py` / `job_orchestration.py`），本change 的控制信号重抛正是在它引入的 `except` 旁边动手。
> **必须先归档那个 change**，否则合并冲突不可避免。

## 0. 前置（硬阻塞）

- [x] 0.1 归档 `add-analysis-run-trace-and-error-reporting` —— **已完成 2026-10-05**。CLI 报告 35/36 并警告 1 项未完成，按用户决策保留 6.1 为已知缺口（外接盘真实写入端到端验证未做）；`+ 7 added` 合入主规格 `openspec/specs/analysis-run-trace/spec.md`（主规格 201 → 202），已按项目流程补写真实 `## Purpose`（CLI 只写 TBD 占位符）。归档路径 `openspec/changes/archive/2026-10-05-add-analysis-run-trace-and-error-reporting/`
- [x] 0.1b **遗留缺口已补验收（2026-10-06）**：读取真实双摄 `take_sync_20260720_121319_e7f03b` 的两路首帧后注入可复现解码失败，实际 Worker 执行两轮；`job-587ff8edc3/run_trace.jsonl` 落在外接盘该 session 的 `analysis/` 中，含完整 retry 异常及策略字段，句柄均释放。证据见 `acceptance-20261008.md`。此验收覆盖真实媒体读取、故障与重试落盘，不代表 joint 算法验收。
- [x] 0.2 记录改动前的测试基线 —— **后端 2026-10-05 实测：1689 passed / 1 failed（145.93s）**，唯一失败为`test_analysis_worker_liveness.py::test_worker_heartbeat_runs_without_stage_progress_callbacks`，与项目记录的历史基线完全一致：后端全量 `pytest tests -q --basetemp=.runtime/<dir> --ignore=tests/test_hybrid_ball_regression_fixture.py --ignore=tests/test_sync_recording.py`（须先 `mkdir -p .runtime`，全量需 `CODEBUDDY_SAFE_DELETE_ENABLED=0`），前端全量 `vitest --maxWorkers=2`
- [x] 0.3 确认已知既有失败不作为本次引入 —— **已用文件交换法证明**：把 `job_orchestration.py` 换回 HEAD 版重跑该测试**同样失败**（1 failed / 11 deselected），随后恢复我的版本。测试文件前 395 行（原有全部）与 HEAD 逐字节一致：`test_analysis_worker_liveness.py::test_worker_heartbeat_runs_without_stage_progress_callbacks`（时序敏感，50ms sleep vs 10ms 心跳）。**判定失败是否自己引入时不要 `git stash`**（工作区含他人未提交改动），用 `git show HEAD:<path> | diff -q - <path>` 逐字节比对
- [x] 0.4 读完速查表并确认目标行号仍与当前工作区一致 —— 抽查 `job_orchestration.py:1251-1261`（`_stop_event` 误用两处）、`:1321`（`failed_event` 检查点）**全部对齐**，无行号漂移

## 1. Worker 关停语义（最高优先，改动量最小）

- [x] 1.1 删除 `job_orchestration.py:1253` 与 `:1259` 的 `self._stop_event.set()`，只保留 `failed_event.set()` —— **已完成**
- [x] 1.2 在 `_heartbeat_loop` 的 docstring 写明语义边界 —— **已完成**，写明「租约丢失只终止本次运行，通过 `failed_event` 表达」「不得置 `_stop_event`（该事件是整个 Worker 关停语义，由 `stop()` 使用并作为 `_loop` 主循环 `while` 条件）」「常见触发：用户取消运行中任务使 job 进终态导致 `mutate(expected_status="running")` 失配」
- [x] 1.3 新增回归测试 —— **已完成**，追加 2 个用例：`test_lease_loss_does_not_stop_worker_from_claiming_next_job`（断言 `_stop_event.is_set() is False`）、`test_worker_loop_keeps_running_after_lease_loss_of_single_job`（断言第二个 job 仍能 claim）。**两者均通过**
- [x] 1.4 验证 `_stop_event` 使用点 —— **通过**：仅剩 `:1167` 创建 / `:1176` clear / `:1185` `stop()` / `:1220` `_loop` while 条件 + 1 处新写docstring 引用，无新增误用

## 2. 控制信号穿透（让刚建立的失败归因体系真正生效）

- [x] 2.1 新建 `backend/app/services/analysis_errors.py` —— **已完成**，含三控制信号异常 + 模块 docstring 明确「只放控制信号、不加业务异常」的边界，把 `JobCanceledError` / `WorkerLeaseLostError` / `StageTimeoutError` 三个类从 `job_orchestration.py:1120/1125/1129` 移入；模块 docstring 写明边界「只放控制信号异常，业务异常留在各自模块」
- [x] 2.2 `job_orchestration.py` 侧 re-export —— **已完成**：改为从 `analysis_errors` import 并保留原导出名。**验证**：`job_orchestration.JobCanceledError is analysis_errors.JobCanceledError` 为 True；`analysis_pipeline` 可直接 import `analysis_errors` **无循环依赖**；三个异常原先仅在本模块内使用（外部零 import），迁移安全（`from app.services.analysis_errors import ...`），确保既有 import 路径不破
- [x] 2.3 在 `except Exception` 之前重抛控制信号 —— **已完成**（新分支在 `:600` 附近，注释说明为何不能落入 `except Exception`）。**验证**：`inspect.getsource` 确认重抛分支索引 < `except Exception as exc:` 索引
- [x] 2.4 移除 `ball_trajectory_status` 二次覆盖 —— **已完成**。`traj_status` 三分支（available/unavailable/failed，`:1342-1359`）已完备，与 `detections_*` 同源；覆盖块已删并加注释说明「两者必须来自同一判定」
- [x] 2.5 pose 中途失败保留已累积帧 —— **已完成**：删掉 `pose_frames = []`，保留 `pose_error = str(exc)`。循环条件 `:2134` 已有 `pose_error is None` 守卫，失败后自动停止继续推理。**验证**：全文仅 `:1906` 一处 `pose_frames = []`（初始化，正确保留），except 块内无销毁
- [x] 2.6 **集成验证完成**：`test_real_pipeline_lease_loss_preserves_classification_and_worker_continuity` 使用实际 JobStore、Worker 与 AnalysisPipeline，证明租约丢失穿透流水线、终态 failureClass=worker_lease、没有错误重试，同一个 Worker 继续领取下一任务。2026-10-08 定向 37 项回归通过。

## 3. 资源生命周期

- [x] 3.1 `analysis_pipeline.py:1778` 的 `cv2.VideoCapture` 及其后全部逻辑（`:1780-2182`）包进同一个 `try/finally: capture.release()`；`debug_writer` / `debug_overlay` 的 close 保留在内层 finally。缩进变更用 `git diff -w` 核对
- [x] 3.2 `isOpened()` 失败路径补 `capture.release()`（虽然未成功打开，但保持与另 3 处 `:151` / `:3132` / `:3182` 的写法一致）
- [x] 3.3 新增回归测试：让窗口准备阶段的 `resolve_analysis_window` 抛异常，并覆盖 `isOpened()` 失败，断言句柄都被释放
- [x] 3.4 `analysis_pipeline.py:1887-1888` 的静默 `pass` 改为 `logger.warning` 并把原因写入标定诊断产物——它当前导致 `calibration_quality` 静默保持 `None` 并传入 `debug_writer.write_frame`（`:2106`）
- [x] 3.5 `analysis_pipeline.py:1720-1723` 的静默 `continue` 至少加 `logger.warning`。**注意风险**：若 `tracking_overlay.json` 损坏，当前会生成「空 overlays 但状态仍 `available`」的叠加视频，需要让状态与实际一致
- [x] 3.6 `tmp_dir`（`core/config.py:44`）补保留期与清理机制：当前被声明并创建但**零消费者**，`kill -9` 的任务残留永久堆积。实现启动期 + 每日 `purge_stale_tmp(max_age_hours)`，按 mtime 清 `data/tmp` 与无对应 running job 的孤儿目录
- [x] 3.7 **删除** `ResourceLimiter.gpu`（`job_orchestration.py:1138`）与 `enable_gpu_jobs` / `max_gpu_jobs` 两个配置项（design Q1 已决策）。依据：`scripts/remote/` 下 `cuda`/`gpu` 零命中（远端无 GPU 部署计划），本机只认 CUDA 不认 MPS、推理 100% 走 CPU，补齐的判断分支永远走不到。**留着配了不生效的选项比没有更糟**
- [x] 3.8 `tmp_dir` 保留期清理机制落地后，验证「崩溃残留」与「正常结束」两条路径行为不同

## 4. 产物落盘一致性

- [x] 4.1 `storage_service.py:103-104` 的 `_job_artifact_root`：当 `capture_take_id` 存在但解析失败时，写入独立的 `outputs/_degraded/<job_id>`，不与正常本地 job 混写同一根。**并在该 job 上打降级标记 + 日志告警；按 design Q2 决策，前端本轮不显示降级 UI**（全仓 `degraded` 零命中，补UI 会明显放大本 change 范围）
- [x] 4.2 修正 `register_capture_job_from_take`（`:69-85`）的 `except Exception: return None`：区分「无 `session_dir`」（合法返回 `None`）与「解析失败」（记 warning + 标记降级）。当前它把数据库连接失败、模型 package 错误一并吞成 `None`
- [x] 4.3 `StorageService._capture_job_roots`（`:29`）加 `threading.RLock`，把 `register_capture_job` 的 `mkdir` + 写入收进同一临界区；`register_capture_job_from_take` 用 `setdefault` 语义避免重复 mkdir
- [x] 4.4 新增并发回归测试：两个请求同时首次访问同一 job 的 artifact（模拟前端并发拉 tracking-overlay + ball-trajectory），断言产物落在同一个根
- [x] 4.5 `storage_service.py` 约 60 个路径构造器统一经 `_safe_join()` 入口（`resolve()` + `is_relative_to` 越界校验）。可先只加入口不改调用，逐步迁移
- [x] 4.6 给 `_safe_join` 补测试：拒绝 `../` 穿越、拒绝绝对路径注入、接受正常相对路径。参考正确写法 `api/routes_analysis.py:783-785`（`Path(file_name).name` + 后缀白名单）
- [x] 4.7 阶段重试幂等：进入下一轮前清理上一次 attempt 的产物（或写显式未完成标记）。消除「`:1142-1143` 写completed 的 `result.json`，第 2 轮失败但 `:1482` 的 `mark_failed` 不写该文件」导致的状态分叉
- [x] 4.8 新增回归测试：构造「第 1 轮写 completed → 第 2 轮中途抛异常」，断言磁盘 `result.json` 与控制面 `canonicalStatus` 不分叉

## 5. SQLite 并发

- [x] 5.1 `database.py` 的 `get_engine()` 用 `event.listens_for(engine, "connect")` 统一施加 PRAGMA，对所有库生效，消除 `app.sqlite3`（实测 `journal_mode=delete`）与 `analysis_control.sqlite3`（WAL）的两套配置不一致
- [x] 5.2 **按路径分支决定是否开 WAL**：主库可能落在外接盘，而 WAL 依赖共享内存 `mmap`，USB 卷上可能失效甚至损坏数据库。用文件系统探测而非硬编码 `/Volumes`；无法确定时**降级为不开 WAL**（保守方向：只损失并发性能，不冒数据损坏风险）
- [x] 5.3 `busy_timeout` 无条件设置（本地与外接盘都安全）
- [x] 5.4 验证：`sqlite3 data/app.sqlite3 "PRAGMA journal_mode"` 在本地路径下返回 `wal`；外接盘路径下不报错且库文件完好


第五组实施记录：主库 engine 与 analysis control plane 共用连接 PRAGMA 策略；仅当两库路径都由系统确认在固定本地卷时启用 WAL，外接或无法识别的卷两者统一使用 DELETE。busy_timeout=30000 与 synchronous=NORMAL 无条件设置。定向测试 7 项通过；本机隔离临时数据库实测 WAL / busy_timeout=30000 / integrity_check=ok，外接卷分支以策略模拟验证 DELETE 与完整性。

## 6. 对外错误信息脱敏

- [x] 6.1 `job_orchestration.py:1472-1482` 路径改为固定用户文案 + `internal_message=result.message`，与 `:1559-1583` 已做对的 public/internal 分层对齐。当前 `:1780` 的 `f"Could not read uploaded video: {video.path}"` 经 `:599` → `:1482` → `:1078-1079` 直接进 `publicErrorMessage`
- [x] 6.2 检查同类点：`:1566`（标定诊断）、`:763`（发球检测）、`:1636` / `:1693`（可视化）把 `{exc}` 拼进 stage detail，而 `stage_from_pipeline`（`:330`）用 `detail=stage.public_message or stage.detail` 一路带到 `AnalysisStage.publicMessage`
- [x] 6.3 `read_analysis_job_logs`（`analysis_run_trace.py:291`）返回前对日志行做路径脱敏（`/Users/[^/\s]+`、`/Volumes/...` → `<path>`）；`_JOB_LOGS_ENABLED` 默认值改为关闭
- [x] 6.4 决定 `runTrace.target`（`job_orchestration.py:1285` 持久化进控制面 payload，随 `GET /jobs` 响应外泄）与 `scanned_files`（`analysis_run_trace.py:302,309`）是否改为逻辑引用。倾向本 change 内一并修（见 design Open Questions 3）
- [x] 6.5 新增测试：构造含绝对路径的失败，断言 `publicErrorMessage` 不含路径、`internalErrorMessage` 含

### 6A. 绝对路径外泄（design Q3 决策：与鉴权同批修）

- [x] 6A.1 `runTrace.target`（`job_orchestration.py:1285` 持久化进控制面 payload，`schemas/analysis.py:338` 是 `AnalysisJobSummary` 字段，`GET /jobs` 响应模型）改为**逻辑引用**（`analysis/<job_id>/run_trace.jsonl`）。当前每次拉任务列表都把外接盘挂载点 `/Volumes/Elements/项目/匹克球/...` 推给前端
- [x] 6A.2 复用 `storage_service` 已有但未使用的 `logical_artifact_reference` 能力，不新造
- [x] 6A.3 `analysis_run_trace.py:302,309` 的 `scanned_files` 改为只返回文件名，不返回绝对路径
- [x] 6A.4 **关键：关掉 `/docs` 挡不住这条路径**，它与鉴权是两条独立的泄露链——鉴权落地后同网段仍可读。因此必须与第 7 组同批完成
- [x] 6A.5 测试：`GET /jobs` 与 `/run-trace` 响应中不出现任何以 `/` 开头的绝对路径

## 7. API 访问控制

- [x] 7.1 新建 `backend/app/core/api_auth.py`：`require_api_token` 依赖，用 `secrets.compare_digest` 做常量时间比较，token 从 `PICKLEBALL_API_TOKEN` 读取
- [x] 7.2 在 `main.py` 把 `require_api_token` 挂到 18 个 router 之外（统一挂载点，不逐个路由装饰）
- [x] 7.3 **无 token 时拒绝启动**（除非 `PICKLEBALL_AUTH_DISABLED=true`）。这是有意的破坏性变更：默认放行等于默认无保护
- [x] 7.4 远端部署关闭 `/docs`、`/openapi.json`、`/redoc`（`main.py:58-63` 未传这三个参数，三者默认开启）
- [x] 7.5 **同步更新 `start-pickleball.command`、`scripts/start-local-runtime.sh` 与 `README`/`docs/`**——不允许只改代码不改文档，否则本地演示会直接起不来
- [x] 7.6 测试：默认无 token 时启动被拒；带正确 token 可访问；带错误 token 返回 401；`PICKLEBALL_AUTH_DISABLED=true` 时豁免


第六、七组实施记录：失败文案与内部错误分层；日志默认关闭并在 API 输出前去掉宿主路径；job/run-trace target 使用逻辑引用，扫描日志仅返回文件名。所有 /api 与 /calibration 路由在统一 HTTP 边界校验 Bearer token，/health 公开；未配置 token 时启动失败，显式测试旁路为 PICKLEBALL_AUTH_DISABLED=true；文档端点关闭。本地启动脚本每次生成随机 token 并传给 API、worker、Vite，curl 文档已补认证头。
验证：pytest 18 passed；analysisClient 16 passed；tsc --noEmit 通过。

后续界面核验发现：浏览器原生 `<video>` 不支持附加 Bearer header，双摄标定中的两个直连视频请求因此被鉴权返回 401。Vite 本地运行时新增同源 `/__analysis_api` 资源代理，由服务端补 Bearer header；视频、海报、诊断视频、摄像头预览、展示流、分析图片和同步锚点导出统一经此入口。真实双摄页面验证两个视频均加载并显示自动角点；后端 Range 响应为 206，自动标定请求 200。

## 8. 前端轮询自恢复与竞态

- [x] 8.1 轮询 `catch` 保留列表并继续重试 —— **已完成**。**注意区分**：`:394` 的 `loadJobs`（**手动刷新**路径）中的 `setJobs([])` **刻意保留**——用户主动点刷新，失败后显示空态+错误是合理设计；只有**轮询** catch 必须保留列表。已加注释说明
- [x] 8.2 恢复计时起点可重入 —— **已完成**：离开 recovering 时重置 `startedAt = 0` 与 `attemptCount = 0`，并加注释说明为何必须重置（否则第二次恢复立即超时且不请求后端，数据被丢弃）
- [x] 8.3 tracks 为空时不回退 0 —— **已完成**：`stoppedDurationMs` 改用 `?? (captureTakeId ? undefined : 0)`，下方 effect 判断由 `!== null` 改为 `typeof === "number"`，以 `undefined` 表达「未知」而非用 0 冒充已知值
- [x] 8.4 `CANCEL_REQUESTED` 死 action —— **已完成**：采用「加 canceling 阶段」方案（首个选项）。`types/capture.ts` 的 `CaptureRuntimeState` 新增 `{ phase: "canceling" }`，reducer 的 `CANCEL_REQUESTED` 从 `return state` 改为 `return { ...state, phase: "canceling" }`。**验证**：`tsc --noEmit` 全绿（无遗漏的穷尽式检查）
- [x] 8.5 `useLiveCoding` 切 take 竞态 —— **已完成**：新增 `takeLoadSeqRef`，每次开始加载自增；三个 `await` 之后与挂 ref 前各校验一次，stale 时 `sender.stop()` 并return。**验证**：`tsc --noEmit` 全绿；eslint 1 warning 与 HEAD 版**同一处**（仅行号 190→224），零新增
- [x] 8.6 时间线事件加载加 seq 守卫 —— **已完成**：新增独立 `timelineLoadSeqRef`（依赖 `fieldSessionId` 故与 take 加载分离），`.then` 内校验 seq，过期则丢弃
- [x] 8.7 `EChart.tsx:155`：把 `onEvents` 从 init effect 依赖中移出（两处调用方 `displayHeatmap.tsx:208` / `recoveryTimeline.tsx:113` 传内联字面量，导致每次重渲染 `dispose` + `init`，用户已缩放的 dataZoom 视口被重置）
- [x] 8.8 5 处轮询在 `document.hidden` 时暂停：`AnalysisJobPage.tsx:215`、`AnalysisTasksPage.tsx:362,372`、`CameraHubPage.tsx:310`、`useCaptureRuntime.ts:170`
- [x] 8.9 轮询依赖数组中的对象改为标量信号（`AnalysisTasksPage` 的 `recordings` / `CameraHubPage` 的 `sessions` 每次 fetch 都是新数组，导致定时器每轮重建）；补 in-flight 守卫（`useCaptureRuntime.ts:170-191` 缺，对照 `useCaptureRuntimeStatus.ts:94` 有 `inFlightRef`）
- [x] 8.10 `useCaptureRuntimeStatus.ts:219-222` 的 `isPolling` 渲染期读 ref 导致失真（`:197-209` 隐藏时只 `clearPollTimer()` 不 setState）→ 改用 `useState` 镜像或从 `phase` + `isVisible` 派生
- [x] 8.11 `analysisRuntimeStore.ts:68-72`：页面隐藏时仍每 5s 唤醒（`!documentVisible` 时 `scheduleNext()` 照调）→ 改由 visibilitychange 恢复时启动
- [x] 8.12 `AnalysisTasksPage` 选择态计算 O(n²)（`:496-497`）改 `Set` 查表（代码库注释提到「580 视频 + 33 sync」，数据量到三位数）
- [x] 8.13 前端测试仍须 `--maxWorkers=2`。补测试：轮询失败后继续重试且保留列表、恢复计时可重入、seq 守卫拦截旧响应

## 9. 门禁与可观测

- [x] 9.1 CI 接入 `ruff check backend/app`。**基线已实测（ruff 0.16.1）：545 errors，其中 151 项可 `--fix` 自动修复**；规则分布 `E501` 322 / `I001` 55 / `UP035` 34 / `F401` 33 / `UP037` 17 / `B905` 17 / `F841` 16 / `E702` 14。注意本机 ruff 在 `~/miniconda3/bin/ruff`（不在 `backend/.venv` 内），`backend/.venv` 无 ruff
- [x] 9.2 制定豁免策略：`E501`（322 项，占59%）需定 line-length 或分目录豁免，避免为过门禁而机械折行；`F841`/`F401` 设error 阻断
- [x] 9.3 修 `quality.yml:47` 的 OpenSpec 校验目标：当前校验 `harden-project-reliability-and-delivery`，而它唯一命中在 `openspec/changes/archive/2026-09-08-...` → 改 `openspec validate --all --strict` 或显式列出活跃 change，禁止硬编码单个易归档名字
- [x] 9.4 补 `PICKLEBALL_RUNTIME_DIR` 的 export —— **已完成**：在 `start-local-runtime.sh` 的**两个**后端子shell（API 与 worker）各加1 行 `export PICKLEBALL_RUNTIME_DIR="$RUNTIME_DIR"`。**验证**：`git diff --stat` 显示纯 8 行新增（每处 4 行：3 行注释 + 1 行 export），`bash -n` 语法通过，无任何意外改动：`start-local-runtime.sh:7` 用它写日志，但 `export PICKLEBALL_*` 清单（`:338-358`）不含它 → 后端读默认路径，`GET /jobs/{id}/logs` 恒返回 `no_matching_log_lines`，**今天刚交付的排障能力静默失效**
- [x] 9.5 把 `PICKLEBALL_RUNTIME_DIR` 的解析收进 `config.py` —— **已完成**：`Settings` 新增 `runtime_dir` 字段 + `PICKLEBALL_RUNTIME_DIR` env 接线 + `resolved_runtime_dir` / `resolved_runtime_logs_dir` 两个 property。路由层 `_runtime_log_dir()` 改为读 Settings。
  **过程记录（重要）**：首次实现让路由层直接调 `get_settings()`，导致 `test_analysis_run_trace_api.py` 失败——`get_settings` 带 `lru_cache`，而测试用 `monkeypatch.setenv` 改环境变量后缓存不刷新。改为仍直接读 `os.environ`（保持可测试性），但缺省值改用 `Path.cwd()/.runtime` 替代 `parents[3]` 猜测。测试恢复 7 passed
- [x] 9.6 修 `analysis_pipeline.py:1816-1817` 的死变量 `clip_start_frame` / `clip_end_frame`（赋值后全文无引用）。**注意相邻的 `decode_start_frame` / `decode_end_frame`（`:1814-1815`）有引用，别一起删**
- [x] 9.7 注意 `F841` 的误报：`roi_filtered_detection_count` / `full_frame_fallback_count`（`:1866-1867`）形似死变量但 `:2313` 有使用，**不要当bug 改**
- [x] 9.8 引入 `@swallow(why=...)` 装饰器（design D6），先对新增/改动代码强制，存量 40 处分批收敛
- [x] 9.9 修 `job_orchestration.py:286-290`：`succeeded` 任务强制把所有 stage 改成 `done/100`，掩盖真实的 failed/skipped 阶段 → 只收敛 `pending`/`active`
- [x] 9.10 修 `:1722` 附近的 `locals().get`（`:918` 的 `_reconstruction_serve_events`、`:935` 的 `tracking_run_output`）→ 在函数顶部显式初始化为 `None`，让未定义变量能被静态检查捕获
- [x] 9.11 **真实 PR 验证完成（2026-10-08）**：[隔离草稿 PR #2](https://github.com/TuIanL/bsu-pickleball/pull/2) 的 [运行 37788800305](https://github.com/TuIanL/bsu-pickleball/actions/runs/37788800305) 明确检出故障样例 F401、静默 broad exception，以及 OpenSpec 缺少 SHALL/MUST 与 Scenario；三个检查均 exit 1。PR 已关闭未合并。本地正常代码 Ruff、增量异常策略与 OpenSpec strict 均通过；该负例不声称完整远端质量作业通过。

## 10. 运行时类型校验（低优先）

- [x] 10.1 引入 `zod`，只为**核心读路径**加 schema：`listAnalysisJobs` / `getAnalysisResult` / `getCaptureTake`（design D8：按「出错可见性」分配校验强度，不追求全量）
- [x] 10.2 以既有类型守卫 `isPipelineResult`（`services/pipelineReportAdapter.ts`）为推广起点
- [x] 10.3 收敛生产代码里的 `as unknown as`（`buildPlayerReportEvidence.ts:86,152,305`、`useLiveCoding.ts:132,137`、`PbCoachInsight.tsx:28`），与 10.1 叠加放大风险
- [x] 10.4 确认 zod 未突破 350 KiB gzip 落地页预算（`scripts/check-landing-budget.mjs` 已在 `npm run build` 中执行）

## 11. 暗色模式与可访问性（低优先）

- [x] 11.1 未迁移的调色板类名改走 `--ui-warning-*` / `--ui-danger-*` / `--ui-brand-*`：`StructuredZoneHeatmap.tsx:298`、`AnalysisSegmentPanel.tsx:220`、`FieldSessionGroupCard.tsx:93,120`、`RecordingTaskCard.tsx:34`、`DeleteToast.tsx:41-42,51`、`displayHeatmap.tsx:199`、`ScoreBoard.tsx:39`
- [x] 11.2 硬编码 hex 共 164 处统一走主题变量，重点是 `AnalysisTasksPage.tsx:1084`（`bg-[#F8FBF4]` 近白出现在双摄回放弹层）、`RallyShotTimeline.tsx` 4 处浅底、`AnalysisFlowSelector.tsx` 三态底色（暗色下「选中」看起来像「禁用」）。**完成**：全 `src/**/*.tsx` 的 200 处任意值颜色 utility 已迁移至 `--ui-*` / `--capture-*` 语义变量；可视化/舞台固定调色板集中为 `--ui-display-*`。暗色主题为界面状态与表面提供对应取值；视觉回归仍由 11.7 人工完成。
- [x] 11.3 `Modal.tsx:47-58` 补 `role="dialog"` / `aria-modal="true"` / `aria-labelledby` + focus trap + 焦点归位（被 6 处复用）
- [x] 11.4 渲染期 `window.location` 读取收进 `router.parseLocation`（`AnalysisJobPage.tsx:65`、`MultiViewAnalysisSetupPage.tsx:350-351`、`AppRouter.tsx:113`、`LibraryItemWorkspace.tsx:59`）。注意 `AppRouter.tsx:113` 的 `as "cam_1"|"cam_2"` 断言会让 `?cam=x` 以 `cam="x"` 流进 `RecordingAnalyzePage`
- [x] 11.5 删除 `AnalysisJobPage.tsx:85-89`、`:163-178` 中从不生效的 `useMemo`（依赖是每次渲染新建的对象），或把 `origin` 本身 `useMemo` 住
- [x] 11.6 `useDisplayViewGeometry.ts:160-161` 渲染期 `JSON.stringify` + `JSON.parse` → 改用显式浅比较 key
- [x] 11.7 **人工视觉验收通过（2026-10-08）**：用户确认刷新比赛库和双摄标定页、切换主题后，两路画面、角点、按钮文字和页面背景均正常。

第八组本轮完成：图表事件处理不再因内联 handler 重建实例；轮询隐藏时暂停、恢复时立即对账，并加入在途保护；任务列表选择改用 Set。新测试覆盖图表 handler 更新、轮询失败后恢复、恢复周期重入、旧响应拦截和隐藏标签页。

第九组本轮完成 9.1–9.10：CI 执行 Ruff 的 F401/F841 阻断规则，保留既有长行等基线，不机械格式化存量；OpenSpec CI 动态校验活跃 change；死变量、异常吞并、任务阶段归一化和 `locals().get` 已处理。9.11 仍需真实 PR 验证门禁。

第十组本轮完成：核心 API 响应使用 Zod 校验；最终生产构建通过，落地页静态 JS gzip 为 141,787 字节，低于 350 KiB 预算。

第十一组本轮完成状态：11.1–11.6 已完成。11.2 将全体任意值颜色 utility 迁移到语义变量；展示舞台和可视化调色板使用固定的 `--ui-display-*` / `--capture-*` 变量，避免把数据色误当成界面状态色。`npm run build` 通过，色值 utility 扫描为零，主题变量引用扫描未发现无定义且无 fallback 的变量。11.7 已于 2026-10-08 由用户确认通过。

最终验证（2026-10-05）：后端全量 1,719 passed、17 warnings；前端全量 95 文件 / 738 用例通过；`ruff check backend/app` 通过；生产构建通过（落地页静态 JS gzip 141,787 字节）；`openspec validate harden-analysis-runtime-reliability --strict` 通过；`openspec/specs/` 的 TBD 扫描零命中。

## 12. 收尾

- [x] 12.1 后端全量：`cd backend && mkdir -p .runtime && pytest tests -q --basetemp=.runtime/full --ignore=tests/test_hybrid_ball_regression_fixture.py --ignore=tests/test_sync_recording.py`（全量需 `CODEBUDDY_SAFE_DELETE_ENABLED=0`；日志勿放 basetep否则会被 rmtree）
- [x] 12.2 前端全量：`npm test -- --maxWorkers=2`（否则 SIGTERM / exit 137）
- [x] 12.3 `openspec validate harden-analysis-runtime-reliability --strict` 通过
- [x] 12.4 复核 `grep -rin "TBD" openspec/specs/` 零命中
- [x] 12.5 **存储验收完成**：真实 Elements session 写入和解码句柄释放通过；按 design 2026-10-06 决策，使用可丢弃磁盘镜像实际挂载/卸载/重挂，验证正常落点、持久降级理由与恢复后读原产物。2026-10-08 用户重连 Elements 后两路真实视频 Range 均 206。验收未主动卸载用户原始素材卷，范围与证据见 `acceptance-20261008.md`。
- [x] 12.6 **提交拆分完成（2026-10-08）**：独立 UI、CI、后端 runtime/trace、前端生命周期/同源鉴权四个提交已保存到本地审阅分支 `codex/harden-analysis-runtime-reliability-20261008`。共享文件按 hunk 拆分，保留四人身份与切分算法改动；主分支与原暂存区保持不变。隔离快照后端 1,685 / 前端 751 全量通过，构建、Ruff 和异常策略门禁通过。详见 `acceptance-20261008.md`。
- [x] 12.7 **归档完成（2026-10-08）**：归档到 `openspec/changes/archive/2026-10-08-harden-analysis-runtime-reliability/`，同步 32 条新增、13 条修改，并为三个新主规格补写真实 Purpose。
- [x] 12.8 **范围移交完成，算法审核仍待做**：按 design Q5，把多摄身份链独立审核列入 `restore-confirmed-four-player-joint-analysis` 的 6.5。此项仅记录移交，不声明四人身份算法通过验收。


---

## 第一批实施小结（2026-10-05）

**后端全量：1691 passed / 1 failed**（基线 1689/1，新增 2 个即本change 的 liveness 回归用例）。
唯一失败 `test_analysis_worker_liveness.py::test_worker_heartbeat_runs_without_stage_progress_callbacks` 已用文件交换法证明早于改动（HEAD 版源文件同样失败）。

**前端全量：89 文件 / 693 用例，1 failed**。注意用例总数与历史基线（93/728）不同——本轮为实测值，跨时点不可直接比较。

**该 1 个失败是既有的 flaky 测试，非本change 引入**，证据：
1. 失败文件 `src/pages/AnalysisJobPage.test.tsx` 不在本 change 改动范围内。
2. 同一份代码连续两次跑该文件：第 1 次 `1 failed | 16 passed`，第 2 次 `17 passed` 全过 → 不稳定。
3. 把本 change 全部 5 个改动文件还原为 HEAD 版后重跑，该文件反而 `5 failed | 12 passed`（更差）→ 我的版本不劣于 HEAD。
**按项目惯例只报告不修**（既有时序敏感/不稳定用例超出本 change 范围）。

**lint 零新增**：改动文件 eslint 与 HEAD 版 warning 计数一致（AnalysisTasksPage/useCaptureRuntime/types/capture 均 5 warnings→5 warnings；useLiveCoding 1→1）。
