> 语言约定：本文档用简体中文撰写；`API` / `REST` / `JSON` 等技术术语保留英文。

## Why

2026-10-04 的双摄任务 `job-dc737801f5`（`analysisKind=multiview`、`executionMode=joint_tracking_v2`、120s 片段）提供了一份完整实测证据：`multiview-ball-analysis` 阶段抛出异常后，阶段内重试把 `retryCount` 记为 1、把阶段 detail 覆写成固定文案「阶段执行失败，正在按策略重试」，但**异常对象、异常类型、堆栈、错误码全部被丢弃**——落盘结果是 `errorCode=null`、`internalMessage=null`，同时 `.runtime/logs/analysis-worker.log` 里零条 WARNING/ERROR。用户唯一能观察到的现象是任务「又从头跑了一遍」（重试会整条 executor 重跑，双摄等价于 joint tracking 全量重解码，代价极高），却拿不到任何失败原因；最终用户手动取消，`errorCode` 又被 `ANALYSIS_JOB_CANCELED` 覆盖，真实失败码彻底消失。

结论：当前系统在**失败发生的那一刻主动删除证据**，导致「为什么失败」在本机数据上不可回答，只能靠反复重跑试错。这个缺口直接阻碍双摄链路的任何根因定位。

## What Changes

- 新增**每次运行的结构化事件轨迹（run trace）**：append-only 记录 `attempt / stage / event(start|end|retry|fail|lease_lost|canceled) / 时间戳 / 稳定错误码 / 异常类型 / 异常摘要 / traceback digest / worker 身份`，落盘为 job 目录下的 artifact。
- **重试必须留痕**：阶段内重试不再静默——必须记录本次 attempt 的真实失败原因与重试决策（是否可重试、已用次数、上限）。
- **稳定失败归因码**：把异常归入 `input_media / calibration / model_environment / resource_timeout / worker_lease / orchestration / internal_defect` 等类别，使用户第一眼就能看到失败属于哪一类，而非只有 `ANALYSIS_INTERNAL_ERROR`。
- **终态失败证据保真**：取消/超时/失联不得覆盖已经发生的失败证据；job 详情必须能同时表达「曾因 X 失败并重试 N 次」与「最终被取消」。
- **阶段回退可解释**：重试导致阶段状态从 active 回退为 pending、进度回退时，必须能从 trace 与阶段字段解释该回退来自重试，而不是「任务莫名从头开始」。
- **artifact 落盘位置统一交回 job 目录**：双摄 job 目录位于外接盘（`/Volumes/Elements/项目/匹克球/视频录制/captures/.../analysis/`），trace 与其余产物同址存放，外接盘不可用时给出明确不可用原因而非静默失败。
- **前端呈现**：任务详情页新增「分析进程」时间线（第 N 次尝试、重试原因、是否还会再重试），并把 `internalErrorMessage` 收进「技术详情」折叠区；提供 trace 的复制/下载。
- **日志可定位**：新增按 `job_id` 读取后端/Worker 日志的只读入口，免去手动翻 `.runtime/logs/`。

非目标（本次明确不做）：

- 不改变 `canonicalStatus` 六态生命周期与双摄阶段图。
- 不修改 `job_max_retries`、心跳超时、阶段超时等策略默认值（本次只做「让策略可见」，不做「改策略」）。
- 不修复「双摄创建绕过去重」「心跳/租约抖动误判失联」「编排反复 reconcile」这三个根因；本次只提供定位它们所需的证据。

## Capabilities

### New Capabilities

- `analysis-run-trace`: 每次分析运行的**事件轨迹与失败归因**能力。覆盖：轨迹事件的字段与语义、重试留痕、稳定失败码与归因分类、终态失败证据保真规则、artifact 落盘位置与外接盘不可用时的降级契约、以及 `API` / 前端消费该轨迹的契约。

### Modified Capabilities

<!-- 刻意留空：本次仅新增可观测性能力，未改变任何既有 spec 的 requirement。
     `analysis-job-orchestration` 的六态生命周期、阶段图与「Job fails 需记录分离的内部诊断信息」
     等既有要求均被本次新增能力补强而非改写；详见 design.md 的决策记录。 -->

- （无）

## Impact

**后端**

| 文件 | 影响 |
| --- | --- |
| `backend/app/services/job_orchestration.py` | 阶段内重试分支（当前 1251-1279）改为写入 trace 并保留异常证据；`mark_failed` / `mark_canceled` 不再覆盖已有失败证据；新增 trace 写入与运行目录解析 |
| `backend/app/services/analysis_control_plane.py` | payload 新增 trace 摘要字段（如 `failureClass`、`retryHistory`）；需兼容无该字段的历史 job |
| `backend/app/schemas/analysis.py` | 扩充 `ANALYSIS_ERROR_CODES` 与阶段/任务级失败归因字段 |
| `backend/app/services/storage_service.py` | 新增 job 运行目录与 trace artifact 路径；区分本地 `outputs/` 与外接盘 session 目录 |
| `backend/app/api/routes_analysis.py` | 新增 trace 读取与按 `job_id` 过滤日志的只读端点 |
| `backend/app/services/analysis_executor_dispatch.py` 及各 executor | 阶段边界埋点，供 trace 记录 attempt 内阶段起止 |

**前端**

- `src/types/report.ts`：补齐 trace 与失败归因字段类型。
- `src/pages/AnalysisJobPage.tsx`：新增「分析进程」时间线、「技术详情」折叠 `internalErrorMessage`。
- `src/pages/AnalysisTasksPage.tsx`：列表行体现失败归类与重试次数。
- `src/services/analysisClient.ts`：trace 与日志读取客户端。

**数据与兼容**

- `analysis_control.sqlite3`（`analysis_jobs.payload_json`）新增字段；历史 job 缺失时保持旧行为。
- job 目录新增 trace artifact；双摄落在**外接盘**。外接盘未挂载时，trace 写入必须显式记录「落盘位置不可用」原因，不得静默丢弃。
- 历史任务（含 `job-dc737801f5`）无 trace 时，前端按「轨迹不可用」降级展示，不得报错。
