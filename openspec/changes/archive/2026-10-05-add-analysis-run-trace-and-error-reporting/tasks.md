## 1. 轨迹基础设施（后端）

- [x] 1.1 新增 `backend/app/services/analysis_run_trace.py`：定义 `analysis-run-trace.v1` 事件模型与 `event` 枚举（`start` / `end` / `retry` / `fail` / `lease_lost` / `canceled` / `trace_sink_unavailable`），纯逻辑模块，不 import `cv2` / `ultralytics`
- [x] 1.2 在该模块实现 JSONL sink：按行 append + flush、`seq` 进程内单调递增、单行独立完整 JSON；写入异常时降级为一条 `trace_sink_unavailable`（含目标路径与原因）且不抛给主流程
- [x] 1.3 在 `backend/app/services/storage_service.py` 新增 `run_trace_jsonl_path(job_id)`，复用 `_job_artifact_root(job_id)`，使正式采集任务自动落 `<session_dir>/analysis/<job_id>/run_trace.jsonl`
- [x] 1.4 单测 `backend/tests/test_analysis_run_trace.py`：覆盖（a）追加顺序与 `seq` 单调；（b）截断到任意字节前缀仍可逐行解析；（c）目标目录不可写时产出 `trace_sink_unavailable` 且 sink 调用不抛异常
- [x] 1.5 验证：`cd backend && mkdir -p .runtime && .venv/bin/python -m pytest tests/test_analysis_run_trace.py -q --basetemp=.runtime/trace-unit`

## 2. 失败归因（errorCode 与 failureClass 正交）

- [x] 2.1 新增 `failure_class` 枚举（`input_media` / `calibration` / `model_environment` / `resource_timeout` / `worker_lease` / `orchestration` / `internal_defect`）与纯函数 `classify_failure(exception_type, message, error_code) -> str`
- [x] 2.2 在 `backend/app/schemas/analysis.py` 补充归因相关的型别与稳定错误码扩展，保持既有 `ANALYSIS_ERROR_CODES` 语义不变（`error_code` 回答「哪一步」，`failure_class` 回答「为什么」）
- [x] 2.3 单测：7 个类别各至少一例；未知输入回退 `internal_defect` 且原始 `exception_type` / `exception_message` 不被丢弃
- [x] 2.4 单测：同一异常重复出现时 `traceback_digest` 稳定一致（可聚合）

## 3. 重试留痕与失败证据保真（核心）

- [x] 3.1 改造 `backend/app/services/job_orchestration.py` 阶段内重试分支（约 1251-1279）：捕获异常后**先写 `retry` 事件再重跑**，事件携带 `exception_type` / `exception_message`（截断 2KB）/ `traceback_digest` / `traceback_frames`（末 5 帧）
- [x] 3.2 `retry` 事件补齐 `retry_index` / `retry_limit` / `will_retry` / `progress_before` / `progress_after`，使阶段进度回退可归因于重试
- [x] 3.3 重试时把异常摘要写入该阶段 `internalMessage`，使不读轨迹的消费者也有一行原因（禁止只写固定文案）
- [x] 3.4 `AnalysisJobSummary` 新增 `failureEvidence`（首次失败码/归因/阶段/时间/attempt）、`retryHistory`（每次重试的阶段/归因/时间）与 `runTrace` 可用性摘要；`AnalysisStage` 新增 `failureClass`。全部为可选字段，历史 job 缺字段时保持旧行为（规格要求证据挂在任务摘要上，阶段只带归因类别）
- [x] 3.5 `mark_canceled` 与 `mark_interrupted` 只写各自终态字段，**不得**清空或覆盖 `failureEvidence`
- [x] 3.6 在阶段边界的唯一来源（Worker 的 `progress_callback`）补 `start` / `end` 埋点，使轨迹能还原每次 attempt 的阶段起止（不逐个 executor 埋点，避免出现多处真相）
- [x] 3.7 单测：复现「可重试阶段失败 → `retryCount=1` 且阶段 `internalMessage` 含真实异常摘要」（当前该字段为 null）
- [x] 3.8 单测：复现「失败重试后被取消 → 终态 `canceled` 且 `failureEvidence` 仍保留真实失败码与归因」
- [x] 3.9 单测：不可重试阶段的失败只写 `fail` 事件、不写 `retry` 事件

## 4. 读取接口（只读 API）

- [x] 4.1 在 `backend/app/api/routes_analysis.py` 新增 `GET /api/analysis/jobs/{job_id}/run-trace`：返回按 `seq` 有序的事件序列 + `availability`（`available` / `unavailable`）+ `reason`
- [x] 4.2 新增 `GET /api/analysis/jobs/{job_id}/logs?tail=N`：按 `claimedAt`~`finishedAt` 时间窗口与 `job_id` / `workerRunId` 匹配过滤 `backend.log` 与 `analysis-worker.log`，强制行数上限；匹配不到返回 `availability=partial` + 原因，不得返回空结果冒充成功
- [x] 4.3 确认任务列表与任务摘要响应**不内联**完整轨迹（避免 5s 轮询体积膨胀）
- [x] 4.4 API 测试：有轨迹返回 `available`；历史 job 返回 `unavailable` + `legacy_job_without_trace`；日志端点行数受限且带部分可用性

## 5. 前端呈现

- [x] 5.1 `src/types/report.ts` 补齐 `failureEvidence` / `retryHistory` / 归因类别 / 轨迹响应型别
- [x] 5.2 `src/services/analysisClient.ts` 新增 `getAnalysisRunTrace(jobId)` 与 `getAnalysisJobLogs(jobId, tail)`，失败按诊断降级（复用 `analysisDiagnostics`）
- [x] 5.3 `src/pages/AnalysisJobPage.tsx` 新增「分析进程」时间线：已尝试次数、每次重试原因、是否还会继续重试
- [x] 5.4 `AnalysisJobPage` 新增「技术详情」折叠区展示 `internalErrorMessage`，并提供轨迹的复制 / 下载
- [x] 5.5 `AnalysisJobPage` 失败/失联/取消三态均展示 `failureEvidence` 与 `retryHistory`，取消态同时呈现终态与历史失败
- [x] 5.6 轨迹不可用时展示不可用原因，任务其余信息保持可用、不报错
- [x] 5.7 `src/pages/AnalysisTasksPage.tsx` 列表行体现失败归因类别与重试次数
- [x] 5.8 前端测试（新增用例覆盖 5.3–5.7），运行：`npm test -- --run --maxWorkers=2`

## 6. 真实验收（禁止只靠单测放行）

- [x] 6.1 **遗留验收补做完成（2026-10-06）**：实际 Worker 读取真实双摄两路首帧后注入可复现解码失败，两轮尝试均释放句柄；`job-587ff8edc3/run_trace.jsonl` 写在 Elements 真实 session 的 `analysis/` 中，含完整 retry 异常与策略字段。详见 `../2026-10-08-harden-analysis-runtime-reliability/acceptance-20261008.md`。验收覆盖实际媒体读取、故障重试和落盘，不代表 joint 算法质量验收。
- [x] 6.2 在**外接盘未挂载**状态下重跑，确认产出 `trace_sink_unavailable` 事件、任务不被中断、前端显示不可用原因
- [x] 6.3 用历史任务 `job-dc737801f5` 验证降级路径：轨迹 `unavailable`、其余字段正常、页面不报错
- [x] 6.4 后端全量（排除两个硬编码外接盘路径的既有测试文件）：`cd backend && mkdir -p .runtime && pytest tests -q --basetemp=.runtime/full --ignore=tests/test_hybrid_ball_regression_fixture.py --ignore=tests/test_sync_recording.py`，确认无**新增**失败（既有 `test_analysis_worker_liveness.py` 失败只报告不修）
- [x] 6.5 前端全量：`npm test -- --run --maxWorkers=2`，确认无新增失败
- [x] 6.6 用 `git show HEAD:<path> | diff -q - <path>` 核对本次未改动的既有失败文件，确认失败不是本 change 引入
