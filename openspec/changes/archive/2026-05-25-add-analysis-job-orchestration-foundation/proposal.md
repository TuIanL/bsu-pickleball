## Why

The product is moving from a competition-facing demonstration into a real pickleball analysis platform whose video-processing, model-validation, and training-loop research will become publishable research output. Real uploaded videos, heavier models, longer processing times, and future multi-user usage require a stronger job execution foundation than the current in-process background task approach.

## What Changes

- Introduce a formal analysis job orchestration foundation covering strict job states, stage telemetry, error taxonomy, resource-aware execution, cancellation, timeout handling, retry semantics, and idempotent submission.
- Separate API responsibility from execution responsibility: the web API creates jobs and reports status while a local worker loop executes queued pipeline jobs.
- Add first-stage observability for every pipeline stage: start time, end time, duration, progress, user-facing error message, engineer-facing error detail, and stable error code.
- Add second-stage operational controls for local product use: configurable CPU/GPU concurrency limits, single-machine queue processing, cancellable jobs, stage timeout policy, and bounded retries for explicitly retryable stages.
- Reposition project description and architecture documentation from "competition showcase" to "real product and research platform", while keeping the current demo path as a labeled sample mode.
- Preserve the existing frontend routes and current MVP analysis flow while upgrading the backend contract and implementation boundaries behind them.

## Capabilities

### New Capabilities
- `analysis-job-orchestration`: Covers durable analysis job records, strict lifecycle states, stage telemetry, worker execution, local queueing, resource controls, cancellation, retry, timeout, and idempotency behavior.

### Modified Capabilities
- `video-analysis-job-flow`: Job creation and status behavior will reflect queued/running/succeeded/failed/canceled lifecycle states, richer stage telemetry, cancellation, and idempotent submissions.
- `analysis-task-management`: Task list and task actions will display orchestration-aware states, stage timing/error details, cancellation controls for active jobs, and stable handling of queued/running jobs.
- `python-vision-backend-foundation`: Backend architecture and documentation will describe API, job store, worker, queue, local storage, model runtime, and research/product positioning as first-class foundations.

## Impact

- Affected backend areas: analysis schemas, analysis routes, job service, pipeline progress callbacks, storage conventions, local runtime startup/shutdown behavior, and backend tests.
- Affected frontend areas: analysis client types, task management UI, job status page, progress/stage display, cancellation affordances, and project/product copy.
- Affected docs: architecture diagrams, backend README, project description, storage/runtime notes, and any text that frames the system as only a competition presentation.
- Dependencies may remain lightweight in the first implementation by using local JSON/SQLite-style persistence and an in-process or process-local worker loop; Redis/Celery-style distributed orchestration is intentionally deferred unless later deployment needs justify it.
