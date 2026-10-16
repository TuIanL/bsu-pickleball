## Context

当前分析任务的可观测性集中在**终态之后**：`AnalysisJobSummary` 有 `errorCode` / `publicErrorMessage` / `internalErrorMessage`，`AnalysisStage` 有 `errorCode` / `internalMessage` / `retryCount`。但**运行中**的失败不留任何证据：

- `job_orchestration.py:1251-1279` 的阶段内重试分支 `except Exception:` 直接重跑 executor，既无 `logger.*`，也不把异常写入 stage 的 `internalMessage`，只写死 `detail="阶段执行失败，正在按策略重试"`。
- 重试会**整条 executor 重跑**（双摄等价于 joint tracking 全量重解码），但没有任何记录表明「这是一次重试、原因是什么、还剩几次」。
- 用户取消后，`mark_canceled` 用 `ANALYSIS_JOB_CANCELED` 覆盖 job 级 `errorCode`，已发生的真实失败码消失。

实测证据（2026-10-04，`job-dc737801f5`，双摄 `joint_tracking_v2`，120s 片段）：

| 字段 | 落盘值 |
| --- | --- |
| `stage` / `progress` | `multiview-joint` / `77` |
| `multiview-ball-analysis` 阶段 | `status=pending`、`progress=0`、`retryCount=1`、`errorCode=null`、`internalMessage=null`、`detail="阶段执行失败，正在按策略重试"` |
| job 级 `internalErrorMessage` / `interruptionCode` | `null` / `null` |
| 最终终态 | `canceled`，`errorCode=ANALYSIS_JOB_CANCELED` |
| `.runtime/logs/analysis-worker.log` | 仅 `started` / `stopping` 两行，零 WARNING/ERROR |

也就是说：唯一存在的失败证据就是那句固定文案，失败原因在发生的那一刻被删除。这使「为什么失败」在本机数据上**不可回答**。

约束：

- 双摄 job 的产物根是外接盘（`_job_artifact_root` 经 `register_capture_job` 解析为 `<session_dir>/analysis/<job_id>`），外接盘可能未挂载。
- 控制面 `analysis_control.sqlite3` 的 `payload_json` 是跨进程事实源，新增字段必须对历史 job 向后兼容。
- 项目既有约定：可测试的纯逻辑模块不 import `cv2` / `ultralytics`（参考 `player_bootstrap_preflight`）。

## Goals / Non-Goals

**Goals:**

- 让每一次尝试、每一个阶段的**起止与失败原因**在事后可完整还原，且证据落在 job 目录（双摄即外接盘）。
- 让「重试」成为一等可观测事实：为什么重试、第几次、还剩几次。
- 让失败具备**正交的两维**：`errorCode`（哪一步）与 `failureClass`（为什么）。
- 终态不得抹掉运行中的失败证据。

**Non-Goals:**

- 不改 `canonicalStatus` 六态语义、阶段图、`merge_stage_progress` 的既有状态机行为。
- 不改 `job_max_retries` / 心跳超时 / 阶段超时默认值。
- 不修「双摄创建绕过去重」「租约抖动误判失联」「编排反复 reconcile」——本次只提供定位这些根因所需的证据。
- 不做远程/集中日志采集，只做本机 runtime 的只读读取。

## Decisions

### D1. 轨迹载体：job 目录下 append-only `run_trace.jsonl`

路径由既有 `_job_artifact_root(job_id) / "run_trace.jsonl"` 决定，从而**自动**落在双摄的外接盘 session 目录，无需新增路径逻辑。

- 备选：独立 SQLite trace store —— 否决。控制面只存索引字段与调度 payload，把逐事件轨迹塞进去会造成跨进程写竞争与 schema 迁移成本，且违背「与 job 产物同址」的诉求。
- 备选：单个 `run_trace.json` 覆盖写 —— 否决。进程被杀时已写入内容会整体丢失；append-only JSONL 保证「崩溃前已写的行仍然可读」，这恰是本能力最需要的性质。

### D2. 外接盘不可用时**不静默 fallback**

写入失败时向控制面 payload 追加一条 `trace_sink_unavailable` 记录（含目标路径与失败原因），前端显示「轨迹不可用（原因）」；**不**改写到本地 `outputs/`。

- 理由：用户明确要求「都要落盘到外接硬盘」。静默 fallback 会让「有轨迹」的判断失真，与本次目标（可精确定位）直接冲突。
- 代价：外接盘不在时，本次运行无轨迹。可接受——因为「无轨迹」这件事本身是显式可见的，而不是被伪装成「有轨迹」。

### D3. 事件模型：统一枚举 + 最小必填字段 + `seq`

```jsonc
{
  "schema_version": "analysis-run-trace.v1",
  "seq": 42,                       // 单调递增，跨进程合并后可排序
  "ts": "2026-10-04T10:28:04.640Z",
  "job_id": "job-dc737801f5",
  "attempt": 1,                    // 对应 job.attempt
  "worker_id": "analysis-worker-80953",
  "worker_run_id": "analysis-worker-80953-b962...",
  "stage": "multiview-ball-analysis",
  "event": "retry",                // start | end | retry | fail | lease_lost | canceled | trace_sink_unavailable
  "outcome": "failed",             // 可选，事件语义补充
  "error_code": null,              // 稳定码（哪一步）
  "failure_class": "resource_timeout", // 归因类别（为什么）
  "exception_type": "cv2.error",
  "exception_message": "OpenCV(4.11.0) ...",  // 截断 2KB
  "traceback_digest": "a1b2c3d4e5f60718",     // sha256 前 16 位，用于聚合同一异常
  "traceback_frames": ["frame_timing_provider.py:118", "..."], // 末 5 帧，无日志时仍可定位
  "retry_index": 1,
  "retry_limit": 1,
  "will_retry": false,
  "progress_before": 0,
  "progress_after": 0
}
```

- 用 `traceback_digest` + `traceback_frames` 而非完整堆栈：轨迹要小且长期留存；完整堆栈已有 `internalErrorMessage` 通道承载。
- 备选：只写 `exception_message` —— 否决。同一句消息可能来自不同位置，无法聚合也无法定位。

### D4. 重试必须先写事件、再重跑

重试分支调整为：捕获异常 → 构造 `retry` 事件（含全部异常字段与 `retry_index` / `retry_limit` / `will_retry`）→ 写 trace → 把异常摘要写入该阶段 `internalMessage` → 再重跑 executor。

- 只写 trace 不够：UI 在无 trace 或 trace 不可用时仍需一行原因，因此阶段 `internalMessage` 必须带摘要。
- 备选：仅 `logger.warning` —— 否决。日志不可跨进程聚合、无 job 维度结构、且用户当前就没有翻日志的习惯。

### D5. `failureClass` 与 `errorCode` 正交，分类器为纯函数

新增归因枚举：`input_media` / `calibration` / `model_environment` / `resource_timeout` / `worker_lease` / `orchestration` / `internal_defect`。

- `errorCode` 回答「哪一步失败」（既有 `ANALYSIS_ERROR_CODES` 体系继续承担）；`failureClass` 回答「为什么失败」。两者都保留，不做互相替代。
- 分类器实现为纯函数模块（输入异常类型/消息/错误码，输出类别），不 import `cv2` / `ultralytics`，可独立单测；未知一律归 `internal_defect`，并**始终保留**原始 `exception_type` / `exception_message`，允许事后重分类。

### D6. 终态不覆盖运行中证据

新增独立字段 `failureEvidence`（首次失败的码/类别/时间/attempt）与 `retryHistory`（每次重试的 stage + 类别 + 时间）。

- `mark_canceled` / `mark_interrupted` 只写自己的终态字段，**不得**清空 `failureEvidence`。
- 前端同时展示两层：终态（已取消）+ 历史（曾因 X 失败并重试 N 次）。
- 兼容：历史 job 无该字段时保持旧行为。

### D7. 不改阶段状态机，只记录回退

现状 `multiview-ball-analysis` 在重试时落盘为 `pending` / `progress=0`，造成「任务莫名从头开始」的主观体验。本次**不动** `merge_stage_progress` 的既有语义（它有既有规格与测试约束），改为在 `retry` 事件中记录 `progress_before` / `progress_after`，使「回退」这件事**可解释**。

- 备选：直接修阶段回退 —— 否决。属于状态机行为变更，应有独立 change 与独立验收，避免本 change 变成大杂烩。

### D8. `API` 侧新增两个只读端点

- `GET /api/analysis/jobs/{job_id}/run-trace` → 解析后的轨迹数组 + `availability`（`available` / `unavailable`）+ `reason`。
- `GET /api/analysis/jobs/{job_id}/logs?tail=N` → 按时间窗口（`claimedAt` ~ `finishedAt`）与 `job_id` / `workerRunId` 行内匹配过滤 `backend.log` / `analysis-worker.log`，带行数上限。

**不**把轨迹内联进 `AnalysisJobSummary`：任务列表与进度页按 1.6s / 5s 轮询，内联会让轮询体积随重试次数膨胀。

### D9. 日志匹配失败要显式声明

`.runtime/logs/*.log` 的行不带 `job_id` 前缀，只能靠 `workerRunId` / `job_id` 子串 + 时间窗口兜底。匹配不到时返回 `availability=partial` 与原因，而不是返回空数组让用户以为「没有日志」。

## Risks / Trade-offs

- [轨迹写入放大 I/O，且 job 目录可能在外接盘] → 单行 append + flush；事件数设上限（心跳类高频事件不入轨迹，只入 start/end/retry/fail/lease_lost）；写入失败降级为 `trace_sink_unavailable` 事件，绝不阻塞主流程。
- [外接盘拔掉导致轨迹丢失] → 显式 `unavailable` 原因 + 前端可见；接受「无轨迹」但拒绝「假装有轨迹」。
- [日志 API 暴露敏感路径] → 只读；仅本机 runtime 目录；返回行数硬上限；可配置开关。
- [历史 job 无轨迹，前端需降级] → `availability=unavailable` + `reason=legacy_job_without_trace`；不报错。
- [归因分类器误判] → 默认 `internal_defect`；原始 `exception_type` / `exception_message` 永远保留，允许事后重分类。
- [轨迹与 `internalErrorMessage` 双写不一致] → 规定 trace 为权威、`internalMessage` 为摘要视图；两者由同一处代码路径产出，禁止各写一套。

## Migration Plan

1. 新增字段全部为可选，`AnalysisControlPlane._payload_from_row` 与 `AnalysisJobSummary` 读取路径对历史 job 保持兼容。
2. 只对**新创建**的 job 写轨迹，历史 job 不回溯补写。
3. 回滚：撤掉轨迹写入不影响控制面（字段是 additive），前端按 `availability` 降级即可；`run_trace.jsonl` 随 job 删除一并清理。
4. 部署后必须用**真实双摄素材**触发一次可复现失败（例如故意使用不匹配的标定 / 损坏片段）跑通验收，而不是只跑单元测试。

## Open Questions

- Q1 轨迹保留策略：随 job 删除一并删（默认），还是独立 TTL？——默认随 job 删除。
- Q2 `failureClass` 是否需要聚合到 `late_fusion_v1` 的内部 child？——默认 child 各自落盘轨迹，public Parent 只做聚合视图。
- Q3 `logs` 端点是否默认开启？——建议本地 runtime 默认开启，并保留关闭开关。
- Q4 是否需要一个显式的「疑似重复提交」信号（同一 `inputSignature` 存在多个非复用 job 时在任务列表标注）？——与本次「双摄绕过去重」根因相关，可作为独立 change 或本 change 的小增量，待定。
