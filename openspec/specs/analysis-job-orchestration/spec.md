# analysis-job-orchestration Specification

## Purpose
TBD - created by archiving change add-analysis-job-orchestration-foundation. Update Purpose after archive.
## Requirements
### Requirement: Durable analysis job lifecycle
The system SHALL manage real analysis jobs through a strict durable lifecycle with canonical states `queued`, `running`, `succeeded`, `failed`, and `canceled`.

#### Scenario: Job is created
- **WHEN** a valid real analysis request is accepted
- **THEN** the system persists a job record with status `queued`, creation time, queue time, input references, analysis configuration, current stage, progress, and initial stage records before returning the job response

#### Scenario: Worker starts a job
- **WHEN** a worker claims a queued job for execution
- **THEN** the system atomically marks the job as `running`, records the start time, records the worker identity when available, and prevents another worker from claiming the same job

#### Scenario: Job succeeds
- **WHEN** all required analysis stages and report generation complete
- **THEN** the system marks the job as `succeeded`, records the finish time, stores result/report artifact references, and leaves stage telemetry available for later inspection

#### Scenario: Job fails
- **WHEN** a non-recoverable stage error occurs
- **THEN** the system marks the job as `failed`, records the finish time, records a stable error code, records a user-facing error message, and persists internal diagnostic detail separately

#### Scenario: Job is canceled
- **WHEN** a cancellation request is accepted for a queued or running job
- **THEN** the system eventually marks the job as `canceled`, records cancellation timing, stops or skips remaining analysis stages, cleans temporary files when safe, and preserves the job record

### Requirement: Stage telemetry
The system SHALL persist structured telemetry for each analysis stage rather than relying only on free-text progress details.

#### Scenario: Stage starts
- **WHEN** a stage begins execution
- **THEN** the system records the stage identifier, status, start time, initial progress, and public stage message

#### Scenario: Stage updates progress
- **WHEN** a long-running stage reports progress
- **THEN** the system updates stage progress and may record structured counters such as processed frames, detections, subjects, generated artifacts, or skipped prerequisites

#### Scenario: Stage finishes
- **WHEN** a stage completes, skips, fails, or is canceled
- **THEN** the system records the end time, duration, terminal status, final progress, public message, and any internal diagnostic fields

#### Scenario: Stage error is reported
- **WHEN** a stage fails
- **THEN** the system records a stable error code, a user-facing error message safe to display, and an engineer-facing internal message suitable for local diagnosis

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
