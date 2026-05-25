## Context

The current backend already supports real uploaded-video analysis through FastAPI routes, local video/calibration storage, an `AnalysisPipeline`, and task/status views. Job execution is still MVP-shaped: the API schedules `BackgroundTasks`, active records live in process memory, summaries/results are written as local JSON, and stage records mainly contain label/status/detail.

That shape was acceptable while the system served as a competition demonstration and short-video prototype. The product direction has changed: the platform is now a real pickleball analysis product and a research vehicle. Video analysis runs may become longer, use heavier YOLO/RTMPose/court-calibration models, and produce artifacts that support scientific evaluation, model comparison, and publishable results. A job foundation is now part of the product, not background plumbing.

The design should preserve local development simplicity. The first implementation should not require Redis, Celery, Kubernetes, or a distributed scheduler. It should create clean boundaries so those can be introduced later without changing the frontend contract.

## Goals / Non-Goals

**Goals:**
- Define a strict job lifecycle that can represent queued, running, succeeded, failed, and canceled jobs without ambiguous `completed`/`processing` transitions.
- Persist richer stage telemetry for every pipeline stage: timestamps, duration, progress, error code, public error message, internal diagnostic detail, retry count, and skip reason when applicable.
- Move pipeline execution behind a worker boundary so API handlers create/query/cancel jobs and worker code performs model work.
- Provide local queue behavior with deterministic ordering, configurable priority, and resource limits for CPU/GPU work.
- Support cancellation, stage timeouts, and bounded retries for explicitly retryable stages.
- Add idempotent submission semantics so repeated submissions with the same input/config can reuse an existing job or intentionally create a new version.
- Update docs and product copy to describe the system as a real product and research platform while keeping sample/demo data clearly labeled.
- Keep the current route concepts and task-centered user flow stable for the frontend.

**Non-Goals:**
- Building a distributed orchestration platform in this change.
- Requiring Redis/Celery/RQ, cloud queues, containers, or multi-host worker deployment.
- Solving full GPU memory scheduling across multiple machines.
- Rewriting the computer-vision algorithms themselves.
- Implementing training-batch orchestration beyond the queue/priority hooks needed to support it later.
- Changing the current demo route into a marketing landing page.

## Decisions

### Use an orchestration service boundary instead of extending `mock_analysis.py`

Create a dedicated job orchestration layer with separate responsibilities:

```text
API routes
  |
  v
JobOrchestrationService
  |
  +-- JobStore
  +-- LocalJobQueue
  +-- WorkerRuntime
  +-- ResourceLimiter
  +-- AnalysisPipeline adapter
```

Rationale: `mock_analysis.py` currently mixes demo report generation, persisted summaries, background execution, deletion, pipeline result storage, and stage merging. Extending that module would make the product-critical execution model harder to test and reason about. A new service boundary lets the existing flow keep working while implementation migrates behind the same API routes.

Alternative considered: directly add fields and queue behavior to the existing module. This is faster initially but keeps the same coupling that caused ambiguous task behavior.

### Preserve lightweight persistence, but make the model durable

The first implementation can keep file-backed JSON persistence, or introduce SQLite if implementation complexity stays reasonable. The key design requirement is not the storage engine; it is the durable job model:

```text
JobRecord
  id
  status
  priority
  input_signature
  config_signature
  attempt
  created_at
  queued_at
  started_at
  finished_at
  cancel_requested_at
  current_stage
  progress
  public_error
  internal_error

StageRecord
  job_id
  stage_id
  status
  progress
  started_at
  finished_at
  duration_ms
  error_code
  public_message
  internal_message
  retry_count
```

Rationale: a durable schema is the contract that matters. SQLite would improve indexing and locking, but local JSON is acceptable if writes are atomic and tests cover restart/listing behavior. The design should allow a later storage implementation swap.

Alternative considered: immediately adopt Postgres or Redis as the source of truth. That is premature for a local-first research/product prototype and raises setup burden for demos.

### Introduce canonical lifecycle states and compatibility mapping

Use canonical backend states:

```text
queued -> running -> succeeded
                 \-> failed
                 \-> canceled
```

For frontend compatibility, map them to the existing task labels where needed:

| Canonical | Existing-compatible display |
| --- | --- |
| `queued` | `queued` |
| `running` | `processing` |
| `succeeded` | `completed` |
| `failed` | `failed` |
| `canceled` | `failed` or new `canceled` where UI supports it |

Rationale: `completed` is user-facing language, while `succeeded` is clearer for a state machine. The implementation can expose both a canonical `status` and compatibility field, or update TypeScript/Python schemas together.

Alternative considered: keep the existing statuses unchanged. This avoids UI changes but weakens the state machine and makes cancellation awkward.

### Keep stage progress as structured telemetry, not only copy text

Pipeline progress callbacks should send structured updates rather than only `id/label/status/detail`. A stage update should include:

- `stage_id`
- `status`
- `progress`
- `started_at` / `finished_at` when known
- `public_message`
- `internal_message`
- `error_code`
- `processed_frames`, `detections`, `subjects`, `artifact_paths`, or other metrics when relevant

Rationale: this supports user-facing progress, engineering diagnostics, and research logs from the same source. Internal messages must not leak stack traces to users.

Alternative considered: parse detail strings after the fact. That would be brittle and unsuitable for research output.

### Implement a local worker loop before external queues

The second phase should introduce a local worker runtime that polls or receives queued jobs from the job store and executes them outside request handlers. The process may still run inside the backend process for local development, but route handlers must no longer directly run the pipeline.

```text
POST /api/analysis/jobs
  -> validate input
  -> compute idempotency signature
  -> persist queued JobRecord
  -> notify local queue
  -> return immediately

Worker loop
  -> claim next queued job by priority/created_at
  -> mark running
  -> run pipeline with progress callback + cancellation token
  -> persist result/report/artifacts
  -> mark succeeded/failed/canceled
```

Rationale: this gives the product the right execution boundary without imposing external infrastructure. The same service can later be backed by Redis/RQ/Celery.

Alternative considered: keep FastAPI `BackgroundTasks`. This remains tied to the web process and cannot cleanly support resource isolation, retry, or recovery.

### Resource limits are configuration-driven and conservative

Add settings such as:

- `PICKLEBALL_MAX_CPU_JOBS`
- `PICKLEBALL_MAX_GPU_JOBS`
- `PICKLEBALL_ENABLE_GPU_JOBS`
- `PICKLEBALL_JOB_STAGE_TIMEOUT_SECONDS`
- `PICKLEBALL_JOB_MAX_RETRIES`

Default local behavior should be conservative: one heavy analysis at a time. GPU jobs should be serialized unless explicitly configured otherwise.

Rationale: the main near-term risk is one long/heavy video making the local service unstable. Strict serialization is acceptable for a research/product MVP and easier to explain in a demo.

Alternative considered: detect live GPU memory and dynamically schedule work. Useful later, but platform-specific and unnecessary for the first two phases.

### Cancellation is cooperative

Cancellation should set a durable `cancel_requested` marker and pass a cancellation token into the pipeline. The pipeline should check it between stages and inside long frame loops where feasible. Cancellation should clean temporary files while preserving the job record and user-visible terminal state.

Rationale: Python model inference cannot always be interrupted safely mid-call. Cooperative cancellation gives predictable behavior without unsafe thread/process termination.

Alternative considered: forcibly kill worker processes. That is useful for future hard timeouts but adds platform and cleanup complexity.

### Retry only safe stages

Retries should be opt-in per stage. Metadata loading, artifact writing, and report generation may be retryable. Heavy model inference should not be blindly retried unless the error is known transient and cleanup is safe.

Rationale: retrying CUDA out-of-memory or bad input video repeatedly wastes resources and hides the real problem.

Alternative considered: global retry for all failures. Simpler to implement but risky for heavy analysis.

### Idempotency uses input and config signatures

Compute a stable signature from:

- video id and uploaded file metadata/hash where available
- calibration id or calibration point hash
- frame stride and analysis options
- model/runtime config versions that affect output
- analysis mode

If a matching queued/running/succeeded job exists, the API should either return the existing job or create a new version when the request explicitly asks for rerun/new version.

Rationale: this prevents duplicate work from double-clicks and supports research reproducibility by making analysis configuration part of the identity.

Alternative considered: client-generated idempotency key only. Useful, but insufficient for detecting equivalent submissions from different clients.

### Product and research positioning belongs in docs and UI copy

Update architecture and README-like materials to describe the system as:

- a real pickleball visual-analysis product
- a research platform for sports video understanding, pose/tracking validation, court calibration, movement metrics, and training feedback
- a project whose experiments, datasets, evaluation notes, and model comparisons can become research outputs

Rationale: project framing affects feature prioritization. The execution foundation should be justified by product reliability and research reproducibility, not only presentation polish.

Alternative considered: leave positioning in proposal only. That would not reach users, collaborators, or future developers.

## Risks / Trade-offs

- [Risk] The local worker still shares a process with the API in development → Mitigation: keep the service boundary explicit and document how it can move to a separate process later.
- [Risk] JSON persistence may suffer from concurrent write edge cases → Mitigation: use atomic writes or SQLite if implementation reveals locking complexity; add tests around concurrent submission/status updates.
- [Risk] New canonical statuses may break frontend assumptions → Mitigation: update shared types and provide compatibility mapping during migration.
- [Risk] Cancellation may not stop immediately inside long model calls → Mitigation: document cooperative behavior and check cancellation at stage/frame boundaries.
- [Risk] Retry logic could mask deterministic failures → Mitigation: retries are stage-specific, bounded, and recorded in telemetry.
- [Risk] Project positioning copy could overclaim scientific maturity → Mitigation: phrase research output as "research process and artifacts will support scientific output" rather than claiming completed publications.

## Migration Plan

1. Add orchestration schemas and persistence helpers while preserving existing API response fields.
2. Update job creation to persist queued jobs and return immediately.
3. Introduce local worker runtime and route existing `AnalysisPipeline` execution through it.
4. Extend pipeline callbacks to emit structured stage telemetry.
5. Update frontend types and task/job status UI to display richer state and cancellation.
6. Add idempotency handling and tests for duplicate submission.
7. Update project docs and visible copy to reflect real-product and research-platform positioning.
8. Keep demo/sample behavior intact and clearly labeled.

Rollback strategy: retain the current direct pipeline execution path behind a local setting during implementation, then remove it once tests cover the worker-backed flow.

## Open Questions

- Should the first implementation use atomic JSON files or SQLite for job records?
- Should canonical API status values switch immediately to `succeeded/canceled`, or should the first implementation expose compatibility values while adding canonical fields?
- Which pipeline stages should be retryable in the first pass?
- How much internal diagnostic data should be persisted locally by default when research logs may include sensitive uploaded-video metadata?
