## Context

The upload and analysis flow is already wired end-to-end: the frontend uploads a video, optionally submits calibration, creates an analysis job, polls the job status page, and opens the visual workspace after completion. However, the current failure path collapses backend context into generic messages. `requestJson` and `requestForm` only expose HTTP status, upload-page handlers replace caught errors with static Chinese copy, and automatic court-line calibration hides the useful diagnostics already returned by the backend.

The backend job runner also reports a coarse lifecycle. It creates a queued job, sets one processing update at `video-read`/25%, runs the full pipeline synchronously in the background task, and then sets either failed or completed. The frontend polling loop can display intermediate states, but the backend does not persist them yet.

## Goals / Non-Goals

**Goals:**

- Make frontend errors actionable by preserving endpoint, status code, backend detail, and operation context.
- Show automatic court-line calibration diagnostics that help users distinguish model setup problems, unreadable video frames, low confidence masks, and geometry rejection.
- Persist monotonic, stage-based job progress while the backend pipeline runs so the status page no longer appears stuck at one coarse percentage.
- Keep existing API payloads backward compatible and reuse optional fields already present in automatic calibration responses.
- Preserve manual four-corner calibration as the safe fallback path.

**Non-Goals:**

- Add a new external job queue, websocket stream, or long-running worker system.
- Redesign the analysis UI layout or visual brand.
- Implement a new court-line model, improve segmentation accuracy, or retrain models.
- Make automatic calibration required before analysis.
- Change demo analysis behavior except where shared error/progress components are reused.

## Decisions

### Structured frontend API errors

Introduce a small frontend error wrapper, for example `AnalysisApiError`, created by `requestJson` and `requestForm` when `response.ok` is false or response parsing fails. It should retain:

- request path and resolved URL
- HTTP status and status text when available
- backend `detail`, including string or structured FastAPI detail payloads
- a concise display message

This avoids changing backend routes only to improve failed request display. Handlers in the upload, automatic calibration, job, and result-loading flows can render the same error shape with context-specific titles.

Alternative considered: add custom error envelopes to every backend route. That would make errors consistent long term, but it is larger and unnecessary because FastAPI already returns useful `detail` payloads.

### Backend-owned progress

Keep the job status page driven by `AnalysisJobSummary.progress` and `AnalysisJobSummary.stages`, but update those fields more often during `run_analysis_job`. Add a progress callback or helper boundary around existing pipeline steps so the job can be persisted at meaningful stages:

`queued -> video-read -> frame-sampling -> detection -> pose -> tracking -> projection -> metrics -> visualization -> report`.

Progress should be derived from the ordered stage list and clamped so it never moves backward for a single job. Stage details should include counts or skip reasons when the pipeline knows them, while preserving current final `AnalysisPipelineResult` output.

Alternative considered: simulate progress in the frontend between polls. That would look smoother but would not help users locate backend failures, and it could lie about work that has not started.

### Diagnostic rendering for automatic calibration

Use the existing `AutomaticCalibrationResponse` fields as the source of truth:

- `status`
- `detail`
- `selected_frame`
- `confidence`
- `quality.reprojection_error`
- `mask.model_configured`
- `mask.model_path`
- `mask.confidence`
- `mask.mask_area_ratio`
- `mask.line_count`
- `mask.detail`
- `preview_image_url`

The upload workflow should show a compact diagnostic panel after any automatic calibration attempt. Available suggestions still fill points and preview. Rejected or unavailable results should explain why and keep manual point selection active.

Alternative considered: treat automatic calibration failure as a top-level form error only. That is simpler but loses exactly the information needed to distinguish local setup issues from poor video/frame geometry.

### Backward compatibility

No existing required schema fields should be removed. New diagnostics should be optional, and frontend rendering should tolerate older stored jobs or calibration responses that lack newer fields.

## Risks / Trade-offs

- Stage updates may still appear coarse if the current pipeline has large blocking calls inside a single function → add updates at every existing boundary first, then consider finer callbacks only if needed.
- Writing job JSON more often increases local storage writes → only persist when stage/progress/detail changes and keep payloads small.
- Backend detail strings may be technical or English → render them as diagnostic details rather than replacing user-friendly Chinese summary text.
- Automatic calibration diagnostics can make the upload form feel busy → keep the primary status sentence short and place technical values in a compact detail list.
