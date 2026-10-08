> 语言约定：本文档用简体中文撰写；`API` / `REST` / `JSON` / `PRAGMA` 等技术术语保留英文。

## Context

本 change 源于 2026-10-04 的一次覆盖式静态审核（后端 320 个 `.py` / 101,360 行，前端 278 个 `.ts|.tsx` / 57,550 行）。审核的价值不在于「找到了多少行风格问题」，而在于揭示了一个共同根因：

**这套系统大量使用「宽泛捕获 + 静默继续」的错误处理风格，而系统缺少与之配套的观测与门禁。**

单独看每一处都像是局部疏忽，但它们叠加后构成了一个失效模式：**系统不报错、不崩溃，只是 quietly 地停止工作、丢数据或说谎。** 这比崩溃危险，因为崩溃会被发现。

三个最具代表性的实例（均已逐行复核，非推断）：

1. `analysis_pipeline.py:1778` 的 `cv2.VideoCapture` 是全文件 4 处中唯一没有 `try/finally` 的（另 3 处 `:151` / `:3132` / `:3182` 都正确），裸打开 236 行后才在 `:2175` 释放。而 `run()` 的 `except Exception`（`:594`）会把任何窗口内异常转成「任务失败」，运维看到的是普通失败，**看不到句柄泄漏**。

2. `_heartbeat_loop`（`job_orchestration.py:1253`、`:1259`）用 `self._stop_event.set()` 表达「这个 job 丢了租约」。但 `_stop_event` 是「整个 Worker 关停」语义——`:1185` 的 `stop()` 用它，`:1220` 的 `_loop` 用它作 `while` 条件。置位后主循环永久退出。而「用户取消一个运行中的任务」恰好就会让 `heartbeat` 返回 False。

3. `:571` 的 `try` 块**包住**了 `:571-573` 的第一次 `_notify_progress(progress_callback, ...)`。`progress_callback` 会抛控制信号异常，落进 `:594` 的 `except Exception` 被转成 `status="failed"`。编排层 `:1358-1366` 的捕获顺序**是正确的**——但异常根本没机会冒上来。**正确的代码因为被放在错误的位置而完全失效。**

### 约束

- **不改动任何算法逻辑。** 身份链门限、坐标变换、球检测策略、P1/P2=A 端分侧假设等一律不动。本 change 只修「让正确逻辑被正确执行」的基础设施。
- **后端 1689 用例 / 前端 728 用例必须保持通过。** 后端唯一既有失败 `test_analysis_worker_liveness.py::test_worker_heartbeat_runs_without_stage_progress_callbacks` 是时序敏感且已用 `git show HEAD:<path> | diff -q` 证明为既有，本次不修。
- **前端全量测试须 `--maxWorkers=2`**（否则 SIGTERM / exit 137）。
- **pytest 须 `--basetemp=.runtime/<dir>`** 且先 `mkdir -p .runtime`。
- **本机推理 100% CPU**（设备选择只认 CUDA，不认 MPS）。
- 与两个活跃 change 并行：`add-analysis-run-trace-and-error-reporting`（35/36，失败归因）与 `restore-confirmed-four-player-joint-analysis`（23/28，四人身份链）。本 change 不侵入二者 scope，但**与前者共享 `job_orchestration.py` 与 `analysis_pipeline.py`**，需注意合并顺序。

### 利益相关方

单一团队（竞赛项目）。**没有外部署环境的硬约束**——但正因为要部署到远端（AutoDL / 云主机），零鉴权从「不阻塞」变成「必须」。

## Goals / Non-Goals

**Goals:**

- **消除每日损伤现场能力的缺陷**：句柄泄漏、Worker 误停、控制信号被吞——这三项每天都在真实消耗可用性。
- **让「失败」与「沉默」在架构上不可混淆**：任何被吞掉的异常都必须留下声明过的痕迹；任何静默降级都必须可观测。
- **把可观测性断链补齐**：`PICKLEBALL_RUNTIME_DIR` 未导出导致今天刚交付的 `/logs` 端点恒返回 `no_matching_log_lines`——这不是「功能缺失」，是**排障能力静默为零**。
- **让门禁真正生效**：`ruff` 配置已写好却 0 次执行、OpenSpec 校验指向已归档对象，这两处让「门禁已覆盖」成为假信号。
- **远端部署前消除零鉴权**这一明确的攻击面。

**Non-Goals:**

- 不做依赖 CVE 扫描与自动升级。
- 不做前端视觉回归验证（按项目约定由人工执行）。
- 不重构 `analysis_pipeline.py`（3317 行）等超长模块的结构，只在缺陷点做最小手术。
- 不处理多摄身份链的算法正确性（属另一活跃 change）。
- 不把 40 处静默异常逐个加日志——逐个加日志的收益不抵噪音，**必须用机制而非人力解决**。
- 不承诺「消灭所有静默异常」。目标是**让每一处静默都有显式声明与可审计的审查面**。

## Decisions

### D1：控制信号异常下沉到独立模块，而非就地加 except

**问题**：需要在 `analysis_pipeline.py` 的 `except Exception` 之前重抛 `JobCanceledError` / `WorkerLeaseLostError` / `StageTimeoutError`。但三者当前定义在 `job_orchestration.py:1120/1125/1129`，而 `analysis_pipeline.py` 若 import `job_orchestration` 会形成循环依赖（编排层已 import pipeline）。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 在 pipeline 就地 `except (JobCanceledError, ...): raise`，配合函数内延迟 import | 能work，但延迟 import 是循环依赖的 smell，且三处都要重复 |
| B. **下沉到 `app/services/analysis_errors.py`** | ✅ 选定。两边都 import 它，无环|
| C. 定义 `control_signal` 异常基类，pipeline 只 `except ControlSignal: raise` | 更优雅，但需改动三个异常的继承关系，收益不抵风险 |
| D. 让 pipeline 不参与异常翻译，改由 `progress_callback` 返回状态而非抛异常 | 改动面最大，会波及所有阶段回调 |

**决策：B**。理由：最小改动面（只动定义位置，不动任何 `raise` 语句与捕获顺序），无循环依赖，且为将来可能的 `ControlSignal` 基类留了位置。风险是 `analysis_errors.py` 可能被误认为「异常定义收纳处」而后续往里塞业务异常——用模块 docstring 明确边界。

### D2：Worker 关停与单任务失败用不同事件，不引入 `_fatal_event`

**问题**：`_heartbeat_loop` 需要表达「这次运行失败了」，却用了 `_stop_event`（Worker 关停）。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 删掉 `:1253`/`:1259` 的 `_stop_event.set()`，只留 `failed_event.set()` | ✅ 选定。`failed_event` 已在 `:1321`/`:1446`/`:1457` 被检查，语义完整 |
| B. 新增 `_fatal_event`，区分「可恢复的租约丢失」与「不可恢复的故障」 | 更完备，但当前**没有任何场景需要退出 Worker**——引入无人触发的机制就是新的死代码 |
| C. 心跳线程失败时抛到主线程 | 跨线程异常无法可靠传播 |

**决策：A**。关键理由：`failed_event` 的三个检查点已构成完整的失败传播链，**`_stop_event` 在此处是纯粹的语义误用**。若将来真出现「必须退出 Worker」的场景（例如检测到控制面不可写），那时再引入 `_fatal_event` 并由守护循环负责重启——但不要为假想需求预留代码。

**风险**：删掉后若租约持续丢失，Worker 会反复claim 并反复失败。**缓解**：`claim` 本身有 `expected_status="queued"` 原子保护，失败的 job 已是终态不会被重复 claim；且 `recover_stale_running` 会周期性标记。

### D3：外接盘降级用独立根目录，而非标记位

**问题**：外接盘离线时，40+ 个 artifact 路径会落到本地 `outputs/<job_id>`，与正常本地 job 混写同一根，任务照常 `succeeded`，零痕迹。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 维持混写，在 job 上打 `degraded` 标记 | 标记易被忽略；且已写出的文件与后续读取的路径可能不一致 |
| B. **降级根改为 `outputs/_degraded/<job_id>`** | ✅ 选定。目录结构本身表达状态，运维 `ls` 即可发现，且 API 读取路径一致 |
| C. 外接盘离线时直接让任务失败 | 语义最诚实，但会中断现场录制后的分析，代价过高 |
| D. 阻塞等待外接盘挂载 | 不可行，任务不应挂起|

**决策：B**。理由：目录名是**不可被忽略的信号**（标记位可以被忘记检查，目录结构不会），且不改变任务的业务结局（仍然 `succeeded`，产物仍可读）。同时修正 `register_capture_job_from_take` 的 `except Exception: return None`（`:84`）——它把数据库连接失败、模型 package 错误一并吞成 `None`，必须区分「无 session_dir」（合法 `None`）与「解析失败」（告警 + 降级）。

### D4：SQLite PRAGMA 按路径分支，而非全局无条件开 WAL

**问题**：运行时实测 `app.sqlite3` 的 `journal_mode=delete`，而 `analysis_control.sqlite3` 是 WAL（`analysis_control_plane.py:31-33` 单独设的）。并发写下主库会 `database is locked`。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 全局无条件 `journal_mode=WAL` | ❌ **危险**。WAL 依赖共享内存 `mmap`，**USB / 外接卷上可能失效甚至损坏数据库**。而本项目的主库完全可能落在外接盘 |
| B. **按路径分支**：路径位于 `/Volumes/*` 或非本地盘时不设 WAL，仅设 `busy_timeout` | ✅ 选定 |
| C. 主库也迁移到 `analysis_control_plane` 那套显式 sqlite3 连接 | 改动过大，会与 SQLAlchemy session体系冲突 |
| D. 只加 `busy_timeout` 不动 journal_mode | 缓解但不根治：rollback journal 下并发写仍会锁，只是等得更久 |

**决策：B**。理由：这是唯一同时解决「并发锁」与「不损坏外接盘数据」的方案。实现上用 `event.listens_for(engine, "connect")` 统一施加，并对 `busy_timeout` 无条件设置（本地与外接盘都安全）。

**风险**：路径判断依赖挂载点检测，跨平台行为不一致。**缓解**：用「是否为本地文件系统」的探测而非硬编码 `/Volumes`（后者是 macOS 特有）。

### D5：鉴权默认拒绝启动，而非默认放行

**问题**：后端全站零鉴权（`Depends(` 中非 `get_db` 的用法零命中），叠加 `/docs`、`/openapi.json` 默认开启，任何可达方可拉取完整 API 契约并读取含绝对路径的错误消息与运行日志。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 保持零鉴权，靠网络隔离 | 竞赛期间内网可行，但 AutoDL / 云主机部署不成立 |
| B. **默认拒绝启动 + 显式豁免开关** | ✅ 选定。安全默认值 |
| C. 默认放行 + 启动时打印醒目警告 | 警告会被忽略，等于没做 |
| D. 只保护高危端点（DELETE / 上传） | 攻击面残留，且遗漏一个就前功尽弃 |

**决策：B**。理由：这是**唯一让「忘记配置」等于「安全」的默认值**。破坏性（未配 token 时服务起不来）是刻意的——它把安全从「记得做」变成「不做就起不来」。

**风险**：会打断现有本地开发与演示流程。**缓解**：`PICKLEBALL_AUTH_DISABLED=true` 显式豁免，且同步更新 `start-pickleball.command` 与 README。

### D6：静默异常用声明式装饰器，而非逐个加日志

**问题**：全仓 `except Exception` 694 处，其中 **40 处 handler body 只有 `pass`/`continue`**（AST 判定，2026-10-04 复核修正；初版统计 115 处因判定条件把嵌套双层 except 计入，已更正），分布分散、无单一热点（`services/multiview_overlay_repair.py` 与 `services/canonical_shot_rally_events.py` 各 3 处最多）。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 逐个加 `logger.warning` | 40 处里大部分确实无害，逐个加日志会淹没真正的问题 |
| B. **引入 `@swallow(why=...)` 装饰器强制声明理由** | ✅ 选定。声明本身成为可审计的契约 |
| C. 全局禁止裸 `except Exception`（lint 规则） | 会在 694 处里炸出 579 处噪声，短期内无法收敛 |
| D. 只修关键的 10 处 | 治标；且「关键」由谁判定？无标准 |

**决策：B**。理由：40 处里绝大多数是**合理的**（如清理临时文件、关闭可选句柄），问题不在于吞，而在于**吞的理由没有被记录，所以没人能判断某处吞得对不对**。装饰器把「为什么可以吞」变成必须回答的问题，未回答者在 lint 阶段暴露。这比加日志更省力也更严格。

**配套**：先用装饰器覆盖**新增与改动到的代码**，不追求单次全量替换。40 处存量分批收敛，避免大爆炸式diff。

### D7：前端轮询的收敛点放在「自恢复」而非「统一封装」

**问题**：5 处轮询各有各的问题（隐藏时不停、依赖含新对象、无 in-flight 守卫、失败即停摆）。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 写一个通用 `usePolling` hook 统一管理所有轮询 | 统一度最高，但要改 5 处以上调用点，且各处轮询参数（间隔、终止条件、terminal 处理）差异大，抽象容易变成「配置地狱」 |
| B. **定义不变量，各处就地修正** | ✅ 选定。每个轮询保持独立，但共享一组必须满足的行为约束 |
| C. 只修停摆的那一处 | 遗漏同样会造成停摆的 `useCaptureRuntime` / `analysisRuntimeStore` |

**决策：B**。理由：这些轮询的**业务语义差异过大**（任务列表看terminal、录制状态看 phase、运行时看 session、商店在模块级），强行统一的收益低于成本。改为在 spec 中定义「轮询必须满足的不变量」——失败自恢复、隐藏暂停、依赖用标量、terminal 停止、in-flight 守卫——让每处实现各自满足。

**关键洞察**：`AnalysisTasksPage` 的停摆是**遗漏而非设计**，证据是同项目 `AnalysisJobPage.tsx:225` 的 catch 里做了 `scheduleLoad(3000)`。因此**不需要发明新模式，只需要补齐一致性**。

### D8：运行时类型校验只覆盖核心读路径，不追求全量

**问题**：`zod`/`valibot`/`ajv` 一个都没安装，`analysisClient.ts:517-538` 的 `requestJson` 直接 `return response.json() as Promise<T>`，2067 行 client 全走这一个无校验出口。

**备选方案：**

| 方案 | 评价 |
|---|---|
| A. 引入 zod 并给全部接口加 schema | 工作量巨大，且 2067 行的 schema 维护成本会压垮迭代节奏 |
| B. **只给核心读路径加 schema + 复用既有类型守卫** | ✅ 选定。`isPipelineResult`(`services/pipelineReportAdapter.ts`) 已有类型守卫可作推广起点 |
| C. 不加校验，靠 TS 编译期 | 现状。Python 侧无类型约束，改动零成本，编译期完全无法防护 |
| D. 改用 `openapi` 自动生成客户端 | 需先解决 P0「`/openapi.json` 暴露面」，且生成物与手写类型并存会增加复杂度 |

**决策：B**。理由：核心读路径（任务列表、任务详情、结果、take）决定了前端能否正确渲染；这几条出问题会直接表现为「界面数据错乱」，而写路径失败用户会立刻知道。**按「出错可见性」分配校验强度**，而不是按接口数量平均分配。

**风险**：引入 zod 是新增依赖，需评估 bundle 影响。**缓解**：zod 仅用于读路径校验，不进渲染热路径；`dist` 已有 350 KiB gzip 落地页预算门禁可作监控。

## Risks / Trade-offs

**[本change 与活跃 change 修改同一批文件，合并冲突]** → `analysis_pipeline.py` / `job_orchestration.py` 同时被 `add-analysis-run-trace-and-error-reporting` 修改（本 change 的控制信号重抛正是在它引入的 `except` 旁边）。**缓解**：先归档 `add-analysis-run-trace-and-error-reporting`（36/36 只差 1 项）再动手；本 change 的 tasks 明确按「先归档、再改同文件」的顺序排列。

**[鉴权默认拒绝会打断现有演示流程]** → 用户无法直接 `npm run app:start`。**缓解**：`PICKLEBALL_AUTH_DISABLED=true` 显式豁免；同步改 `start-pickleball.command`、README 与 `docs/`；**在 tasks 中把「更新启动脚本与文档」列为与鉴权实现同一批的强制项，不允许只改代码不改文档**。

**[外接盘 WAL 的路径判断可能不准]** → 挂载点检测跨平台行为不一致。**缓解**：用文件系统探测而非硬编码路径；无法确定时**降级为不开WAL**（保守方向：只损失并发性能，不冒数据损坏风险）。

**[`@swallow` 装饰器 115 处存量无法单次收敛]** → diff 过大难以review。**缓解**：只强制新增/改动处；存量分批；装饰器本身带 `why` 默认值以便渐进迁移。

**[控制信号异常下沉会移动三个异常的定义位置]** → 可能有其他 import 路径依赖。**缓解**：移动而非复制，保留 `job_orchestration` 侧的 re-export 以免破坏既有 import。

**[`_stop_event` 删掉后，租约持续丢失时 Worker 会空转]** → 反复 claim 失败的 job。**缓解**：`claim` 的 `expected_status="queued"` 原子保护确保终态 job 不会被重复claim；`recover_stale_running` 周期性兜底。**验证方式**：新增测试断言「单 job 租约丢失后第二个 job 仍能被 claim」。

**[引入 zod 增加 bundle 体积]** → 可能突破 350 KiB gzip 落地页预算。**缓解**：zod 不进落地页闭包；CI 有预算门禁可发现。

**[并行修改导致测试基线漂移]** → 难以判断新失败是自己引入的还是既有的。**缓解**：沿用项目既有手法——判定失败是否自己引入时**不要 `git stash`**（工作区常含他人未提交改动），用 `git show HEAD:<path> | diff -q - <path>` 逐字节比对。

## Migration Plan

分四批，每批可独立验证、独立回滚：

| 批次 | 内容 | 验证 | 回滚 |
|---|---|---|---|
| **第一批**（当天可做） | D2 删 `_stop_event` 两行 · D1 控制信号重抛 · D3 标记位降级（先只加 warning） · 前端两处一行修复（轮询 catch 重试、恢复计时重置） · `PICKLEBALL_RUNTIME_DIR` export | 后端全量 pytest + 前端全量 vitest | 逐文件 revert，无数据迁移 |
| **第二批** | D1 异常下沉 · D3 降级根切到 `_degraded/` · D5 鉴权 + 同步改启动脚本与文档 · D4 SQLite PRAGMA 分支 | 同上 + **手工验证外接盘挂载/卸载两种情况** | 鉴权回滚需同时改回启动脚本 |
| **第三批** | D6 静默异常装饰器（新增代码强制） · D7 轮询不变量落地 · 路径构造收敛 `_safe_join` | 同上 + lint 无新增 | 装饰器可保留（无副作用） |
| **第四批** | D8 核心读路径 schema 校验 · 暗色迁移 · 门禁修复（CI 接入 ruff、修正 OpenSpec 校验目标） | 同上 + **CI 在真实 PR 上验证门禁真的会红** | 门禁改动需回滚 workflow 文件 |

**回滚策略**：本 change 不涉及数据 schema 变更、不涉及不可逆迁移，回滚 = `git revert`。唯一需要注意的是**第二批的鉴权与启动脚本必须同批回滚**，否则会出现「代码要求 token 但脚本不提供」的不可启动状态。

**部署注意**：鉴权与「关闭 `/docs`」**必须在远端部署前生效**。竞赛本地演示可通过 `PICKLEBALL_AUTH_DISABLED=true` 豁免。

## Open Questions（2026-10-05 已全部决策）

以下 5 项已于 2026-10-05 逐条核实代码事实并决策，决策结果已回写至对应 Requirement 与 `tasks.md`；本节保留决策依据以备追溯。

### Q1 · `max_gpu_jobs` / `enable_gpu_jobs` 是补齐还是删除？→ **删除**

核实依据：`scripts/remote/` 下 `cuda` / `gpu` **零命中**（远端无 GPU 部署计划），且本机设备只认 CUDA 不认 MPS、推理 100% 走 CPU。补齐需要判断「哪些阶段用 GPU」，而该判断在当前与可预见的环境里永远走不到。

**决策：删除** `ResourceLimiter.gpu` 与这两个配置项。理由：留着配了不生效的选项比没有更糟——它会让使用者以为并发受控。

### Q2 · `_degraded/` 产物的生命周期？→ **本轮只做后端标记，不做前端 UI**

核实依据：全仓 `degraded` **零命中**，前端无任何降级概念。补一整套 UI 提示会明显放大本 change 范围。

**决策：后端在 job 上打降级标记 + 日志告警；前端暂不显示。** 降级本身是异常情况，运维看日志足够；等它成为常态再补 UI。

### Q3 · `runTrace.target` / `scanned_files` 的绝对路径是否本轮改？→ **改，与鉴权同批**

核实依据：`runTrace` 是 `schemas/analysis.py:338` 的 `AnalysisJobSummary` 字段，而该模型是 `GET /jobs` 的响应模型 —— **每次拉任务列表都会把外接盘挂载点（`/Volumes/Elements/项目/匹克球/...`）推给前端**。

**决策：改。** 关键理由：关闭 `/docs` 挡不住这条路径，它与鉴权是**两条独立的泄露链**——鉴权落地后同网段仍可读。改法是存逻辑引用（`analysis/<job_id>/run_trace.jsonl`），复用 `storage_service` 已有但未使用的 `logical_artifact_reference` 能力。

### Q4 · `_run_tracking` 的 236 行保护用 try/finally 还是细粒度清理？→ **try/finally**

**决策：try/finally。** 细粒度清理需覆盖 6 个可抛点，漏一个即前功尽弃，且后续新增代码还会再漏；缩进变更由 `git diff -w` 可忽略，diff 变大不是真问题。

### Q5 · 多摄身份链审核何时补？→ **并入 `restore-confirmed-four-player-joint-analysis` 收尾，不开第三个 change**

**决策：并入现有 change。** 该层属算法正确性（IoU 门限、坐标翻转、P1/P2 分侧假设在相机视角翻转下是否成立、`_reconsider_roster_end` 多数票是否反复翻转），与本 change 的基础设施性质不同；且该 change 已 4/4 产物完成、剩 23/28 任务在跑，审核结论应并入其收尾而非并行开新 change。


## 2026-10-06 收尾决策：仅本机演示

用户明确当前只在这台电脑演示，默认仅允许本机访问。本轮保留后端 Bearer 认证，把浏览器入口收敛为只监听 loopback 的同源代理；凭据只存在 API/Worker/Vite 服务端环境中，不进入 `VITE_*`、URL 或前端产物。代理校验连接地址、Host、Origin 与 Fetch Metadata，拒绝跨来源请求。开发和构建后的本地 preview 使用相同代理。远端/局域网会话认证与部署另行设计，不将本地代理宣称为远端认证方案。

运行中断验收走实际 SQLite 任务存储、dispatcher 和 Pipeline，在 tracking 回调内撤销租约，断言 `interrupted`、`worker_lease` 留痕以及同一 Worker 继续执行下一任务。已有首次失败证据仍保留。

降级目录增加持久标记，重启和外接盘重新可用时继续读取原降级产物，避免内存索引清空后无声切回空的外接目录。目录标记提供运维证据；它不能代替面向用户的提示。实际外接盘只执行独立验收任务；卸载/重挂使用可丢弃磁盘镜像，避免影响用户原始素材卷。


## 2026-10-08 验收补正

- 比赛库主背景改用主题变量；主题状态更新器保持纯函数，DOM/存储/同页事件在 React 提交后同步；补 StrictMode、刷新及跨标签同步回归。
- 封面 404 回退到真实视频首帧，视频本身不可用时显示占位图，避免破图；封面 URL 更新后允许重新加载。
- 显式 `PICKLEBALL_LOCAL_DOCS=true` 仅允许 loopback peer 与本机 Host 查阅文档；本机启动脚本打开，其他启动及远端部署默认关闭。避免之前无条件关闭违背本地调试场景。
- `@swallow` 不吞取消、超时和租约丢失；新增 AST 门禁按 Git 增量检查宽泛静默 handler 和理由声明，存量不整体阻断。
- Ruff、增量异常声明和 OpenSpec 门禁独立于完整质量任务。真实故障 PR #2 三项均明确 exit 1；PR 已关闭、未合并，完整远端质量任务的依赖安装失败单独记录。
- 身份链算法审核已移交四人身份 change 的 6.5，可靠性 change 不以算法审核作为自身归档条件。
