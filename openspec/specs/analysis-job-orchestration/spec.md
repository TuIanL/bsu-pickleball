# analysis-job-orchestration Specification

## Purpose
TBD - created by archiving change add-analysis-job-orchestration-foundation. Update Purpose after archive.
## Requirements
### Requirement: Durable analysis job lifecycle

`canonicalStatus` 五态生命周期（`queued / running / succeeded / failed / canceled`）保持为唯一业务状态维度；系统 MUST 使用独立维度 `orchestrationStatus`（`none / waiting_sources / fallback_ready / fusion_ready / fusing / composing / completed`）表达多视角 Parent 的编排，MUST NOT 将 `waiting_sources` 等编排状态塞入 `canonicalStatus`。创建任务时 MUST 持久化分析窗口（`clipStartMs` / `clipEndMs`）与 `analysisKind`，使子任务执行时能拿到窗口。

#### Scenario: multiview Parent 等待 child

- **WHEN** 一个 `analysisKind=multiview` 的 Parent 已创建且两个 child 未全部完成
- **THEN** 该 Parent SHALL 保持 `canonicalStatus=queued`、`orchestrationStatus=waiting_sources`
- **AND** 该状态 SHALL 在 `queued` 兼容语义下可被取消

#### Scenario: 取消等待中的 Parent

- **WHEN** 用户取消 `waiting_sources` 的 Parent
- **THEN** 该 Parent SHALL 置 `canonicalStatus=canceled`
- **AND** 编排层 SHALL 级联取消其 owned 非终态 children

#### Scenario: 分析窗口落盘

- **WHEN** 创建分析任务携带 `clipStartMs/clipEndMs`
- **THEN** 任务摘要 SHALL 持久化该窗口
- **AND** 子任务执行时 SHALL 按其窗口限定的帧范围分析，而非整场视频

### Requirement: Stage telemetry

阶段遥测保持既有 `AnalysisStage` 结构。`MultiViewAnalysisExecutor` 返回的 `AnalysisPipelineResult.stages` MUST 表达聚合阶段（素材与同步检查 / A 机位视觉分析 / B 机位视觉分析 / 多视角融合 / 指标重算 / 报告），子级细粒度进度 MUST 经 Parent `viewRuns` 暴露（运行中惰性刷新为 child 实时进度），MUST NOT 铺 24 行单摄阶段。

#### Scenario: Parent 聚合阶段

- **WHEN** 前端轮询 multiview Parent 摘要
- **THEN** Parent `stages` SHALL 展示聚合阶段
- **AND** `viewRuns`（`cam_1 / cam_2` 各自的 `status / stage / progress`）SHALL 提供两路子进度，运行中也反映 child 实时进度

### Requirement: API and worker execution separation
The system SHALL separate job creation/status APIs from the execution of heavy analysis pipeline work.

#### Scenario: API creates a job
- **WHEN** the client creates a real analysis job
- **THEN** the API validates the request, persists the queued job, schedules or notifies local execution, and returns without running the full analysis pipeline inside the request handler

#### Scenario: Worker executes a job
- **WHEN** the local worker finds an eligible queued job
- **THEN** it executes the analysis pipeline, writes progress through the job orchestration service, and persists terminal job/result/report state

#### Scenario: API reads status during execution
- **WHEN** the client requests status for a queued or running job
- **THEN** the API returns the latest persisted job and stage telemetry without depending on in-memory-only state

### Requirement: Local queue and priority execution
The system SHALL provide a local queue that selects queued jobs by priority and creation order.

#### Scenario: Jobs have the same priority
- **WHEN** multiple jobs are queued with the same priority
- **THEN** the worker claims the oldest eligible job first

#### Scenario: Jobs have different priorities
- **WHEN** multiple queued jobs are eligible and one has higher priority
- **THEN** the worker claims the higher-priority job before lower-priority jobs unless a configured fairness rule prevents starvation

#### Scenario: Queue survives process restart
- **WHEN** the backend restarts after jobs were queued but not completed
- **THEN** the system can list those durable jobs and either leave them queued or mark interrupted running jobs with a recoverable failed/interrupted state

### Requirement: Resource-limited execution
The system SHALL limit local concurrent analysis work according to configured CPU and GPU resource settings.

#### Scenario: CPU limit is reached
- **WHEN** the configured maximum number of CPU jobs is already running
- **THEN** additional CPU-bound jobs remain queued until capacity is available

#### Scenario: GPU limit is reached
- **WHEN** the configured maximum number of GPU jobs is already running
- **THEN** additional GPU-bound jobs remain queued until GPU capacity is available

#### Scenario: Default local configuration is used
- **WHEN** no explicit resource configuration is provided
- **THEN** the system runs heavy analysis conservatively so one long or model-backed job cannot start unbounded concurrent analysis jobs

### Requirement: Cancellation
The system SHALL support cooperative cancellation for queued and running analysis jobs.

#### Scenario: Queued job is canceled
- **WHEN** a client requests cancellation for a queued job
- **THEN** the system marks the job as canceled without running the analysis pipeline

#### Scenario: Running job is canceled
- **WHEN** a client requests cancellation for a running job
- **THEN** the system records a cancellation request and the worker stops at the next safe cancellation checkpoint

#### Scenario: Terminal job cancellation is rejected
- **WHEN** a client requests cancellation for a succeeded, failed, or already canceled job
- **THEN** the system returns a stable non-destructive response and does not alter the terminal result

### Requirement: Timeout and retry policy
The system SHALL support bounded timeout and retry behavior for explicitly configured stages.

#### Scenario: Stage exceeds timeout
- **WHEN** a stage exceeds its configured timeout
- **THEN** the system records a timeout error code and either retries the stage if it is retryable or fails the job with a user-facing timeout message

#### Scenario: Retryable stage fails
- **WHEN** a retryable stage fails with a retryable error and retry attempts remain
- **THEN** the system records the failed attempt, increments the retry count, and retries the stage according to the configured policy

#### Scenario: Non-retryable stage fails
- **WHEN** a non-retryable stage fails
- **THEN** the system fails the job without retrying and preserves the diagnostic context

### Requirement: Idempotent job submission
The system SHALL support idempotent real-analysis job submission based on stable input and configuration signatures.

#### Scenario: Duplicate submission is detected
- **WHEN** a client submits the same input video, calibration, analysis options, and model/runtime configuration without requesting a new version
- **THEN** the system returns or references the existing queued, running, or succeeded job rather than starting duplicate work

#### Scenario: New version is requested
- **WHEN** a client explicitly requests a new analysis version for an otherwise identical input signature
- **THEN** the system creates a new job version and records the relationship to the previous signature-compatible job

#### Scenario: Configuration changes
- **WHEN** the same video is submitted with materially different analysis options or model/runtime configuration
- **THEN** the system treats it as a distinct analysis signature and may create a separate job

### Requirement: Research-grade execution record
The system SHALL preserve enough execution metadata to support product debugging and research reproducibility.

#### Scenario: Completed job is inspected for research
- **WHEN** a developer or researcher reviews a completed real analysis job
- **THEN** the job record exposes the input references, analysis configuration signature, stage timings, model/runtime availability, artifact references, and terminal status needed to reproduce or compare the run

#### Scenario: Internal diagnostics are stored
- **WHEN** internal error details or environment diagnostics are recorded
- **THEN** the system separates them from user-facing messages so the UI does not expose stack traces or sensitive local paths unnecessarily

### Requirement: 任务调度保留并传递源 FPS
系统 SHALL 在分析任务创建、持久化、签名和 worker 执行过程中保留用户确认的源 FPS。

#### Scenario: 创建任务保存 FPS
- **WHEN** API 收到包含源 FPS 的分析任务创建请求
- **THEN** JobStore MUST 将该 FPS 保存到任务摘要或任务输入中
- **AND** 后续查询任务时 SHALL 能读取该 FPS

#### Scenario: Worker 传递 FPS 给 Pipeline
- **WHEN** AnalysisWorker 执行包含源 FPS 的任务
- **THEN** worker MUST 将源 FPS 传递给 AnalysisPipeline
- **AND** Pipeline MUST 使用该值计算 `effective_fps`

#### Scenario: FPS 纳入签名
- **WHEN** `analysis_signature()` 计算任务签名
- **THEN** 签名输入 MUST 包含源 FPS 或其规范化等价值
- **AND** 不同源 FPS 的任务 MUST 产生不同签名

### Requirement: 分析任务支持时间裁剪与预热区间

系统 MUST 在 AnalysisJob JSON Schema 中支持 clip 参数（非数据库列），Pipeline 执行时使用预热区间。

#### Scenario: Job Schema 包含 clip 字段

- **WHEN** 创建含裁剪参数的分析任务
- **THEN** `AnalysisJobCreate` SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** `AnalysisJobSummary` SHALL 包含对应字段

#### Scenario: 任务签名包含 clip 信息

- **WHEN** `analysis_signature()` 计算
- **THEN** 输入 payload SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** 同一视频不同 Rally SHALL 产生不同签名

#### Scenario: Pipeline 预热区间

- **WHEN** 任务携带 clip 范围
- **THEN** 解码范围 SHALL = `[clip_start - pre_roll_ms, clip_end + post_roll_ms)`
- **AND** 默认 pre_roll_ms=1500, post_roll_ms=500
- **AND** 半开区间 `[start, end)`，相邻片段不会在边界重复处理
- **AND** 预热帧不纳入正式分析指标

#### Scenario: Pipeline 裁剪结果记录

- **WHEN** Pipeline 按 clip 范围执行
- **THEN** 结果 SHALL 记录 `requested_clip.start_ms/end_ms` 和 `decoded_range.start_ms/end_ms`

### Requirement: 可执行判定统一为 is_runnable

`JobStore.claim_next()` / `claim` 的可执行判定 MUST 收口为 `is_runnable(job)`：`canonicalStatus != "queued"` → False；`analysisKind=single_view` → True；`analysisKind=multiview` → `orchestrationStatus ∈ {fusion_ready, fallback_ready}`。MUST NOT 再直接按 `canonicalStatus == "queued"` 领取。

#### Scenario: waiting_sources 不被领取

- **WHEN** `claim_next()` 遇到 `orchestrationStatus=waiting_sources` 的 Parent
- **THEN** 该 Parent SHALL 被跳过，不占用 Worker（杜绝 Parent 占锁等待 child 的死锁）

#### Scenario: fusion_ready 正常领取

- **WHEN** Parent `orchestrationStatus=fusion_ready`
- **THEN** `claim_next()` SHALL 按既有优先级/排队规则领取

### Requirement: Worker 经 Executor registry 分发

`AnalysisWorkerRuntime._execute` MUST 通过 `executor_registry.resolve(job.analysisKind)` 解析执行体并调用 `execute(job, token, progress_callback)`，MUST NOT 在 Worker 主循环内按 `analysisKind` 硬编码分支。第一版 registry 仅含 SingleView / MultiView 两个执行体（不做插件框架）。取消/重试/超时兜底逻辑归属与行为保持不变。

#### Scenario: 单摄执行不变

- **WHEN** 执行 `analysisKind=single_view` 任务
- **THEN** 行为 SHALL 与改造前一致（SingleViewAnalysisExecutor 封装现有 Pipeline）
- **AND** 现有单摄回归测试 SHALL 通过

#### Scenario: 双摄执行链路

- **WHEN** 执行 `analysisKind=multiview` 的 Parent
- **THEN** MultiViewAnalysisExecutor SHALL 读 child 产物 → 执行 Fusion → Composer → 返回 Parent 结果

### Requirement: 新增编排字段兼容读取

`AnalysisJobSummary` MUST 支持新增字段（`analysisKind` / `visibility` / `parentJobId` / `analysisScope` / `orchestrationStatus` / `fusionRunId` / `sourceJobs` / `viewRuns` / `referenceViewId` / `clipStartMs` / `clipEndMs`）的历史兼容读取：缺省按 `single_view` / `public` / `none` 解析，不破坏既有任务。

#### Scenario: 历史任务读取

- **WHEN** 读取不含新字段的历史 job
- **THEN** 系统 SHALL 按缺省值解析并正常渲染

