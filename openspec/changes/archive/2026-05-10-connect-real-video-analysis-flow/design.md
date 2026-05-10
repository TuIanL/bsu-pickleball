## Context

The frontend currently has a polished analysis upload form, job page, visual workspace, and report pages, but the selected video file is not sent to the backend. `createAnalysisJob` posts metadata only, and the frontend falls back to a local demo report when the API cannot be reached.

The backend already has most of the MVP analysis pieces: video upload storage, manual calibration, an `AnalysisPipeline`, player detection/tracking interfaces, court projection, movement metrics, raw pipeline result JSON, and mock-compatible report payloads. The missing product path is the connective tissue between the selected browser file, backend video storage, calibration, job execution, progress reporting, and frontend feedback.

The important constraint is that real court-coordinate movement metrics require calibration. Without a valid homography, the current pipeline cannot truthfully project tracked players onto the pickleball court. The first usable product should therefore include a lightweight four-corner calibration step for real video analysis, while preserving explicit demo/sample routes.

## Goals / Non-Goals

**Goals:**

- Upload the selected video file to the backend before creating a real analysis job.
- Link analysis jobs to `videoId`, optional `calibrationId`, and match metadata.
- Add a user-facing MVP calibration handoff using four court corners from the selected video.
- Run or schedule the backend MVP pipeline and expose status, stage details, failures, and raw result data.
- Adapt available algorithm output into the existing visual workspace and report surfaces.
- Keep the demo experience available, but stop silently treating failed real uploads as successful local mock jobs.

**Non-Goals:**

- Automatic court calibration.
- Ball tracking, paddle tracking, hit detection, rally segmentation, tactical shot classification, or pose-based action diagnosis.
- Cloud object storage, authentication, multi-user permissions, or production queue infrastructure.
- Full video overlay rendering with exported annotated video.
- Replacing the existing frontend report layout.

## Decisions

### Use a two-step upload and job creation flow

The frontend will first send the selected file as `multipart/form-data` to `/api/videos/upload`, then create an analysis job with the returned `videoId`.

Alternative considered: one multipart endpoint that uploads video and creates the job in one call. That would be convenient, but it would force a larger backend API change and make calibration awkward. The two-step flow matches the existing backend surface and allows calibration to happen between upload and job creation.

### Require calibration for full real analysis

The MVP real path will ask the user to mark the four visible court corners on a still frame from the selected video, then submit those points to the existing manual calibration endpoint. A job with `videoId` and `calibrationId` can run detection, tracking, footpoint estimation, court projection, and movement metrics.

Alternative considered: run the pipeline without calibration and show deterministic mock tracks. That keeps the UI smooth but undermines trust because the output is not derived from the uploaded video. A no-calibration path can still exist as a limited or blocked state, but it must not be presented as full analysis.

### Treat demo fallback as explicit sample mode

The current local mock fallback is useful for demos, but real uploads should fail visibly if the backend is unavailable, the upload fails, calibration fails, or analysis fails.

Alternative considered: silently creating a local mock job when the backend cannot be reached. That is friendly for a showcase, but it conflicts with the new product promise that uploaded videos are actually analyzed.

### Add a minimal background job model

Video processing can be slow, especially on CPU. Job creation should return quickly with a queued or processing job, while the backend updates a local job record as the pipeline moves through upload, calibration, video read, detection, tracking, projection, metrics, and report generation. The frontend job page will poll the job endpoint until completion or failure.

Alternative considered: keep job creation synchronous. This is simpler, but large uploads or model-backed detection can cause request timeouts and gives users no useful stage progress.

### Preserve the existing report contract through an adapter

The frontend already renders a rich `AnalysisReport`. Backend raw pipeline output should be adapted into that shape where possible: movement path from projected tracks, movement/coverage metrics from `PerformanceMetrics`, heatmap data from the heatmap artifact, and source metadata from the job.

Alternative considered: rewrite the frontend to consume raw pipeline JSON directly. That would expose implementation details everywhere and delay the first usable version. The adapter keeps the UI stable while allowing richer report data over time.

## Risks / Trade-offs

- Real model execution can be slow or unavailable on local machines -> use configurable `frameStride`, clear dependency errors, and a lightweight degraded state when detections cannot run.
- Manual calibration can be inaccurate -> require four named points, surface calibration quality, and avoid claiming precise tactical insight when projection quality is poor.
- Large video uploads can fail or take time -> show upload progress/state, validate file type, and report backend errors without losing the selected metadata.
- File-backed local storage is not a production database -> persist enough job/video/result metadata for the local MVP, while leaving multi-user durability out of scope.
- Existing report pages include tactical demo content that the MVP algorithm cannot yet infer -> mark unavailable algorithm fields clearly or replace them with movement-focused feedback instead of fabricating shot events.

## Migration Plan

1. Keep existing demo routes and local demo data unchanged.
2. Add real upload and calibration behavior behind the existing `/analysis/new` entry.
3. Add backend job persistence and status updates without changing the public route names.
4. Add a report adapter that prefers algorithm-derived fields for job routes and falls back only to explicit sample/demo content.
5. Remove or revise upload-page copy that says the selected file is not uploaded.

Rollback is straightforward for the frontend: keep the demo routes available and gate the real upload flow behind API availability. Backend rollback can retain the existing metadata-only job path for developer smoke tests.

## Open Questions

- Should the first implementation make calibration mandatory before starting analysis, or allow a clearly labeled "limited analysis" path without court projection?
- What maximum upload size and supported file duration should the local MVP enforce?
- Should YOLO model weights be bundled, downloaded on first use, or configured via an environment variable?
