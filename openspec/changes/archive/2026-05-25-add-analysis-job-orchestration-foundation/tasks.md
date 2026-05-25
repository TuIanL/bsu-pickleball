## 1. Orchestration Domain Model

- [x] 1.1 Define canonical job statuses, compatibility display statuses, stage statuses, error fields, retry metadata, and cancellation fields in backend schemas.
- [x] 1.2 Extend frontend TypeScript analysis/job types to consume canonical status, compatibility status, richer stage telemetry, timing, and cancellation fields.
- [x] 1.3 Define stable pipeline stage identifiers and error-code constants for upload, queue, calibration, video-read, frame-sampling, detection, pose, tracking, projection, metrics, visualization, and report stages.
- [x] 1.4 Add input/config signature fields and versioning fields needed for idempotent job submission and research reproducibility.

## 2. Durable Job Store

- [x] 2.1 Introduce a `JobStore` service boundary for creating, reading, listing, updating, claiming, canceling, and deleting durable job records.
- [x] 2.2 Implement the first storage backend using atomic local persistence or SQLite, preserving existing local data directory conventions.
- [x] 2.3 Migrate existing persisted job summary read/list behavior to the new store without losing compatibility with current JSON job files.
- [x] 2.4 Persist stage telemetry updates with timestamps, duration, progress, public message, internal diagnostic message, error code, retry count, and structured counters.
- [x] 2.5 Add tests for job creation, listing, unreadable persisted records, terminal state persistence, and restart-visible queued/running jobs.

## 3. Local Queue and Worker Runtime

- [x] 3.1 Create a local queue selector that orders queued jobs by priority and creation time.
- [x] 3.2 Add a worker runtime that claims queued jobs, marks them running, executes the analysis pipeline, and writes terminal state through `JobStore`.
- [x] 3.3 Move real pipeline execution out of FastAPI request handlers so job creation returns after durable enqueue.
- [x] 3.4 Add conservative resource limit configuration for CPU and GPU job concurrency with defaults that serialize heavy model-backed analysis.
- [x] 3.5 Add startup/shutdown handling for the local worker in backend runtime commands or FastAPI lifecycle code.
- [x] 3.6 Add tests proving queued jobs execute via the worker and cannot be claimed twice.

## 4. Pipeline Telemetry, Cancellation, Timeout, and Retry

- [x] 4.1 Update `AnalysisPipeline` progress callbacks to emit structured stage telemetry rather than only label/status/detail text.
- [x] 4.2 Add cooperative cancellation token checks between stages and inside long frame-processing loops where feasible.
- [x] 4.3 Add cancellation API support for queued and running jobs, including terminal-state rejection for succeeded/failed/canceled jobs.
- [x] 4.4 Add configurable stage timeout handling and record timeout error codes in job/stage telemetry.
- [x] 4.5 Add bounded retry support for explicitly retryable stages and persist retry attempts in stage telemetry.
- [x] 4.6 Ensure temporary file cleanup runs when jobs fail or cancel while preserving durable job records.

## 5. Idempotency and Result Reuse

- [x] 5.1 Compute stable analysis signatures from video reference, calibration reference, frame stride/options, model/runtime configuration, and analysis mode.
- [x] 5.2 Return or reference an existing queued, running, or succeeded job when an equivalent submission arrives without a new-version request.
- [x] 5.3 Support explicit new-version/rerun requests for otherwise equivalent submissions and record the signature relationship.
- [x] 5.4 Add tests for duplicate submission, changed configuration, and explicit rerun behavior.

## 6. API and Frontend Integration

- [x] 6.1 Update analysis job creation, status, result, report, list, delete, and cancellation routes to use the orchestration service boundary.
- [x] 6.2 Preserve existing demo/sample job behavior while clearly distinguishing demo, limited real, queued/running real, succeeded real, failed, and canceled states.
- [x] 6.3 Update task management UI to display orchestration-aware statuses, stage progress, stage timing, cancellation state, and user-facing error codes/messages.
- [x] 6.4 Add cancellation controls for queued/running jobs and pending/error feedback for cancellation requests.
- [x] 6.5 Update job status page polling and result-action gating to use canonical or compatibility orchestration states.
- [x] 6.6 Ensure internal diagnostic fields are not displayed in user-facing UI surfaces.

## 7. Product and Research Positioning

- [x] 7.1 Update system architecture documentation to describe the platform as a real pickleball analysis product and research vehicle, not only a competition showcase.
- [x] 7.2 Update backend README and local runtime documentation to include job orchestration, worker execution, storage conventions, and resource-limit settings.
- [x] 7.3 Update user-facing product copy where relevant so demo/sample data remains labeled and real uploaded-video analysis is framed as the primary product flow.
- [x] 7.4 Add documentation for research-grade execution records: input/config signatures, stage timings, model/runtime context, artifacts, and reproducibility notes.
- [x] 7.5 Review existing docs for overclaims and revise wording so research output is positioned as supported by the project process and artifacts.

## 8. Verification

- [x] 8.1 Run backend unit tests covering job store, orchestration service, worker claim/execution, cancellation, idempotency, and pipeline telemetry.
- [x] 8.2 Run frontend build/type checks to verify updated job/status types and UI behavior.
- [x] 8.3 Run an end-to-end local smoke test: upload or reference a video, create job, observe queued/running stage telemetry, complete or cancel, list task, and load result/report when succeeded.
- [x] 8.4 Validate OpenSpec status for the change and update tasks/specs if implementation discoveries alter scope.
